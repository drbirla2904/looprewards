"""Tests for the v2 growth layer: boosts, perks, referrals, tiers, segments, bookings, feedback, campaigns."""
from datetime import timedelta
from decimal import Decimal
import json
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.test import override_settings
from rest_framework.test import APITestCase

from . import engage
from .models import (Booking, Boost, Business, CustomerProfile, Feedback, Notification, PurchaseEntry, Reward,
                     RewardGrant, ShopOffer, ShopOfferItem, TaskProgress, User)


class GrowthBase(APITestCase):
    def login(self, mobile, role):
        r = self.client.post("/api/auth/register/", {"mobile": mobile, "password": "secret1", "role": role, "name": "N" + mobile[-2:], "accepted": True})
        self.client.credentials(HTTP_AUTHORIZATION="Token " + r.data["token"])
        return self.client._credentials["HTTP_AUTHORIZATION"]

    def setUp(self):
        self.owner_tok = self.login("9100000001", "owner")
        self.code = self.client.post("/api/businesses/", {"name": "Chai Point", "pay_upi_id": "chai@upi"}).data["shop_code"]
        self.client.post(f"/api/b/{self.code}/programs/", {"title": "Club", "tasks": [
            {"title": "5 visits", "type": "visit", "target": 5, "rewards": [{"title": "Free chai", "type": "free_item"}]},
            {"title": "Spend 500", "type": "amount", "target": 500, "rewards": [{"title": "50 off", "type": "flat_off", "value": 50}]}]}, format="json")
        self.biz = Business.objects.get(shop_code=self.code)
        Business.objects.filter(pk=self.biz.pk).update(cooldown_minutes=0, daily_cap=50)
        self.visit_task, self.amount_task = self.biz.programs.first().tasks.order_by("id")

    def as_owner(self):
        self.client.credentials(HTTP_AUTHORIZATION=self.owner_tok)

    def customer(self, mobile, ref=None):
        tok = self.login(mobile, "customer")
        self.client.post(f"/api/b/{self.code}/join/", {"ref": ref} if ref else {}, format="json")
        return tok

    def buy(self, cust_tok, task=None, value=1):
        """customer submits, owner approves; returns the entry id"""
        self.client.credentials(HTTP_AUTHORIZATION=cust_tok)
        r = self.client.post("/api/entries/", {"task": (task or self.visit_task).id, "value": value})
        self.assertEqual(r.status_code, 201, r.data)
        self.as_owner()
        self.client.post(f"/api/entries/{r.data['id']}/review/", {"action": "approve"})
        return r.data["id"]


class BoostTests(GrowthBase):
    def test_boost_multiplies_visit_stamps_and_undo_reverses_exactly(self):
        Boost.objects.create(business=self.biz, title="Always double", multiplier=2)
        cust = self.customer("9100000010")
        eid = self.buy(cust)
        prog = TaskProgress.objects.get(task=self.visit_task)
        self.assertEqual(prog.current_value, Decimal("2"))
        self.assertEqual(PurchaseEntry.objects.get(pk=eid).multiplier, 2)
        self.as_owner()
        self.assertEqual(self.client.post(f"/api/entries/{eid}/reverse/").status_code, 200)
        prog.refresh_from_db()
        self.assertEqual(prog.current_value, Decimal("0"))

    def test_boost_never_applies_to_spend_tasks_and_inactive_boost_is_ignored(self):
        Boost.objects.create(business=self.biz, title="Double", multiplier=2)
        Boost.objects.create(business=self.biz, title="Off", multiplier=5, active=False)
        cust = self.customer("9100000011")
        self.buy(cust, self.amount_task, 100)
        self.assertEqual(TaskProgress.objects.get(task=self.amount_task).current_value, Decimal("100"))
        self.buy(cust, self.visit_task)
        self.assertEqual(TaskProgress.objects.get(task=self.visit_task).current_value, Decimal("2"))  # 2x, not 5x

    def test_weekday_boost_only_on_matching_days(self):
        other = (timezone.localtime().weekday() + 1) % 7
        Boost.objects.create(business=self.biz, title="Other day", multiplier=3, weekdays=str(other))
        cust = self.customer("9100000012")
        self.buy(cust)
        self.assertEqual(TaskProgress.objects.get(task=self.visit_task).current_value, Decimal("1"))

    def test_owner_boost_api_validation_and_ownership(self):
        self.as_owner()
        r = self.client.post(f"/api/b/{self.code}/boosts/", {"title": "Tue", "multiplier": 2, "weekdays": "1", "start_time": "14:00", "end_time": "17:00"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(self.client.post(f"/api/b/{self.code}/boosts/", {"title": "Bad", "multiplier": 9}, format="json").status_code, 400)
        self.assertEqual(self.client.post(f"/api/b/{self.code}/boosts/", {"title": "Bad", "multiplier": 2, "weekdays": "9"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(f"/api/b/{self.code}/boosts/", {"title": "Half", "multiplier": 2, "start_time": "14:00"}, format="json").status_code, 400)
        self.login("9100000099", "owner")  # a different owner cannot touch it
        self.assertEqual(self.client.delete(f"/api/boosts/{r.data['id']}/").status_code, 404)


class PerkTests(GrowthBase):
    def _perks(self, body):
        self.as_owner()
        r = self.client.put(f"/api/b/{self.code}/perks/", body, format="json")
        self.assertEqual(r.status_code, 200, r.data)

    def test_welcome_reward_granted_once_on_first_approved_purchase(self):
        self._perks({"welcome": {"title": "Free cookie", "type": "gift", "value": 0, "expiry_days": 14}})
        cust = self.customer("9100000020")
        self.buy(cust)
        self.assertEqual(RewardGrant.objects.filter(reward__trigger="welcome").count(), 1)
        self.buy(cust)
        self.assertEqual(RewardGrant.objects.filter(reward__trigger="welcome").count(), 1)

    def test_referral_rewards_the_inviter_after_friends_first_purchase(self):
        self._perks({"referral": {"title": "Free chai for inviting", "type": "free_item"}})
        inviter = self.customer("9100000021")
        self.client.credentials(HTTP_AUTHORIZATION=inviter)
        ref = self.client.get(f"/api/me/shop/{self.code}/").data["referral_code"]
        self.assertEqual(len(ref), 6)
        friend = self.customer("9100000022", ref=ref)
        self.assertEqual(CustomerProfile.objects.get(user__username="9100000022").referred_by.user.username, "9100000021")
        self.assertFalse(RewardGrant.objects.filter(reward__trigger="referral").exists())  # not before the first purchase
        self.buy(friend)
        g = RewardGrant.objects.get(reward__trigger="referral")
        self.assertEqual(g.profile.user.username, "9100000021")
        self.buy(friend)
        self.assertEqual(RewardGrant.objects.filter(reward__trigger="referral").count(), 1)

    def test_cannot_refer_yourself_and_unknown_code_is_ignored(self):
        cust = self.customer("9100000023")
        self.client.credentials(HTTP_AUTHORIZATION=cust)
        own = self.client.get(f"/api/me/shop/{self.code}/").data["referral_code"]
        self.client.post(f"/api/b/{self.code}/join/", {"ref": own}, format="json")
        self.assertIsNone(CustomerProfile.objects.get(user__username="9100000023").referred_by)
        self.customer("9100000024", ref="NOPE00")
        self.assertIsNone(CustomerProfile.objects.get(user__username="9100000024").referred_by)

    def test_turning_a_perk_off_keeps_existing_rewards_valid(self):
        self._perks({"welcome": {"title": "Cookie", "type": "gift"}})
        self.buy(self.customer("9100000025"))
        grant = RewardGrant.objects.get(reward__trigger="welcome")
        self._perks({"welcome": None})
        self.assertTrue(RewardGrant.objects.filter(pk=grant.pk).exists())
        self.assertIsNone(self.client.get(f"/api/b/{self.code}/perks/").data["welcome"])
        self.buy(self.customer("9100000026"))
        self.assertEqual(RewardGrant.objects.filter(reward__title="Cookie").count(), 1)

    def test_perk_validation(self):
        self.as_owner()
        self.assertEqual(self.client.put(f"/api/b/{self.code}/perks/", {"welcome": {"title": "", "type": "gift"}}, format="json").status_code, 400)
        self.assertEqual(self.client.put(f"/api/b/{self.code}/perks/", {"welcome": {"title": "x", "type": "nonsense"}}, format="json").status_code, 400)
        self.assertEqual(self.client.put(f"/api/b/{self.code}/perks/", {"welcome": {"title": "x", "type": "gift", "value": "-5"}}, format="json").status_code, 400)

    def test_new_perk_notifies_only_opted_in_customers(self):
        opted_in = User.objects.create_user("9100000061", "secret1", role="customer")
        opted_out = User.objects.create_user("9100000062", "secret1", role="customer")
        CustomerProfile.objects.create(user=opted_in, business=self.biz, marketing_consent=True)
        CustomerProfile.objects.create(user=opted_out, business=self.biz)
        self._perks({"welcome": {"title": "Free cookie", "type": "gift"}})
        self.assertTrue(Notification.objects.filter(user=opted_in, text__contains="Free cookie").exists())
        self.assertFalse(Notification.objects.filter(user=opted_out).exists())


class ShopOfferTests(GrowthBase):
    def test_offer_announcement_reaches_only_opted_in_shop_members(self):
        opted_in = User.objects.create_user("9100000071", "secret1", role="customer")
        opted_out = User.objects.create_user("9100000072", "secret1", role="customer")
        CustomerProfile.objects.create(user=opted_in, business=self.biz, marketing_consent=True)
        CustomerProfile.objects.create(user=opted_out, business=self.biz)
        self.as_owner()
        response = self.client.post(f"/api/b/{self.code}/offers/", {
            "offer_type": "bogo",
            "items": json.dumps([{"name": "Coffee", "price": "50"}]),
        }, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(Notification.objects.filter(user=opted_in, text__contains="New buy-one-get-one offer").exists())
        self.assertFalse(Notification.objects.filter(user=opted_out).exists())

    def test_quick_reward_announcement_reaches_opted_in_customers(self):
        opted_in = User.objects.create_user("9100000073", "secret1", role="customer")
        CustomerProfile.objects.create(user=opted_in, business=self.biz, marketing_consent=True)
        self.as_owner()
        response = self.client.post(f"/api/b/{self.code}/rewards/quick/", {
            "template": "visits", "n": 2, "give": "Free tea", "give_type": "free_item", "give_value": 0,
            "expiry_days": 30,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(Notification.objects.filter(user=opted_in, text__contains="Free tea").exists())

    def test_reward_added_to_program_notifies_opted_in_customers(self):
        opted_in = User.objects.create_user("9100000074", "secret1", role="customer")
        CustomerProfile.objects.create(user=opted_in, business=self.biz, marketing_consent=True)
        self.as_owner()
        program = self.biz.programs.first()
        response = self.client.post(f"/api/programs/{program.id}/tasks/", {
            "title": "Buy 3 teas", "type": "count", "target": 3,
            "reward": {"title": "Free tea", "type": "free_item", "value": 0},
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(Notification.objects.filter(user=opted_in, text__contains="Free tea").exists())

    def test_shop_offer_items_are_public_and_can_be_turned_off_and_deleted(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        with override_settings(MEDIA_ROOT=media.name):
            self.as_owner()
            response = self.client.post(f"/api/b/{self.code}/offers/", {
                "offer_type": "fixed_price",
                "items": json.dumps([{"name": "Masala chai", "price": "40", "offer_price": "30"}]),
                "image_0": SimpleUploadedFile("chai.png", b"image", content_type="image/png"),
            }, format="multipart")
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(response.data["items"][0]["name"], "Masala chai")
            self.assertTrue(response.data["items"][0]["image"].endswith(".png"))

            public = self.client.get(f"/api/b/{self.code}/").data
            self.assertEqual(len(public["offers"]), 1)
            self.assertEqual(public["offers"][0]["items"][0]["offer_price"], "30.00")

            hidden = self.client.patch(f"/api/b/{self.code}/offers/{response.data['id']}/", {"active": False}, format="json")
            self.assertEqual(hidden.status_code, 200)
            self.assertEqual(self.client.get(f"/api/b/{self.code}/").data["offers"], [])
            self.assertFalse(self.client.get(f"/api/b/{self.code}/offers/").data[0]["active"])
            item = ShopOfferItem.objects.get(offer_id=response.data["id"])
            image_name = item.image.name
            self.assertTrue(item.image.storage.exists(image_name))
            deleted = self.client.delete(f"/api/b/{self.code}/offers/{response.data['id']}/")
            self.assertEqual(deleted.status_code, 204)
            self.assertFalse(item.image.storage.exists(image_name))

    def test_percentage_offer_validation_and_remove_all(self):
        self.as_owner()
        invalid = self.client.post(f"/api/b/{self.code}/offers/", {
            "offer_type": "percent_off", "value": "101",
            "items": json.dumps([{"name": "Coffee", "price": "50"}]),
        }, format="multipart")
        self.assertEqual(invalid.status_code, 400)

        created = self.client.post(f"/api/b/{self.code}/offers/", {
            "offer_type": "bogo", "items": json.dumps([
                {"name": "Coffee", "price": "50"}, {"name": "Tea", "price": "30"},
            ]),
        }, format="multipart")
        self.assertEqual(created.status_code, 201, created.data)
        removed = self.client.delete(f"/api/b/{self.code}/offers/")
        self.assertEqual(removed.status_code, 200)
        self.assertFalse(self.client.get(f"/api/b/{self.code}/offers/").data[0]["active"])

    def test_owner_can_delete_one_offer_without_touching_the_others(self):
        self.as_owner()
        def create(name):
            response = self.client.post(f"/api/b/{self.code}/offers/", {
                "offer_type": "bogo",
                "items": json.dumps([{"name": name, "price": "50"}]),
            }, format="multipart")
            self.assertEqual(response.status_code, 201, response.data)
            return response.data["id"]

        deleted_id, remaining_id = create("Coffee"), create("Tea")
        response = self.client.delete(f"/api/b/{self.code}/offers/{deleted_id}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(ShopOffer.objects.filter(pk=deleted_id).exists())
        self.assertTrue(ShopOffer.objects.filter(pk=remaining_id, business=self.biz).exists())


class TierStreakSegmentTests(GrowthBase):
    def test_tier_ladder(self):
        b = self.biz
        self.assertEqual(engage.tier_info(b, 0)["tier"], "member")
        self.assertEqual(engage.tier_info(b, 5)["tier"], "silver")
        self.assertEqual(engage.tier_info(b, 15)["tier"], "gold")
        self.assertEqual(engage.tier_info(b, 3)["to_next"], 2)
        b.tier_silver_visits, b.tier_gold_visits = 0, 0
        self.assertEqual(engage.tier_info(b, 99)["tier"], "member")  # tiers switched off

    def test_streak_counts_consecutive_weeks_and_forgives_an_empty_current_week(self):
        from datetime import date
        today = date(2026, 11, 18)  # Wednesday
        week = lambda n: today - timedelta(days=7 * n)
        self.assertEqual(engage.streak_weeks([week(0), week(1), week(2)], today), (3, True))
        self.assertEqual(engage.streak_weeks([week(1), week(2)], today), (2, False))   # this week not yet visited
        self.assertEqual(engage.streak_weeks([week(2), week(3)], today), (0, False))   # missed last week: streak broken
        self.assertEqual(engage.streak_weeks([], today), (0, False))

    def test_segments(self):
        now = timezone.now()
        d = lambda n: now - timedelta(days=n)
        self.assertEqual(engage.segment_of(0, None), "never")
        self.assertEqual(engage.segment_of(1, d(2), now), "new")
        self.assertEqual(engage.segment_of(4, d(10), now), "regular")
        self.assertEqual(engage.segment_of(4, d(45), now), "at_risk")
        self.assertEqual(engage.segment_of(4, d(90), now), "lapsed")

    def test_visits_are_counted_per_day_not_per_entry(self):
        cust = self.customer("9100000030")
        self.buy(cust)
        self.buy(cust, self.amount_task, 100)  # same day, second task
        p = CustomerProfile.objects.get(user__username="9100000030")
        self.assertEqual(len(engage.visit_days(p)), 1)


class CrmCampaignTests(GrowthBase):
    def test_customer_list_filters_and_is_owner_only(self):
        a = self.customer("9100000040")
        self.buy(a)
        self.customer("9100000041")  # joined, never bought
        self.as_owner()
        d = self.client.get(f"/api/b/{self.code}/customers/").data
        self.assertEqual(d["count"], 2)
        self.assertEqual(d["segments"]["never"], 1)
        self.assertEqual(self.client.get(f"/api/b/{self.code}/customers/?segment=new").data["count"], 1)
        self.assertEqual(self.client.get(f"/api/b/{self.code}/customers/?q=0041").data["count"], 1)
        self.client.credentials(HTTP_AUTHORIZATION=a)
        self.assertEqual(self.client.get(f"/api/b/{self.code}/customers/").status_code, 404)  # customers cannot list customers

    def test_owner_note_is_private_and_saved(self):
        self.customer("9100000042")
        self.as_owner()
        pid = self.client.get(f"/api/b/{self.code}/customers/").data["results"][0]["id"]
        r = self.client.patch(f"/api/b/{self.code}/customers/{pid}/", {"note": "likes oat milk"}, format="json")
        self.assertEqual(r.data["note"], "likes oat milk")
        self.client.credentials(HTTP_AUTHORIZATION=self.login("9100000043", "owner"))
        self.assertEqual(self.client.get(f"/api/b/{self.code}/customers/{pid}/").status_code, 404)  # another owner cannot read it

    def test_campaign_targets_segment_respects_consent_and_rate_limits(self):
        a = self.customer("9100000044")
        self.buy(a)
        self.customer("9100000045")
        CustomerProfile.objects.filter(user__username="9100000044").update(marketing_consent=True)
        CustomerProfile.objects.filter(user__username="9100000045").update(marketing_consent=False)
        self.as_owner()
        self.assertEqual(self.client.get(f"/api/b/{self.code}/campaign/?segment=all").data["audience"], 1)
        r = self.client.post(f"/api/b/{self.code}/campaign/", {"text": "Double stamps!", "segment": "all"}, format="json")
        self.assertEqual(r.data["sent"], 1)
        self.assertTrue(Notification.objects.filter(user__username="9100000044", text__contains="Double stamps").exists())
        self.assertFalse(Notification.objects.filter(user__username="9100000045", text__contains="Double stamps").exists())
        self.assertEqual(self.client.post(f"/api/b/{self.code}/campaign/", {"text": "again", "segment": "all"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(f"/api/b/{self.code}/campaign/", {"text": "x", "segment": "bogus"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(f"/api/b/{self.code}/campaign/", {"text": "", "segment": "new"}, format="json").status_code, 400)

    def test_insights_shape_and_owner_only(self):
        self.buy(self.customer("9100000046"))
        self.as_owner()
        d = self.client.get(f"/api/b/{self.code}/insights/?days=30").data
        self.assertEqual(len(d["series"]), 30)
        self.assertEqual(d["kpis"]["customers"], 1)
        self.assertEqual(sum(d["weekday"]), 1)
        self.assertEqual(self.client.get(f"/api/b/{self.code}/insights/?days=abc").status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=self.login("9100000047", "customer"))
        self.assertEqual(self.client.get(f"/api/b/{self.code}/insights/").status_code, 404)


class BookingTests(GrowthBase):
    def setUp(self):
        super().setUp()
        self.as_owner()
        Business.objects.filter(pk=self.biz.pk).update(bookings_enabled=True)
        self.svc = self.client.post(f"/api/b/{self.code}/services/", {"name": "Haircut", "price": "300", "duration_min": 30}, format="json").data
        self.when = (timezone.now() + timedelta(days=1)).isoformat()

    def book(self, cust, when=None, service=None):
        self.client.credentials(HTTP_AUTHORIZATION=cust)
        return self.client.post(f"/api/b/{self.code}/bookings/", {"service": service or self.svc["id"], "starts_at": when or self.when}, format="json")

    def test_booking_lifecycle_credits_visit_and_amount_once(self):
        cust = self.login("9100000050", "customer")
        r = self.book(cust)
        self.assertEqual(r.status_code, 201, r.data)
        bid = r.data["id"]
        self.assertTrue(Notification.objects.filter(user__username="9100000001", text__contains="New booking").exists())
        self.as_owner()
        self.assertEqual(self.client.post(f"/api/bookings/{bid}/action/", {"action": "confirm"}, format="json").data["status"], "confirmed")
        r = self.client.post(f"/api/bookings/{bid}/action/", {"action": "complete"}, format="json")
        self.assertEqual(r.data["status"], "completed")
        self.assertEqual(TaskProgress.objects.get(task=self.visit_task).current_value, Decimal("1"))
        self.assertEqual(TaskProgress.objects.get(task=self.amount_task).current_value, Decimal("300"))
        self.assertEqual(self.client.post(f"/api/bookings/{bid}/action/", {"action": "complete"}, format="json").status_code, 400)  # no double credit
        self.assertEqual(TaskProgress.objects.get(task=self.visit_task).current_value, Decimal("1"))
        self.assertEqual(Booking.objects.get(pk=bid).credited, True)

    def test_booking_rules(self):
        cust = self.login("9100000051", "customer")
        past = (timezone.now() - timedelta(hours=1)).isoformat()
        self.assertEqual(self.book(cust, past).status_code, 400)
        self.assertEqual(self.book(cust, (timezone.now() + timedelta(days=90)).isoformat()).status_code, 400)
        self.assertEqual(self.book(cust).status_code, 201)
        self.assertEqual(self.book(cust).status_code, 400)  # overlapping slot
        for d in (2, 3):
            self.assertEqual(self.book(cust, (timezone.now() + timedelta(days=d)).isoformat()).status_code, 201)
        self.assertEqual(self.book(cust, (timezone.now() + timedelta(days=4)).isoformat()).status_code, 400)  # max 3 open
        self.assertEqual(self.book(cust, service=99999).status_code, 404)

    def test_bookings_need_to_be_enabled_and_owner_cannot_book(self):
        Business.objects.filter(pk=self.biz.pk).update(bookings_enabled=False)
        self.assertEqual(self.book(self.login("9100000052", "customer")).status_code, 400)
        Business.objects.filter(pk=self.biz.pk).update(bookings_enabled=True)
        self.as_owner()
        self.assertEqual(self.client.post(f"/api/b/{self.code}/bookings/", {"service": self.svc["id"], "starts_at": self.when}, format="json").status_code, 403)

    def test_customer_can_cancel_own_but_not_confirm_or_complete_and_strangers_cannot_touch(self):
        cust = self.login("9100000053", "customer")
        bid = self.book(cust).data["id"]
        self.client.credentials(HTTP_AUTHORIZATION=cust)
        for a in ("confirm", "complete", "decline"):
            self.assertEqual(self.client.post(f"/api/bookings/{bid}/action/", {"action": a}, format="json").status_code, 403)
        stranger = self.login("9100000054", "customer")
        self.assertEqual(self.client.post(f"/api/bookings/{bid}/action/", {"action": "cancel"}, format="json").status_code, 403)
        self.client.credentials(HTTP_AUTHORIZATION=cust)
        self.assertEqual(self.client.post(f"/api/bookings/{bid}/action/", {"action": "cancel"}, format="json").data["status"], "cancelled")
        self.assertEqual(self.client.post(f"/api/bookings/{bid}/action/", {"action": "cancel"}, format="json").status_code, 400)

    def test_staff_can_work_the_queue_but_not_edit_services(self):
        self.as_owner()
        self.client.post(f"/api/b/{self.code}/staff/", {"name": "Ravi", "mobile": "9100000060", "password": "secret1"}, format="json")
        cust = self.login("9100000055", "customer")
        bid = self.book(cust).data["id"]
        tok = self.client.post("/api/auth/login/", {"username": "9100000060", "password": "secret1"}).data["token"]
        self.client.credentials(HTTP_AUTHORIZATION="Token " + tok)
        self.assertEqual(len(self.client.get(f"/api/b/{self.code}/bookings/?status=open").data), 1)
        self.assertEqual(self.client.post(f"/api/bookings/{bid}/action/", {"action": "confirm"}, format="json").status_code, 200)
        self.assertEqual(self.client.post(f"/api/b/{self.code}/services/", {"name": "X", "price": 1}, format="json").status_code, 404)

    def test_service_with_history_is_archived_not_deleted(self):
        self.book(self.login("9100000056", "customer"))
        self.as_owner()
        r = self.client.delete(f"/api/services/{self.svc['id']}/")
        self.assertTrue(r.data["archived"])
        self.assertFalse(self.client.get(f"/api/b/{self.code}/").data["services"])

    def test_service_validation(self):
        self.as_owner()
        self.assertEqual(self.client.post(f"/api/b/{self.code}/services/", {"name": "X", "price": -1, "duration_min": 30}, format="json").status_code, 400)
        self.assertEqual(self.client.post(f"/api/b/{self.code}/services/", {"name": "X", "price": 1, "duration_min": 1}, format="json").status_code, 400)


class FeedbackTests(GrowthBase):
    def test_rating_once_per_visit_and_low_rating_alerts_owner(self):
        cust = self.customer("9100000070")
        eid = self.buy(cust)
        self.client.credentials(HTTP_AUTHORIZATION=cust)
        self.assertEqual(self.client.post("/api/feedback/", {"entry": eid, "rating": 9}, format="json").status_code, 400)
        r = self.client.post("/api/feedback/", {"entry": eid, "rating": 1, "comment": "slow service"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.client.post("/api/feedback/", {"entry": eid, "rating": 5}, format="json").status_code, 400)
        self.assertTrue(Notification.objects.filter(user__username="9100000001", text__contains="Low rating").exists())
        self.as_owner()
        self.assertEqual(len(self.client.get(f"/api/b/{self.code}/feedback/").data), 1)

    def test_cannot_rate_someone_elses_or_unapproved_visit(self):
        a, b = self.customer("9100000071"), self.customer("9100000072")
        eid = self.buy(a)
        self.client.credentials(HTTP_AUTHORIZATION=b)
        self.assertEqual(self.client.post("/api/feedback/", {"entry": eid, "rating": 5}, format="json").status_code, 404)
        r = self.client.post("/api/entries/", {"task": self.visit_task.id, "value": 1})
        self.assertEqual(self.client.post("/api/feedback/", {"entry": r.data["id"], "rating": 5}, format="json").status_code, 404)  # still pending


class WalletBlueprintBrandingTests(GrowthBase):
    def test_wallet_and_shop_detail(self):
        cust = self.customer("9100000080")
        self.buy(cust)
        self.client.credentials(HTTP_AUTHORIZATION=cust)
        w = self.client.get("/api/me/wallet/").data
        self.assertEqual(len(w["shops"]), 1)
        s = w["shops"][0]
        self.assertEqual((s["visits"], s["streak"], s["tier"]["tier"]), (1, 1, "member"))
        self.assertEqual(s["best"]["title"], "5 visits")
        d = self.client.get(f"/api/me/shop/{self.code}/").data
        self.assertEqual(d["entries"][0]["status"], "approved")
        self.assertIn("referral_url", d)
        self.as_owner()
        self.assertEqual(self.client.get("/api/me/wallet/").status_code, 403)  # owners have no wallet

    def test_blueprint_applies_complete_setup_and_never_duplicates_perks(self):
        self.as_owner()
        r = self.client.post(f"/api/b/{self.code}/blueprint/", {"key": "salon"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        b = Business.objects.get(pk=self.biz.pk)
        self.assertTrue(b.bookings_enabled)
        self.assertEqual(b.services.count(), 4)
        self.assertEqual(b.perk_rewards.count(), 2)
        self.client.post(f"/api/b/{self.code}/blueprint/", {"key": "salon"}, format="json")
        b.refresh_from_db()
        self.assertEqual((b.services.count(), b.perk_rewards.count(), b.boosts.count()), (4, 2, 1))
        self.assertEqual(self.client.post(f"/api/b/{self.code}/blueprint/", {"key": "nope"}, format="json").status_code, 400)
        self.assertEqual(len(self.client.get("/api/blueprints/").data), 8)

    def test_every_blueprint_is_valid(self):
        from . import blueprints
        self.as_owner()
        for key in blueprints.BLUEPRINTS:
            self.assertEqual(self.client.post(f"/api/b/{self.code}/blueprint/", {"key": key}, format="json").status_code, 201, key)

    def test_branding_validation_and_public_page(self):
        self.as_owner()
        url = f"/api/b/{self.code}/settings/"
        self.assertEqual(self.client.patch(url, {"brand_color": "red"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"tier_silver_visits": 10, "tier_gold_visits": 5}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"phone": "abc"}, format="json").status_code, 400)
        ok = self.client.patch(url, {"brand_color": "#ff8800", "about": "Best chai", "phone": "9876543210", "silver_perk": "Free upgrade"}, format="json")
        self.assertEqual(ok.status_code, 200, ok.data)
        pub = self.client.get(f"/api/b/{self.code}/").data
        self.assertEqual((pub["brand_color"], pub["about"]), ("#ff8800", "Best chai"))
        self.assertEqual(pub["tiers"][0]["perk"], "Free upgrade")

    def test_shop_location_requires_valid_coordinate_pair(self):
        self.as_owner()
        url = f"/api/b/{self.code}/settings/"
        self.assertEqual(self.client.patch(url, {"lat": 19}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"lat": 91, "lng": 72}, format="json").status_code, 400)
        response = self.client.patch(url, {"lat": 0, "lng": 0}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data["lat"], response.data["lng"]), (0, 0))

    def test_shop_page_has_link_preview_tags_and_escapes_name(self):
        Business.objects.filter(pk=self.biz.pk).update(name='<b>"x"</b>')
        html = self.client.get(f"/b/{self.code}/").content.decode()
        self.assertIn('property="og:title"', html)
        self.assertNotIn('<b>"x"</b>', html)


    def test_staff_verifies_follow_before_one_shared_reward_is_issued(self):
        self.as_owner()
        settings_url = f"/api/b/{self.code}/settings/"
        self.assertEqual(self.client.patch(settings_url, {"instagram_url": "https://www.instagram.com/chaipoint/"}, format="json").status_code, 200)
        self.assertEqual(self.client.patch(settings_url, {"instagram_url": "https://example.com/chaipoint"}, format="json").status_code, 400)
        perks_url = f"/api/b/{self.code}/perks/"
        configured = self.client.put(perks_url, {
            "social": {"title": "Free chai", "type": "free_item", "value": 0, "expiry_days": 14},
        }, format="json")
        self.assertEqual(configured.status_code, 200, configured.data)

        customer_token = self.customer("9100000002")
        self.client.credentials(HTTP_AUTHORIZATION=customer_token)
        public = self.client.get(f"/api/b/{self.code}/").data
        self.assertEqual(public["instagram_url"], "https://www.instagram.com/chaipoint/")
        self.assertEqual(public["perks"]["social"]["title"], "Free chai")
        requested = self.client.post(f"/api/b/{self.code}/social-follow/claim/", {}, format="json")
        self.assertEqual(requested.status_code, 201, requested.data)
        self.assertEqual(self.client.get(f"/api/me/shop/{self.code}/").data["social_follow_claim"]["status"], "pending")
        self.assertEqual(RewardGrant.objects.filter(profile__user__username="9100000002").count(), 0)

        self.as_owner()
        staff_response = self.client.post(f"/api/b/{self.code}/staff/", {
            "mobile": "9100000003", "name": "Counter", "password": "secret1",
        }, format="json")
        self.assertEqual(staff_response.status_code, 201, staff_response.data)
        staff_user = User.objects.get(username="9100000003")
        self.client.force_authenticate(user=staff_user)
        claims_url = f"/api/b/{self.code}/social-follow/claims/"
        claims = self.client.get(claims_url).data["claims"]
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["mobile_last4"], "0002")
        rejected = self.client.post(f"{claims_url}{claims[0]['id']}/", {"action": "reject"}, format="json")
        self.assertEqual(rejected.status_code, 200, rejected.data)

        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=customer_token)
        self.assertEqual(self.client.post(f"/api/b/{self.code}/social-follow/claim/", {}, format="json").status_code, 201)
        self.as_owner()
        approved_claim = self.client.get(claims_url).data["claims"][0]
        approved = self.client.post(f"{claims_url}{approved_claim['id']}/", {"action": "approve"}, format="json")
        self.assertEqual(approved.status_code, 200, approved.data)
        self.assertEqual(approved.data["reward_title"], "Free chai")
        self.assertEqual(RewardGrant.objects.filter(profile__user__username="9100000002", reward__trigger="social").count(), 1)

        self.client.credentials(HTTP_AUTHORIZATION=customer_token)
        status = self.client.get(f"/api/me/shop/{self.code}/").data["social_follow_claim"]["status"]
        self.assertEqual(status, "approved")
        self.assertEqual(self.client.post(f"/api/b/{self.code}/social-follow/claim/", {}, format="json").status_code, 400)

    def test_logout_invalidates_the_token(self):
        self.as_owner()
        self.assertEqual(self.client.post("/api/auth/logout/").status_code, 204)
        self.assertEqual(self.client.get("/api/owner/businesses/").status_code, 401)

    def test_staff_list_endpoint(self):
        self.as_owner()
        self.client.post(f"/api/b/{self.code}/staff/", {"name": "Ravi", "mobile": "9100000090", "password": "secret1"}, format="json")
        self.assertEqual(self.client.get(f"/api/b/{self.code}/staff/").data, [{"mobile": "9100000090", "name": "Ravi"}])
