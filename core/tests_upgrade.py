"""Tests for the v2.1 upgrade: subscription flow fixes, redeem preview + QR, nudges, cooldown data, streak reminders."""
from datetime import timedelta
from io import BytesIO

from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APITestCase

from .billing import mark_paid, revoke_period
from .models import CustomerProfile, Notification, Payment, RewardGrant, Subscription, User, get_sub
from .tests_growth import GrowthBase


def _png():
    buf = BytesIO()
    Image.new("RGB", (4, 4), "white").save(buf, "PNG")
    buf.seek(0)
    buf.name = "proof.png"
    return buf


class SubscriptionFlowTests(GrowthBase):
    def owner(self):
        return User.objects.get(username="9100000001")

    def texts(self, user):
        return list(Notification.objects.filter(user=user).values_list("text", flat=True))

    def test_payment_success_notifies_owner_and_status_lists_history(self):
        p = Payment.objects.create(owner=self.owner(), plan="monthly", amount=9900, method="upi", status="pending", utr="U1")
        mark_paid(p.pk)
        self.assertTrue(any("Payment received" in t for t in self.texts(self.owner())))
        self.as_owner()
        d = self.client.get("/api/billing/").data
        self.assertEqual(d["payments"][0]["status"], "paid")
        self.assertEqual(d["yearly_saving"], 9900 * 12 - 99900)
        self.assertIsNone(d["last_rejected"])

    def test_admin_reject_only_touches_pending_upi_and_notifies(self):
        from django.contrib import admin as dj_admin
        from .admin import PaymentAdmin
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory
        o = self.owner()
        paid = Payment.objects.create(owner=o, plan="monthly", amount=9900, method="upi", status="paid", utr="U3")
        pend = Payment.objects.create(owner=o, plan="monthly", amount=9900, method="upi", status="pending", utr="U2")
        rf = RequestFactory().post("/"); rf.session = {}; rf._messages = FallbackStorage(rf)
        PaymentAdmin(Payment, dj_admin.site).reject(rf, Payment.objects.all())
        pend.refresh_from_db(); paid.refresh_from_db()
        self.assertEqual((pend.status, paid.status), ("rejected", "paid"))
        self.assertTrue(any("could not verify" in t for t in self.texts(o)))
        self.as_owner()
        self.assertEqual(self.client.get("/api/billing/").data["last_rejected"]["utr"], "U2")

    def test_refund_removes_paid_period_and_pauses_shop(self):
        o = self.owner()
        p = Payment.objects.create(owner=o, plan="monthly", amount=9900, method="upi", status="pending", utr="U4")
        get_sub(o); Subscription.objects.filter(owner=o).update(trial_ends=timezone.now() - timedelta(days=40))
        mark_paid(p.pk)
        self.assertEqual(get_sub(o).state, "active")
        revoke_period(p.pk)
        self.assertEqual(get_sub(o).state, "grace")  # trial is long over, so the shop pauses
        self.assertEqual(Payment.objects.get(pk=p.pk).status, "refunded")
        revoke_period(p.pk)  # idempotent
        self.assertTrue(any("refunded" in t for t in self.texts(o)))

    def test_refund_keeps_remaining_free_trial(self):
        o = self.owner()
        p = Payment.objects.create(owner=o, plan="monthly", amount=9900, method="upi", status="pending", utr="U5")
        mark_paid(p.pk)  # paid early, trial still running
        revoke_period(p.pk)
        self.assertEqual(get_sub(o).state, "trial")

    @override_settings(RAZORPAY_KEY_ID="rzp_test_x", RAZORPAY_KEY_SECRET="s", RAZORPAY_WEBHOOK_SECRET="w",
                       RZP_PLAN_IDS={"monthly": "plan_m", "yearly": "plan_y"})
    def test_webhook_bad_json_is_400_and_charge_is_applied_once(self):
        import hashlib, hmac, json
        o = self.owner()
        get_sub(o); Subscription.objects.filter(owner=o).update(rzp_sub_id="sub_1", rzp_autorenew_active=True)
        body = json.dumps({"event": "subscription.charged", "payload": {
            "subscription": {"entity": {"id": "sub_1", "plan_id": "plan_m"}},
            "payment": {"entity": {"id": "pay_1", "amount": 9900, "order_id": "order_1"}}}}).encode()
        sig = hmac.new(b"w", body, hashlib.sha256).hexdigest()
        for _ in range(2):
            self.assertEqual(self.client.post("/api/billing/webhook/", body, content_type="application/json",
                                              HTTP_X_RAZORPAY_SIGNATURE=sig).status_code, 200)
        self.assertEqual(Payment.objects.filter(payment_id="pay_1").count(), 1)
        bad = b"not json"
        sig2 = hmac.new(b"w", bad, hashlib.sha256).hexdigest()
        self.assertEqual(self.client.post("/api/billing/webhook/", bad, content_type="application/json",
                                          HTTP_X_RAZORPAY_SIGNATURE=sig2).status_code, 400)

    @override_settings(RAZORPAY_KEY_ID="rzp_test_x", RAZORPAY_KEY_SECRET="s")
    def test_gateway_outage_is_a_friendly_400_not_a_500(self):
        from unittest import mock
        self.as_owner()
        with mock.patch("core.billing.urllib.request.urlopen", side_effect=OSError("down")):
            r = self.client.post("/api/billing/order/", {"plan": "monthly"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("payment service", str(r.data).lower())

    def test_autopay_owner_gets_autorenew_notice_not_renew_nag(self):
        o = self.owner()
        get_sub(o); Subscription.objects.filter(owner=o).update(paid_until=timezone.now() + timedelta(days=3), rzp_sub_id="sub_9", rzp_autorenew_active=True)
        call_command("send_reminders")
        t = self.texts(o)
        self.assertFalse(any("Renew from Billing" in x for x in t))
        # owner reminders go through notify() (log/webhook) not push(); the dedupe row proves the right branch ran
        from .models import ReminderLog
        self.assertTrue(ReminderLog.objects.filter(owner=o, kind="autorenew_7d").exists())


class RewardClickTests(GrowthBase):
    def grant(self, cust_tok):
        for _ in range(5):
            self.buy(cust_tok)
        return RewardGrant.objects.filter(reward__task=self.visit_task).first()

    def test_lookup_previews_then_redeem_works_and_other_shop_cannot_peek(self):
        cust = self.customer("9100000020")
        g = self.grant(cust)
        self.as_owner()
        r = self.client.post("/api/rewards/lookup/", {"code": g.code.lower()})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((r.data["reward"], r.data["redeemable"], r.data["shop"]), ("Free chai", True, "Chai Point"))
        self.assertEqual(self.client.post("/api/rewards/redeem/", {"code": g.code}).status_code, 200)
        self.assertFalse(self.client.post("/api/rewards/lookup/", {"code": g.code}).data["redeemable"])
        # a different owner gets the same answer as for an unknown code
        self.login("9100000099", "owner")
        self.assertEqual(self.client.post("/api/rewards/lookup/", {"code": g.code}).status_code, 400)
        self.assertEqual(self.client.post("/api/rewards/lookup/", {"code": "ZZZZZZZZ"}).status_code, 400)

    def test_customer_cannot_use_lookup(self):
        cust = self.customer("9100000021")
        self.client.credentials(HTTP_AUTHORIZATION=cust)
        self.assertEqual(self.client.post("/api/rewards/lookup/", {"code": "AAAAAAAA"}).status_code, 403)

    def test_reward_qr_is_png_and_rejects_junk(self):
        self.client.credentials()
        r = self.client.get("/api/rewards/qr/ABCD1234.png")
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "image/png"))
        self.assertEqual(self.client.get("/api/rewards/qr/../../etc.png").status_code, 404)
        self.assertEqual(self.client.get("/api/rewards/qr/nothex!!.png").status_code, 404)

    def test_almost_there_nudge_fires_once_at_one_step_left(self):
        cust = self.customer("9100000022")
        user = User.objects.get(username="9100000022")
        for _ in range(3):
            self.buy(cust)
        self.assertFalse(Notification.objects.filter(user=user, text__startswith="Almost there").exists())
        self.buy(cust)  # 4 of 5
        self.assertEqual(Notification.objects.filter(user=user, text__startswith="Almost there").count(), 1)
        self.buy(cust)  # reward unlocked, no nudge
        self.assertEqual(Notification.objects.filter(user=user, text__startswith="Almost there").count(), 1)

    def test_shop_state_reports_cooldown_and_daily_allowance(self):
        from .models import Business
        Business.objects.filter(pk=self.biz.pk).update(cooldown_minutes=10, daily_cap=3)
        cust = self.customer("9100000023")
        self.client.credentials(HTTP_AUTHORIZATION=cust)
        d = self.client.get(f"/api/me/shop/{self.code}/").data
        self.assertEqual((d["cooldown_seconds"], d["entries_left_today"], d["daily_cap"]), (0, 3, 3))
        self.client.post("/api/entries/", {"task": self.visit_task.id, "value": 1})
        d = self.client.get(f"/api/me/shop/{self.code}/").data
        self.assertTrue(0 < d["cooldown_seconds"] <= 600)
        self.assertEqual((d["entries_left_today"], d["pending_count"]), (2, 1))


class StreakReminderTests(GrowthBase):
    def test_saturday_nudge_for_two_week_streak_once_per_week(self):
        from .models import PurchaseEntry
        cust = self.customer("9100000030")
        user = User.objects.get(username="9100000030")
        self.buy(cust)
        e = PurchaseEntry.objects.get(profile__user=user)
        today = timezone.localdate()
        last_mon = today - timedelta(days=today.weekday() + 7)  # Monday of last week, then the week before
        for entry, day in ((e, last_mon), (PurchaseEntry.objects.create(profile=e.profile, task=e.task, value=1, status="approved"),
                                           last_mon - timedelta(days=7))):
            PurchaseEntry.objects.filter(pk=entry.pk).update(created_at=timezone.make_aware(
                timezone.datetime(day.year, day.month, day.day, 12, 0)))
        call_command("send_reminders", "--force-streaks")
        call_command("send_reminders", "--force-streaks")
        self.assertEqual(Notification.objects.filter(user=user, text__startswith="Streak alert: 2 weeks in a row").count(), 1)


class RewardEditAndInvolvementTests(GrowthBase):
    def test_owner_edits_reward_and_task_with_validation(self):
        self.as_owner()
        rw = self.visit_task.rewards.first()
        r = self.client.patch(f"/api/rewards/{rw.id}/", {"title": "Free masala chai", "type": "free_item", "expiry_days": 45, "terms": "Dine-in only"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        rw.refresh_from_db()
        self.assertEqual((rw.title, rw.expiry_days, rw.terms), ("Free masala chai", 45, "Dine-in only"))
        for bad in ({"title": ""}, {"type": "diamond"}, {"expiry_days": 0}, {"type": "percent_off", "value": 150}, {"value": "abc"}):
            self.assertEqual(self.client.patch(f"/api/rewards/{rw.id}/", bad, format="json").status_code, 400, bad)
        self.assertEqual(self.client.patch(f"/api/tasks/{self.visit_task.id}/", {"target": 0}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(f"/api/tasks/{self.visit_task.id}/", {"title": "6 visits", "target": 6}, format="json").status_code, 200)

    def test_other_owner_cannot_edit_my_reward(self):
        rw = self.visit_task.rewards.first()
        self.login("9100000077", "owner")
        self.assertEqual(self.client.patch(f"/api/rewards/{rw.id}/", {"title": "Hacked"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/rewards/{rw.id}/").status_code, 404)

    def test_add_task_with_reward_to_running_program(self):
        self.as_owner()
        pid = self.biz.programs.first().id
        r = self.client.post(f"/api/programs/{pid}/tasks/", {"title": "Buy 3 samosas", "type": "count", "target": 3, "item_name": "samosa",
            "reward": {"title": "Free samosa", "type": "free_item", "expiry_days": 20}}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(len(r.data["tasks"]), 3)
        self.assertEqual(self.client.post(f"/api/programs/{pid}/tasks/", {"title": "x", "type": "nope", "target": 1}, format="json").status_code, 400)
        self.assertEqual(self.client.post(f"/api/programs/{pid}/tasks/", {"title": "x", "type": "count", "target": 0}, format="json").status_code, 400)

    def test_reward_activity_shows_customers_with_nudge_flag(self):
        cust = self.customer("9100000040")
        self.buy(cust)
        self.as_owner()
        data = self.client.get(f"/api/b/{self.code}/reward-activity/").data["rewards"]
        row = next(x for x in data if x["task"] == "5 visits")
        self.assertEqual(row["stats"]["participants"], 1)
        c = row["customers"][0]
        self.assertFalse(c["can_nudge"])  # no consent yet
        self.assertIn("profile_id", c)

    def test_nudge_needs_consent_and_is_rate_limited(self):
        cust = self.customer("9100000041")
        prof = CustomerProfile.objects.get(user__username="9100000041")
        self.as_owner()
        url = f"/api/b/{self.code}/customers/{prof.id}/nudge/"
        self.assertEqual(self.client.post(url, {}).status_code, 400)
        CustomerProfile.objects.filter(pk=prof.pk).update(marketing_consent=True)
        self.assertEqual(self.client.post(url, {"text": "Come back for a free chai"}).status_code, 200)
        n = Notification.objects.filter(user=prof.user).latest("id")
        self.assertEqual(n.link, f"/b/{self.code}/?tab=earn")
        self.assertEqual(self.client.post(url, {}).status_code, 400)  # once per 3 days
        self.login("9100000078", "owner")
        self.assertEqual(self.client.post(url, {}).status_code, 404)

    def test_winback_gift_creates_real_codes_for_consenting_lapsed_only(self):
        from .models import PurchaseEntry
        old = self.customer("9100000042"); self.buy(old)
        PurchaseEntry.objects.update(created_at=timezone.now() - timedelta(days=90), reviewed_at=timezone.now() - timedelta(days=90))
        fresh = self.customer("9100000043"); self.buy(fresh)
        CustomerProfile.objects.update(marketing_consent=True)
        self.as_owner()
        pre = self.client.get(f"/api/b/{self.code}/winback/?segment=lapsed").data
        self.assertEqual(pre["audience"], 1)
        self.assertEqual(self.client.post(f"/api/b/{self.code}/winback/", {"segment": "lapsed"}).status_code, 400)  # needs a gift name
        r = self.client.post(f"/api/b/{self.code}/winback/", {"segment": "lapsed", "title": "Free cookie", "expiry_days": 7})
        self.assertEqual((r.status_code, r.data["sent"]), (200, 1))
        g = RewardGrant.objects.get(reward__trigger="winback")
        self.assertEqual(g.profile.user.username, "9100000042")
        self.assertIn(g.code, Notification.objects.filter(user=g.profile.user).latest("id").text)
        # the gift is a normal code the shop can redeem
        self.assertEqual(self.client.post("/api/rewards/redeem/", {"code": g.code}).status_code, 200)
        self.assertEqual(self.client.post(f"/api/b/{self.code}/winback/", {"segment": "lapsed", "title": "Again"}).status_code, 400)  # once a day


class NotificationLinkTests(GrowthBase):
    def test_links_are_stored_returned_and_unsafe_ones_dropped(self):
        from .notify import push, safe_link
        u = User.objects.get(username="9100000001")
        push(u, "x", link="/app/#/billing")
        push(u, "y", link="https://evil.example/phish")
        push(u, "z", link="//evil.example")
        push(u, "w", link="javascript:alert(1)")
        self.as_owner()
        got = {n["text"]: n["link"] for n in self.client.get("/api/notifications/").data}
        self.assertEqual((got["x"], got["y"], got["z"], got["w"]), ("/app/#/billing", "", "", ""))
        self.assertEqual(safe_link("/b/ABC/?tab=rewards"), "/b/ABC/?tab=rewards")

    def test_reward_unlock_and_pending_notifications_deep_link(self):
        cust = self.customer("9100000050")
        for _ in range(5):
            self.buy(cust)
        user = User.objects.get(username="9100000050")
        n = Notification.objects.filter(user=user, text__startswith="Reward unlocked").latest("id")
        self.assertEqual(n.link, f"/b/{self.code}/?tab=rewards")
        owner_note = Notification.objects.filter(user__username="9100000001", text__startswith="New purchase pending").latest("id")
        self.assertEqual(owner_note.link, "/app/#/")

    def test_mark_single_notification_read(self):
        u = User.objects.get(username="9100000001")
        from .notify import push
        push(u, "a"); push(u, "b")
        ids = list(Notification.objects.filter(user=u).values_list("id", flat=True))
        self.as_owner()
        self.assertEqual(self.client.post("/api/notifications/read/", {"ids": [ids[0]]}, format="json").data["updated"], 1)
        self.assertEqual(Notification.objects.filter(user=u, read=False).count(), len(ids) - 1)


class AutoPayPlanTests(GrowthBase):
    @override_settings(RAZORPAY_KEY_ID="rzp_test_x", RAZORPAY_KEY_SECRET="s", RZP_PLAN_IDS={"monthly": "", "yearly": ""})
    def test_autopay_creates_plan_once_and_reuses_it(self):
        from unittest import mock
        from .models import GatewayPlan
        calls = []

        def fake(path, body):
            calls.append((path, body))
            return {"id": "plan_new"} if path == "plans" else {"id": "sub_new"}

        self.as_owner()
        self.assertTrue(self.client.get("/api/billing/").data["autopay"])
        with mock.patch("core.billing._rzp_post", side_effect=fake):
            r = self.client.post("/api/billing/autopay/", {"plan": "monthly"})
        self.assertEqual((r.status_code, r.data["subscription_id"]), (200, "sub_new"))
        plan_call = next(b for p, b in calls if p == "plans")
        self.assertEqual((plan_call["period"], plan_call["item"]["amount"]), ("monthly", 9900))
        sub_call = next(b for p, b in calls if p == "subscriptions")
        self.assertEqual(sub_call["plan_id"], "plan_new")
        self.assertEqual(GatewayPlan.objects.get(plan="monthly").rzp_plan_id, "plan_new")
        # a second owner reuses the cached plan: no new "plans" call
        calls.clear()
        self.login("9100000090", "owner")
        with mock.patch("core.billing._rzp_post", side_effect=fake):
            self.client.post("/api/billing/autopay/", {"plan": "monthly"})
        self.assertFalse(any(p == "plans" for p, _ in calls))

    @override_settings(RAZORPAY_KEY_ID="rzp_test_x", RAZORPAY_KEY_SECRET="s", RZP_PLAN_IDS={"monthly": "", "yearly": ""})
    def test_price_change_creates_a_new_plan_and_webhook_maps_auto_plans(self):
        from unittest import mock
        from . import billing
        from .models import GatewayPlan
        GatewayPlan.objects.create(plan="monthly", rzp_plan_id="plan_old", amount=19900)
        with mock.patch("core.billing._rzp_post", return_value={"id": "plan_fresh"}):
            self.assertEqual(billing.plan_id("monthly"), "plan_fresh")
        self.assertEqual(billing.plan_for_rzp_id("plan_fresh"), "monthly")
        self.assertIsNone(billing.plan_for_rzp_id("plan_unknown"))


class PartnerSetsOwnerPasswordTests(GrowthBase):
    def vendor(self):
        from .models import Vendor
        vu = User.objects.create_user("9100000600", "secret1", role="vendor", first_name="Partner")
        Vendor.objects.create(user=vu, code="PARTX1", status="approved")
        self.client.force_authenticate(user=vu)

    def test_password_is_required_validated_and_not_echoed(self):
        self.vendor()
        base = {"owner_name": "Mina", "mobile": "9200000610", "name": "Glow", "category": "salon"}
        for bad in ({}, {"password": ""}, {"password": "abc"}, {"password": "9200000610"}):
            r = self.client.post("/api/vendor/assist/", {**base, **bad}, format="json")
            self.assertEqual(r.status_code, 400, bad)
        self.assertFalse(User.objects.filter(username="9200000610").exists())  # nothing half-created
        self.assertEqual(self.client.post("/api/vendor/assist/", {**base, "owner_name": " ", "password": "secret1"}, format="json").status_code, 400)
        r = self.client.post("/api/vendor/assist/", {**base, "password": "Glow#2026"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertNotIn("Glow#2026", str(r.data))
        from rest_framework.test import APIClient
        ok = APIClient().post("/api/auth/login/", {"username": "9200000610", "password": "Glow#2026"}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.data["role"] if "role" in ok.data else "owner", "owner")


class QuickRewardTests(GrowthBase):
    def post(self, **kw):
        body = {"template": "stamps", "n": 8, "item": "coffees", "give": "Free coffee", "give_type": "free_item"}
        body.update(kw)
        return self.client.post(f"/api/b/{self.code}/rewards/quick/", body, format="json")

    def test_quick_add_creates_task_and_reward_in_running_program(self):
        self.as_owner()
        before = self.biz.programs.count()
        r = self.post()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(self.biz.programs.count(), before)  # added to the running program
        task = next(t for t in r.data["tasks"] if t["title"] == "Buy 8 coffees")
        self.assertEqual((task["type"], task["target"], task["rewards"][0]["title"]), ("count", "8.00", "Free coffee"))
        spend = self.post(template="spend", n=1500, give="10% off", give_type="percent_off", give_value=10)
        self.assertEqual(spend.status_code, 201, spend.data)
        self.assertTrue(any(t["title"] == "Spend ₹1,500" and t["rewards"][0]["type"] == "percent_off" for t in spend.data["tasks"]))
        visits = self.post(template="visits", n=5, give="Free dessert")
        self.assertTrue(any(t["title"] == "Visit 5 times" and t["type"] == "visit" for t in visits.data["tasks"]))

    def test_validation_duplicates_and_ownership(self):
        self.as_owner()
        self.assertEqual(self.post(template="nope").status_code, 400)
        self.assertEqual(self.post(n=0).status_code, 400)
        self.assertEqual(self.post(n=2.5).status_code, 400)
        self.assertEqual(self.post(give="").status_code, 400)
        self.assertEqual(self.post(give_type="percent_off", give_value=150).status_code, 400)
        self.assertEqual(self.post(give_type="flat_off", give_value=0).status_code, 400)
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(self.post().status_code, 400)  # same reward twice
        self.login("9100000091", "owner")
        self.assertEqual(self.post(give="Other").status_code, 404)

    def test_customers_can_earn_the_new_reward_immediately(self):
        self.as_owner()
        tid = next(t["id"] for t in self.post(template="visits", n=1, give="Free biscuit").data["tasks"] if t["title"] == "Visit 1 times")
        cust = self.customer("9100000092")
        self.client.credentials(HTTP_AUTHORIZATION=cust)
        r = self.client.post("/api/entries/", {"task": tid, "value": 1})
        self.assertEqual(r.status_code, 201, r.data)
        from .models import RewardGrant
        self.assertTrue(RewardGrant.objects.filter(reward__title="Free biscuit", profile__user__username="9100000092").exists() or r.data["status"] == "pending")

    def test_owner_can_delete_one_unused_reward_without_deleting_program(self):
        from .models import Reward, Task

        self.as_owner()
        reward = self.visit_task.rewards.first()
        sibling = Reward.objects.create(task=self.visit_task, title="Free tea", type="free_item")
        response = self.client.delete(f"/api/rewards/{reward.pk}/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["deleted"])
        self.assertFalse(Reward.objects.filter(pk=reward.pk).exists())
        self.assertTrue(Reward.objects.filter(pk=sibling.pk).exists())
        self.assertTrue(Task.objects.filter(pk=self.visit_task.pk).exists())
        self.assertTrue(self.biz.programs.exists())
        self.assertTrue(Task.objects.filter(pk=self.amount_task.pk).exists())

    def test_reward_delete_is_blocked_by_customer_activity_or_reward_code(self):
        from .models import Reward, RewardGrant, TaskProgress

        reward = self.visit_task.rewards.first()
        cust = self.customer("9100000093")
        profile = CustomerProfile.objects.get(user__username="9100000093", business=self.biz)
        TaskProgress.objects.create(profile=profile, task=self.visit_task, current_value=1, target=5)

        self.as_owner()
        response = self.client.delete(f"/api/rewards/{reward.pk}/")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Reward.objects.filter(pk=reward.pk).exists())

        TaskProgress.objects.filter(profile=profile, task=self.visit_task).delete()
        RewardGrant.objects.create(
            profile=profile, reward=reward, expires_at=timezone.now() + timedelta(days=5)
        )
        response = self.client.delete(f"/api/rewards/{reward.pk}/")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Reward.objects.filter(pk=reward.pk).exists())

    def test_pending_customer_purchase_counts_as_reward_activity(self):
        reward = self.visit_task.rewards.first()
        cust = self.customer("9100000094")
        self.client.credentials(HTTP_AUTHORIZATION=cust)
        entry = self.client.post("/api/entries/", {"task": self.visit_task.pk, "value": 1})
        self.assertEqual(entry.status_code, 201, entry.data)

        self.as_owner()
        activity = self.client.get(f"/api/b/{self.code}/reward-activity/").data["rewards"]
        row = next(item for item in activity if item["id"] == reward.pk)
        self.assertEqual(row["stats"]["participants"], 1)
        self.assertEqual(self.client.delete(f"/api/rewards/{reward.pk}/").status_code, 400)
