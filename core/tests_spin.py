from datetime import date
from unittest.mock import patch

from rest_framework.test import APITestCase

from .models import (Business, CustomerProfile, Notification, Program, PurchaseEntry, Reward, RewardGrant,
                     SpinRecord, SpinWheel, Task, User)


class SpinWinTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user("9100001001", "secret1", role="owner")
        self.customer = User.objects.create_user("9100001002", "secret1", role="customer", first_name="Asha")
        self.other_owner = User.objects.create_user("9100001003", "secret1", role="owner")
        self.business = Business.objects.create(owner=self.owner, name="Spin Cafe")
        self.profile = CustomerProfile.objects.create(user=self.customer, business=self.business)
        self.owner_token = self._token(self.owner)
        self.customer_token = self._token(self.customer)
        self.segments = [
            {"label": "10% off", "reward_type": "percent_off", "probability": 60, "color": "#5e35b1",
             "icon": "🎁", "image_url": "https://example.com/prize.png",
             "value": "10", "expiry_days": 14, "minimum_order": "200",
             "product_restrictions": "Hot drinks", "terms": "One per visit"},
            {"label": "Free coffee", "reward_type": "free_item", "probability": 40, "color": "#e3e6ee", "icon": "🎁"},
        ]

    def _token(self, user):
        from rest_framework.authtoken.models import Token
        return Token.objects.create(user=user).key

    def _as(self, token):
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token)

    def _wheel(self, **overrides):
        data = {"name": "Daily spin", "audience": "all", "weekdays": [], "spins_per_day": 1,
                "active": True, "segments": self.segments}
        data.update(overrides)
        self._as(self.owner_token)
        response = self.client.post(f"/api/b/{self.business.shop_code}/spin-wheels/", data, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_owner_can_create_edit_and_deactivate_a_wheel_and_probabilities_must_total_100(self):
        self._as(self.owner_token)
        invalid = self.client.post(f"/api/b/{self.business.shop_code}/spin-wheels/",
                                   {"name": "Bad", "segments": [{**self.segments[0], "probability": 50},
                                                                  {**self.segments[1], "probability": 40}]},
                                   format="json")
        self.assertEqual(invalid.status_code, 400)
        wheel = self._wheel()
        self.assertEqual(len(wheel["segments"]), 2)
        self.assertEqual(sum(s["probability"] for s in wheel["segments"]), 100)
        self.assertEqual(wheel["segments"][0]["image_url"], "https://example.com/prize.png")
        self.assertEqual(self.client.patch(f"/api/spin-wheels/{wheel['id']}/", {"active": False}, format="json").status_code, 200)
        self.assertFalse(SpinWheel.objects.get(pk=wheel["id"]).active)
        self._as(self._token(self.other_owner))
        self.assertEqual(self.client.get(f"/api/b/{self.business.shop_code}/spin-wheels/").status_code, 404)

    def test_owner_can_delete_a_wheel_without_deleting_spin_history(self):
        wheel = self._wheel()
        wheel_obj = SpinWheel.objects.get(pk=wheel["id"])
        segment = wheel_obj.segments.first()
        record = SpinRecord.objects.create(
            profile=self.profile, business=self.business, wheel=wheel_obj, segment=segment,
            spin_date=date.today(), outcome="won", prize_title=segment.label,
        )

        self._as(self.owner_token)
        response = self.client.delete(f"/api/spin-wheels/{wheel['id']}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(SpinWheel.objects.filter(pk=wheel["id"]).exists())
        record.refresh_from_db()
        self.assertIsNone(record.wheel)
        self.assertIsNone(record.segment)
        self.assertEqual(record.prize_title, segment.label)

    def test_new_audience_wheel_notifies_only_opted_in_customers_without_purchases(self):
        self.profile.marketing_consent = True
        self.profile.save(update_fields=["marketing_consent"])
        returning = User.objects.create_user("9100001004", "secret1", role="customer")
        returning_profile = CustomerProfile.objects.create(user=returning, business=self.business, marketing_consent=True)
        program = Program.objects.create(business=self.business, title="Visits")
        task = Task.objects.create(program=program, title="Visit", type="visit", target=1)
        PurchaseEntry.objects.create(profile=returning_profile, task=task, status="approved")

        self._wheel(audience="new")

        self.assertTrue(Notification.objects.filter(user=self.customer, text__contains="New Spin & Win").exists())
        self.assertFalse(Notification.objects.filter(user=returning, text__contains="New Spin & Win").exists())

    def test_wheel_can_clear_date_and_weekday_schedule(self):
        wheel = self._wheel(start_date="2026-11-23", end_date="2026-11-30", weekdays=[0, 2])
        self._as(self.owner_token)
        response = self.client.patch(f"/api/spin-wheels/{wheel['id']}/",
                                     {"start_date": None, "end_date": None, "weekdays": []},
                                     format="json")
        self.assertEqual(response.status_code, 200, response.data)
        updated = SpinWheel.objects.get(pk=wheel["id"])
        self.assertIsNone(updated.start_date)
        self.assertIsNone(updated.end_date)
        self.assertEqual(updated.weekdays, "")

    def test_only_percentage_off_and_free_item_rewards_are_accepted(self):
        segments = [dict(segment) for segment in self.segments]
        segments[1]["reward_type"] = "gift"
        self._as(self.owner_token)
        response = self.client.post(f"/api/b/{self.business.shop_code}/spin-wheels/",
                                    {"name": "Unsupported reward", "segments": segments}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(SpinWheel.objects.filter(business=self.business).exists())

    def test_bad_segment_image_url_is_treated_as_optional(self):
        segments = [dict(segment) for segment in self.segments]
        segments[0]["image_url"] = "javascript:alert(1)"
        self._as(self.owner_token)
        response = self.client.post(f"/api/b/{self.business.shop_code}/spin-wheels/",
                                    {"name": "Bad image", "segments": segments}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        segment = SpinWheel.objects.get(business=self.business).segments.get(position=0)
        self.assertEqual(segment.image_url, "")

    def test_optional_segment_fields_can_be_left_blank(self):
        segments = [dict(segment) for segment in self.segments]
        for key in ("value", "expiry_days", "minimum_order", "image_url", "product_restrictions", "terms"):
            segments[0][key] = ""
        self._as(self.owner_token)
        response = self.client.post(f"/api/b/{self.business.shop_code}/spin-wheels/",
                                    {"name": "Optional fields", "segments": segments}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        segment = SpinWheel.objects.get(business=self.business).segments.get(position=0)
        self.assertEqual(segment.value, 0)
        self.assertEqual(segment.expiry_days, 30)
        self.assertEqual(segment.minimum_order, 0)
        self.assertEqual(segment.image_url, "")

    def test_unset_segment_image_values_are_treated_as_optional(self):
        segments = [dict(segment) for segment in self.segments]
        for value in (None, "null", "undefined"):
            segments[0]["image_url"] = value
            self._as(self.owner_token)
            response = self.client.post(f"/api/b/{self.business.shop_code}/spin-wheels/",
                                        {"name": f"Optional image {value}", "segments": segments},
                                        format="json")
            self.assertEqual(response.status_code, 201, response.data)
            SpinWheel.objects.filter(business=self.business).delete()

    def test_daily_wheel_selects_customer_group_and_weekday_campaign(self):
        monday = date(2026, 11, 23)
        self._as(self.owner_token)
        new_wheel = self._wheel(name="New Monday", audience="new", weekdays=[0], start_date="2026-11-23",
                                end_date="2026-11-23")
        returning_wheel = self._wheel(name="Returning Monday", audience="returning", weekdays=[0])
        with patch("core.spin_views.timezone.localdate", return_value=monday):
            self._as(self.customer_token)
            self.assertEqual(self.client.get(f"/api/b/{self.business.shop_code}/spin/").data["wheel"]["id"],
                             new_wheel["id"])
            program = Program.objects.create(business=self.business, title="Loyalty")
            task = Task.objects.create(program=program, title="Visit", type="visit", target=5)
            PurchaseEntry.objects.create(profile=self.profile, task=task, status="approved")
            self.assertEqual(self.client.get(f"/api/b/{self.business.shop_code}/spin/").data["wheel"]["id"],
                             returning_wheel["id"])

    def test_winning_spin_adds_coupon_to_wallet_and_enforces_daily_limit(self):
        wheel = self._wheel()
        self._as(self.customer_token)
        with patch("core.spin_views.secrets.randbelow", return_value=0):
            response = self.client.post(f"/api/b/{self.business.shop_code}/spin/", {}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["outcome"], "won")
        grant = RewardGrant.objects.get(code=response.data["grant"]["code"])
        self.assertEqual(grant.profile, self.profile)
        self.assertEqual(grant.reward.trigger, "spin")
        self.assertEqual(grant.reward.type, "percent_off")
        self.assertEqual(grant.reward.min_order_amount, 200)
        self.assertEqual(grant.reward.product_restrictions, "Hot drinks")
        self.assertIn("Minimum order: INR 200.00.", grant.reward.terms)
        self.assertEqual(self.client.get(f"/api/b/{self.business.shop_code}/spin/").data["history"][0]["code"],
                         grant.code)
        limited = self.client.post(f"/api/b/{self.business.shop_code}/spin/", {}, format="json")
        self.assertEqual(limited.status_code, 400)
        self.assertEqual(SpinRecord.objects.filter(profile=self.profile).count(), 1)

        self._as(self.owner_token)
        redeem = self.client.post("/api/rewards/redeem/", {"code": grant.code}, format="json")
        self.assertEqual(redeem.status_code, 200, redeem.data)
        wheel_stats = self.client.get(f"/api/b/{self.business.shop_code}/spin-wheels/").data[0]["analytics"]
        self.assertEqual(wheel_stats["spins"], 1)
        self.assertEqual(wheel_stats["wins"], 1)
        self.assertEqual(wheel_stats["redeemed"], 1)

    def test_try_again_is_recorded_without_a_reward_coupon(self):
        wheel = self._wheel(spins_per_day=2)
        segment = SpinWheel.objects.get(pk=wheel["id"]).segments.get(position=1)
        segment.reward_type, segment.label = "empty", "Try again"
        segment.save(update_fields=["reward_type", "label"])
        self._as(self.customer_token)
        with patch("core.spin_views.secrets.randbelow", return_value=99):
            response = self.client.post(f"/api/b/{self.business.shop_code}/spin/", {}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["outcome"], "try_again")
        self.assertIsNone(response.data["grant"])
        self.assertFalse(Reward.objects.filter(trigger="spin").exists())
        self.assertEqual(SpinRecord.objects.get(profile=self.profile).prize_title, "Try again")

    def test_customer_cannot_spin_another_customers_wheel_or_a_paused_business(self):
        wheel = self._wheel()
        outsider = User.objects.create_user("9100001004", "secret1", role="customer")
        self._as(self._token(outsider))
        self.assertEqual(self.client.get(f"/api/b/{self.business.shop_code}/spin/").status_code, 404)
        self._as(self.customer_token)
        self.business.status = "paused"
        self.business.save(update_fields=["status"])
        self.assertEqual(self.client.post(f"/api/b/{self.business.shop_code}/spin/", {}, format="json").status_code, 400)

    def test_spin_qr_is_a_png(self):
        response = self.client.get(f"/api/b/{self.business.shop_code}/spin-qr.png")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
