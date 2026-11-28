"""v2.5: coin bonuses (welcome / visit / refer-and-earn), coin ledger + cancel, offer titles/end dates, brand payload."""
from io import BytesIO
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image

from .models import (CoinAccount, CoinProgram, CoinTransaction, CoinRedemption, CoinReward, CustomerProfile,
                    ShopOffer, TaskProgress, PurchaseEntry)
from .tests_growth import GrowthBase


class CoinBonusTests(GrowthBase):
    def setUp(self):
        super().setUp()
        CoinProgram.objects.create(business=self.biz, enabled=True, spend_per_coin=10, daily_cap=1000,
                                   welcome_bonus=20, visit_coins=5, referrer_bonus=50, friend_bonus=25)

    def balance(self, mobile):
        p = CustomerProfile.objects.get(user__username=mobile, business=self.biz)
        a = CoinAccount.objects.filter(profile=p).first()
        return a.balance if a else 0

    def test_welcome_bonus_and_visit_coins_once(self):
        c = self.customer("9100000020")
        self.buy(c)
        self.assertEqual(self.balance("9100000020"), 25)  # 20 welcome + 5 visit
        self.buy(c)
        self.assertEqual(self.balance("9100000020"), 30)  # welcome is exactly once

    def test_undo_removes_visit_coins_but_not_welcome(self):
        c = self.customer("9100000021")
        eid = self.buy(c)
        self.as_owner()
        self.assertEqual(self.client.post(f"/api/entries/{eid}/reverse/").status_code, 200)
        self.assertEqual(self.balance("9100000021"), 20)
        self.buy(c)  # re-buying does not pay the welcome bonus twice
        self.assertEqual(self.balance("9100000021"), 25)

    def test_referral_pays_both_sides_on_first_purchase_only(self):
        inviter = self.customer("9100000022")
        self.client.credentials(HTTP_AUTHORIZATION=inviter)
        code = self.client.get(f"/api/me/shop/{self.code}/").data["referral_code"]
        friend = self.customer("9100000023", ref=code)
        self.assertEqual(self.balance("9100000022"), 0)  # joining alone pays nothing
        self.buy(friend)
        self.assertEqual(self.balance("9100000022"), 50)
        self.assertEqual(self.balance("9100000023"), 20 + 25 + 5)
        self.buy(friend)
        self.assertEqual(self.balance("9100000022"), 50)
        self.client.credentials(HTTP_AUTHORIZATION=inviter)
        ref = self.client.get(f"/api/me/shop/{self.code}/").data["referral"]
        self.assertEqual((ref["joined"], ref["purchased"], ref["coins_earned"]), (1, 1, 50))
        self.assertEqual(ref["friends"][0]["status"], "purchased")

    def test_self_referral_and_disabled_program_pay_nothing(self):
        CoinProgram.objects.filter(business=self.biz).update(enabled=False)
        c = self.customer("9100000024")
        self.buy(c)
        self.assertEqual(self.balance("9100000024"), 0)

    def test_owner_settings_validate_and_report_stats(self):
        self.as_owner()
        url = f"/api/b/{self.code}/coin-program/"
        self.assertEqual(self.client.put(url, {"welcome_bonus": -1}, format="json").status_code, 400)
        self.assertEqual(self.client.put(url, {"referrer_bonus": "x"}, format="json").status_code, 400)
        r = self.client.put(url, {"welcome_bonus": 30, "friend_bonus": 10}, format="json")
        self.assertEqual((r.status_code, r.data["welcome_bonus"], r.data["friend_bonus"], r.data["referrer_bonus"]), (200, 30, 10, 50))
        c = self.customer("9100000025")
        self.buy(c)
        self.as_owner()
        self.assertEqual(self.client.get(url).data["stats"]["outstanding"], 35)

    def test_ledger_next_reward_and_cancel_returns_coins(self):
        reward = CoinReward.objects.create(business=self.biz, title="Free cookie", cost=20)
        CoinReward.objects.create(business=self.biz, title="Free meal", cost=100)
        c = self.customer("9100000026")
        self.buy(c)  # 25 coins
        self.client.credentials(HTTP_AUTHORIZATION=c)
        st = self.client.get(f"/api/me/shop/{self.code}/").data["coins"]
        self.assertEqual((st["balance"], st["next_reward"]["title"], st["next_reward"]["needed"]), (25, "Free meal", 75))
        self.assertEqual({h["reason"] for h in st["history"] if h["kind"] == "bonus"}, {"welcome"})
        r = self.client.post(f"/api/coin-rewards/{reward.pk}/request/", {}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.client.post(f"/api/coin-redemptions/{r.data['id']}/cancel/").data["balance"], 25)
        self.assertEqual(self.client.post(f"/api/coin-redemptions/{r.data['id']}/cancel/").status_code, 400)
        self.assertEqual(CoinRedemption.objects.get(pk=r.data["id"]).status, "declined")

    def test_cancel_is_private_to_the_requesting_customer(self):
        reward = CoinReward.objects.create(business=self.biz, title="Free cookie", cost=5)
        c = self.customer("9100000027")
        self.buy(c)
        self.client.credentials(HTTP_AUTHORIZATION=c)
        rid = self.client.post(f"/api/coin-rewards/{reward.pk}/request/", {}, format="json").data["id"]
        self.customer("9100000028")
        self.assertEqual(self.client.post(f"/api/coin-redemptions/{rid}/cancel/").status_code, 404)


class CoinPurchaseCollectionTests(GrowthBase):
    def setUp(self):
        super().setUp()
        CoinProgram.objects.create(business=self.biz, enabled=True, spend_per_coin=10, daily_cap=1000)

    def test_reward_task_purchase_also_requires_bill_when_coin_collection_is_enabled(self):
        customer = self.customer("9100000029")
        self.client.credentials(HTTP_AUTHORIZATION=customer)
        response = self.client.post(
            "/api/entries/", {"task": self.visit_task.id, "value": 1}, format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data[0], "Please attach the bill photo.")

    @staticmethod
    def bill():
        content = BytesIO()
        Image.new("RGB", (4, 4), "white").save(content, format="PNG")
        return SimpleUploadedFile("receipt.png", content.getvalue(), content_type="image/png")

    def submit(self, customer, amount="235.50"):
        self.client.credentials(HTTP_AUTHORIZATION=customer)
        return self.client.post(f"/api/b/{self.code}/coin-purchases/", {
            "amount": amount, "bill_photo": self.bill(),
        }, format="multipart")

    def test_bill_purchase_is_reviewed_and_coins_are_credited_without_task_progress(self):
        customer = self.customer("9100000030")
        profile = CustomerProfile.objects.get(user__username="9100000030", business=self.biz)
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        with override_settings(MEDIA_ROOT=media.name):
            submitted = self.submit(customer)
            self.assertEqual(submitted.status_code, 201, submitted.data)
            self.assertIsNone(submitted.data["task"])
            self.assertEqual((submitted.data["task_type"], submitted.data["task_title"], submitted.data["status"]),
                             ("coin_only", "Coin purchase", "pending"))
            self.assertTrue(submitted.data["bill_url"])
            self.assertFalse(TaskProgress.objects.filter(profile=profile).exists())

            self.as_owner()
            pending = self.client.get("/api/owner/pending/")
            self.assertEqual((pending.status_code, pending.data[0]["id"]), (200, submitted.data["id"]))
            self.assertEqual(pending.data[0]["task_type"], "coin_only")
            approved = self.client.post(f"/api/entries/{submitted.data['id']}/review/", {"action": "approve"})
            self.assertEqual(approved.status_code, 200, approved.data)
            account = CoinAccount.objects.get(profile=profile)
            self.assertEqual(account.balance, 23)

            reversed_entry = self.client.post(f"/api/entries/{submitted.data['id']}/reverse/")
            self.assertEqual(reversed_entry.status_code, 200, reversed_entry.data)
            account.refresh_from_db()
            self.assertEqual(account.balance, 0)

    def test_bill_is_required_and_coin_program_must_be_enabled(self):
        customer = self.customer("9100000031")
        self.client.credentials(HTTP_AUTHORIZATION=customer)
        missing_bill = self.client.post(f"/api/b/{self.code}/coin-purchases/", {"amount": "40.00"}, format="multipart")
        self.assertEqual(missing_bill.status_code, 400)
        CoinProgram.objects.filter(business=self.biz).update(enabled=False)
        disabled = self.submit(customer, "40.00")
        self.assertEqual(disabled.status_code, 400)
        self.assertFalse(PurchaseEntry.objects.filter(profile__user__username="9100000031").exists())

    def test_declined_bill_does_not_award_coins(self):
        customer = self.customer("9100000032")
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        with override_settings(MEDIA_ROOT=media.name):
            submitted = self.submit(customer, "99.00")
            self.assertEqual(submitted.status_code, 201, submitted.data)
            self.as_owner()
            rejected = self.client.post(f"/api/entries/{submitted.data['id']}/review/", {"action": "reject"})
            self.assertEqual(rejected.status_code, 200, rejected.data)
            self.assertFalse(CoinTransaction.objects.filter(purchase_entry_id=submitted.data["id"]).exists())


class OfferAndBrandTests(GrowthBase):
    def _offer(self, **extra):
        self.as_owner()
        import json
        body = {"offer_type": "percent_off", "value": "20", "items": json.dumps([{"name": "Chai", "price": "20"}])}
        body.update(extra)
        return self.client.post(f"/api/b/{self.code}/offers/", body)

    def test_offer_title_end_date_and_expiry_hidden_from_public(self):
        today = timezone.localdate()
        r = self._offer(title="Weekend special", ends_on=(today + timedelta(days=3)).isoformat())
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data["title"], r.data["expired"]), ("Weekend special", False))
        self.assertEqual(len(self.client.get(f"/api/b/{self.code}/").data["offers"]), 1)
        ShopOffer.objects.update(ends_on=today - timedelta(days=1))
        self.assertEqual(self.client.get(f"/api/b/{self.code}/").data["offers"], [])
        self.as_owner()
        self.assertTrue(self.client.get(f"/api/b/{self.code}/offers/").data[0]["expired"])

    def test_past_end_date_rejected_and_extend_via_patch(self):
        self.assertEqual(self._offer(ends_on="2020-01-01").status_code, 400)
        r = self._offer()
        new = (timezone.localdate() + timedelta(days=9)).isoformat()
        p = self.client.patch(f"/api/b/{self.code}/offers/{r.data['id']}/", {"ends_on": new}, format="json")
        self.assertEqual((p.status_code, p.data["ends_on"]), (200, new))
        self.assertEqual(self.client.patch(f"/api/b/{self.code}/offers/{r.data['id']}/", {}, format="json").status_code, 400)

    def test_public_payload_carries_brand_and_coin_rules(self):
        d = self.client.get(f"/api/b/{self.code}/").data
        self.assertEqual(d["brand"]["name"], "OFFLet")
        self.assertTrue(d["brand"]["domain"])
        self.assertIsNone(d["coins"])
        CoinProgram.objects.create(business=self.biz, enabled=True, welcome_bonus=10)
        self.assertEqual(self.client.get(f"/api/b/{self.code}/").data["coins"]["welcome_bonus"], 10)
