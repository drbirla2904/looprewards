from datetime import timedelta
from io import BytesIO
import os
import tempfile
from unittest.mock import patch
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient, APITestCase
from .models import (Business, CustomerProfile, Program, PurchaseEntry, Reward, RewardGrant, Task,
                     TaskProgress, User)


class FlowTest(APITestCase):
    def _login(self, mobile, role):
        r = self.client.post("/api/auth/register/", {"mobile": mobile, "password": "secret1", "role": role, "name": "N", "accepted": True})
        self.client.credentials(HTTP_AUTHORIZATION="Token " + r.data["token"])

    def test_full_loop(self):
        self._login("9999999991", "owner")
        code = self.client.post("/api/businesses/", {"name": "Raju Pizza", "pay_upi_id": "raju@upi"}).data["shop_code"]
        self.client.post(f"/api/b/{code}/programs/", {"title": "Loyalty", "tasks": [
            {"title": "5 pizzas", "type": "count", "target": 5,
             "rewards": [{"title": "Free pizza", "type": "free_item"}]}]}, format="json")
        task_id = self.client.get(f"/api/b/{code}/").data["programs"][0]["tasks"][0]["id"]
        owner_token = self.client._credentials["HTTP_AUTHORIZATION"]

        self._login("9999999992", "customer")
        self.client.post(f"/api/b/{code}/join/")
        r = self.client.post("/api/entries/", {"task": task_id, "value": 5})
        self.assertEqual(r.status_code, 201)
        # cooldown blocks immediate second entry
        self.assertEqual(self.client.post("/api/entries/", {"task": task_id, "value": 1}).status_code, 400)
        cust_token = self.client._credentials["HTTP_AUTHORIZATION"]

        self.client.credentials(HTTP_AUTHORIZATION=owner_token)
        self.assertEqual(len(self.client.get("/api/owner/pending/").data), 1)
        self.client.post(f"/api/entries/{r.data['id']}/review/", {"action": "approve"})

        self.client.credentials(HTTP_AUTHORIZATION=cust_token)
        reward = self.client.get("/api/me/shops/").data[0]["rewards"][0]
        self.client.credentials(HTTP_AUTHORIZATION=owner_token)
        self.assertEqual(self.client.post("/api/rewards/redeem/", {"code": reward["code"], "shop_code": code}).status_code, 200)
        self.assertEqual(self.client.post("/api/rewards/redeem/", {"code": reward["code"], "shop_code": code}).status_code, 400)

    def test_customer_can_update_profile_and_change_password(self):
        user = User.objects.create_user(
            username="9000000109", password="secret1", role="customer", first_name="Old Name"
        )
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get("/api/me/profile/").data["name"], "Old Name")
        response = self.client.patch("/api/me/profile/", {"name": "  New Name  "}, format="json")
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.first_name, "New Name")
        self.assertTrue(user.check_password("secret1"))
        changed = self.client.post(
            "/api/auth/change-password/", {"old": "secret1", "new": "fresh-pass"}
        )
        self.assertEqual(changed.status_code, 200, changed.data)
        user.refresh_from_db()
        self.assertTrue(user.check_password("fresh-pass"))


class CustomerProfilePhotoTest(APITestCase):
    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        media_settings = override_settings(MEDIA_ROOT=self.media_dir.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        self.addCleanup(self.media_dir.cleanup)
        self.owner = User.objects.create_user("9000000101", "secret1", role="owner")
        self.business = Business.objects.create(owner=self.owner, name="Photo Check Cafe")
        program = Program.objects.create(business=self.business, title="Visit rewards")
        self.task = Task.objects.create(program=program, title="Visit", type="visit", target=5)
        self.customer = User.objects.create_user("9000000102", "secret1", role="customer", first_name="Asha Patel")
        self.profile = CustomerProfile.objects.create(user=self.customer, business=self.business)
        PurchaseEntry.objects.create(profile=self.profile, task=self.task, value=1)

    def _photo(self):
        image = BytesIO()
        Image.new("RGB", (32, 32), color="green").save(image, format="PNG")
        return SimpleUploadedFile("customer.png", image.getvalue(), content_type="image/png")

    def test_customer_can_add_photo_and_shop_owner_sees_it_on_pending_purchase(self):
        self.client.force_authenticate(self.customer)
        response = self.client.patch("/api/me/profile-image/", {"profile_image": self._photo()}, format="multipart")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["profile_image_url"].startswith("/media/profiles/"))

        self.client.force_authenticate(self.owner)
        pending = self.client.get("/api/owner/pending/")
        self.assertEqual(pending.status_code, 200)
        self.assertEqual(pending.data[0]["customer_image_url"], response.data["profile_image_url"])

        self.client.force_authenticate(self.customer)
        removed = self.client.delete("/api/me/profile-image/")
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(removed.data["profile_image_url"], "")

    def test_profile_photo_must_be_an_image_within_size_limit(self):
        self.client.force_authenticate(self.customer)
        invalid = self.client.patch(
            "/api/me/profile-image/",
            {"profile_image": SimpleUploadedFile("not-image.png", b"not an image", content_type="image/png")},
            format="multipart",
        )
        self.assertEqual(invalid.status_code, 400)
        large_image = BytesIO()
        Image.frombytes("RGB", (1400, 1400), os.urandom(1400 * 1400 * 3)).save(
            large_image, format="PNG", compress_level=0
        )
        self.assertGreater(len(large_image.getvalue()), 5 * 1024 * 1024)
        too_large = self.client.patch(
            "/api/me/profile-image/",
            {"profile_image": SimpleUploadedFile("large.png", large_image.getvalue(), content_type="image/png")},
            format="multipart",
        )
        self.assertEqual(too_large.status_code, 400)

    def test_all_account_roles_can_upload_and_retrieve_profile_photos(self):
        users = [
            self.customer,
            self.owner,
            User.objects.create_user("9000000103", "secret1", role="staff"),
            User.objects.create_user("9000000104", "secret1", role="vendor"),
        ]
        for user in users:
            with self.subTest(role=user.role):
                self.client.force_authenticate(user)
                uploaded = self.client.patch(
                    "/api/me/profile-image/",
                    {"profile_image": self._photo()},
                    format="multipart",
                )
                self.assertEqual(uploaded.status_code, 200, uploaded.data)
                self.assertTrue(uploaded.data["profile_image_url"].startswith("/media/profiles/"))
                fetched = self.client.get("/api/me/profile-image/")
                self.assertEqual(fetched.data["profile_image_url"], uploaded.data["profile_image_url"])


class CustomerShopVisibilityTest(APITestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="9000000110", password="secret1", role="customer", first_name="Customer"
        )
        self.owner = User.objects.create_user(
            username="9000000111", password="secret1", role="owner", first_name="Owner"
        )
        self.business = Business.objects.create(owner=self.owner, name="History Cafe")
        self.profile = CustomerProfile.objects.create(user=self.customer, business=self.business)
        program = Program.objects.create(business=self.business, title="Visits")
        self.task = Task.objects.create(program=program, title="Visit", type="visit", target=5)
        reward = Reward.objects.create(task=self.task, title="Free tea", type="free_item")
        self.entry = PurchaseEntry.objects.create(profile=self.profile, task=self.task, value=1)
        self.progress = TaskProgress.objects.create(profile=self.profile, task=self.task, current_value=1)
        self.grant = RewardGrant.objects.create(
            profile=self.profile, reward=reward, expires_at=timezone.now() + timedelta(days=5)
        )
        self.client.force_authenticate(self.customer)

    def test_customer_hides_and_restores_past_history_without_erasing_shop_records(self):
        path = f"/api/me/shops/{self.business.shop_code}/history/"
        cleared = self.client.delete(path)
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(self.client.get("/api/me/shops/").data[0]["entries"], [])
        self.assertTrue(PurchaseEntry.objects.filter(pk=self.entry.pk).exists())
        self.assertTrue(TaskProgress.objects.filter(pk=self.progress.pk).exists())
        self.assertTrue(RewardGrant.objects.filter(pk=self.grant.pk).exists())

        recent_entry = PurchaseEntry.objects.create(profile=self.profile, task=self.task, value=1)
        visible = self.client.get("/api/me/shops/").data[0]["entries"]
        self.assertEqual([entry["id"] for entry in visible], [recent_entry.pk])

        restored = self.client.post(path, {}, format="json")
        self.assertEqual(restored.status_code, 200)
        visible_ids = {entry["id"] for entry in self.client.get("/api/me/shops/").data[0]["entries"]}
        self.assertEqual(visible_ids, {self.entry.pk, recent_entry.pk})

    def test_customer_hides_and_restores_shop_without_losing_progress_or_rewards(self):
        path = f"/api/me/shops/{self.business.shop_code}/"
        hidden = self.client.delete(path)
        self.assertEqual(hidden.status_code, 204)
        self.assertEqual(self.client.get("/api/me/shops/").data, [])
        hidden_shops = self.client.get("/api/me/shops/hidden/")
        self.assertEqual(hidden_shops.status_code, 200)
        self.assertEqual(hidden_shops.data[0]["business__name"], self.business.name)
        self.assertTrue(PurchaseEntry.objects.filter(pk=self.entry.pk).exists())
        self.assertTrue(TaskProgress.objects.filter(pk=self.progress.pk).exists())
        self.assertTrue(RewardGrant.objects.filter(pk=self.grant.pk).exists())

        restored = self.client.post(path + "restore/", {}, format="json")
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(len(self.client.get("/api/me/shops/").data), 1)
        self.assertEqual(self.client.get("/api/me/shops/hidden/").data, [])

    def test_joining_hidden_live_shop_restores_it(self):
        self.profile.hidden_from_customer = True
        self.profile.save(update_fields=["hidden_from_customer"])
        response = self.client.post(f"/api/b/{self.business.shop_code}/join/")
        self.assertEqual(response.status_code, 201)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.hidden_from_customer)

    def test_shop_visibility_controls_are_customer_only(self):
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.delete(f"/api/me/shops/{self.business.shop_code}/").status_code, 403)
        self.assertEqual(self.client.get("/api/me/shops/hidden/").status_code, 403)


class PurchaseUndoTest(APITestCase):
    def setUp(self):
        from .models import Business, CustomerProfile, Program, Task, get_sub

        self.owner = User.objects.create_user("9000000040", "secret1", role="owner")
        self.business = Business.objects.create(owner=self.owner, name="Undo Test Cafe")
        get_sub(self.owner)
        program = Program.objects.create(business=self.business, title="Visit rewards")
        self.task = Task.objects.create(program=program, title="Five visits", type="visit", target=5)
        self.customer = User.objects.create_user("9000000041", "secret1")
        self.profile = CustomerProfile.objects.create(user=self.customer, business=self.business)
        self.entry = PurchaseEntry.objects.create(profile=self.profile, task=self.task, value=1)
        self.client.force_authenticate(user=self.owner)

    def test_approved_purchase_can_be_undone_within_five_seconds(self):
        reviewed_at = timezone.now()
        with patch("core.services.timezone.now", return_value=reviewed_at):
            approved = self.client.post(f"/api/entries/{self.entry.pk}/review/", {"action": "approve"}, format="json")
        self.assertEqual(approved.data["status"], "approved")
        self.assertIsNotNone(approved.data["reviewed_at"])

        with patch("core.services.timezone.now", return_value=reviewed_at + timedelta(seconds=5)):
            undone = self.client.post(f"/api/entries/{self.entry.pk}/reverse/", format="json")
        self.assertEqual((undone.status_code, undone.data["status"]), (200, "reversed"))

    def test_approved_purchase_cannot_be_undone_after_five_seconds(self):
        reviewed_at = timezone.now()
        with patch("core.services.timezone.now", return_value=reviewed_at):
            self.client.post(f"/api/entries/{self.entry.pk}/review/", {"action": "approve"}, format="json")

        with patch("core.services.timezone.now", return_value=reviewed_at + timedelta(seconds=5, microseconds=1)):
            expired = self.client.post(f"/api/entries/{self.entry.pk}/reverse/", format="json")
        self.assertEqual(expired.status_code, 400)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, "approved")

    def test_purchase_cannot_be_undone_after_its_reward_is_redeemed(self):
        from .models import Reward

        self.task.target = 1
        self.task.save()
        self.entry.value = 1
        self.entry.save()
        Reward.objects.create(task=self.task, title="Free coffee", type="free_item")
        self.client.force_authenticate(user=self.owner)
        self.client.post(f"/api/entries/{self.entry.pk}/review/", {"action": "approve"}, format="json")
        grant = self.profile.grants.get()
        self.assertEqual(self.client.post("/api/rewards/redeem/", {"code": grant.code, "shop_code": self.business.shop_code}, format="json").status_code, 200)

        undone = self.client.post(f"/api/entries/{self.entry.pk}/reverse/", format="json")
        self.assertEqual(undone.status_code, 400)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, "approved")

    def test_undo_revokes_reward_unlocked_by_purchase(self):
        from .models import Reward

        self.task.target = 1
        self.task.save()
        Reward.objects.create(task=self.task, title="Free coffee", type="free_item")
        reviewed_at = timezone.now()
        with patch("core.services.timezone.now", return_value=reviewed_at):
            self.client.post(f"/api/entries/{self.entry.pk}/review/", {"action": "approve"}, format="json")
        grant = self.profile.grants.get()

        with patch("core.services.timezone.now", return_value=reviewed_at + timedelta(seconds=1)):
            undone = self.client.post(f"/api/entries/{self.entry.pk}/reverse/", format="json")
        self.assertEqual(undone.status_code, 200)
        grant.refresh_from_db()
        self.assertEqual(grant.status, "revoked")
        self.assertTrue(self.customer.notifications.filter(text__contains="approval was undone").exists())

    def test_undo_is_blocked_after_a_newer_purchase_was_approved(self):
        from .models import PurchaseEntry

        reviewed_at = timezone.now()
        with patch("core.services.timezone.now", return_value=reviewed_at):
            self.client.post(f"/api/entries/{self.entry.pk}/review/", {"action": "approve"}, format="json")
        newer = PurchaseEntry.objects.create(profile=self.profile, task=self.task, value=1)
        with patch("core.services.timezone.now", return_value=reviewed_at + timedelta(seconds=1)):
            self.client.post(f"/api/entries/{newer.pk}/review/", {"action": "approve"}, format="json")
        with patch("core.services.timezone.now", return_value=reviewed_at + timedelta(seconds=2)):
            response = self.client.post(f"/api/entries/{self.entry.pk}/reverse/", format="json")

        self.assertEqual(response.status_code, 400)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, "approved")

    def test_review_requires_an_explicit_action(self):
        response = self.client.post(f"/api/entries/{self.entry.pk}/review/", {"action": "later"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, "pending")

    def test_purchase_rejects_invalid_amounts_and_fractional_counts(self):
        self.client.force_authenticate(user=self.customer)
        self.task.type = "amount"
        self.task.save()
        invalid_amount = self.client.post("/api/entries/", {"task": self.task.pk, "value": "not-money"}, format="json")
        self.assertEqual(invalid_amount.status_code, 400)

        self.task.type = "count"
        self.task.save()
        fractional_count = self.client.post("/api/entries/", {"task": self.task.pk, "value": "1.5"}, format="json")
        self.assertEqual(fractional_count.status_code, 400)


import hashlib, hmac, json
from django.conf import settings
from django.test import override_settings
from .models import Donation, Payment, User, get_sub
from .billing import mark_paid


@override_settings(RAZORPAY_WEBHOOK_SECRET="whsec")
class BillingTest(APITestCase):
    def test_subscription_prices_are_99_monthly_and_999_yearly(self):
        owner = User.objects.create_user("9999999942", "secret1", role="owner")
        self.client.force_authenticate(user=owner)
        billing = self.client.get("/api/billing/").data
        public = self.client.get("/api/plans/").data
        self.assertEqual(billing["plans"]["monthly"]["amount"], 9900)
        self.assertEqual(billing["plans"]["yearly"]["amount"], 99900)
        self.assertEqual(public["plans"]["monthly"]["amount"], 9900)
        self.assertEqual(public["plans"]["yearly"]["amount"], 99900)

    def test_status_explains_expiry_window_and_available_payment_methods(self):
        owner = User.objects.create_user("9999999933", "secret1", role="owner")
        subscription = get_sub(owner)
        subscription.paid_until = timezone.now() - _td(days=1)
        subscription.save()
        Payment.objects.create(owner=owner, plan="monthly", amount=9900, method="upi",
                               status="pending", utr="123456789012")
        self.client.force_authenticate(user=owner)

        with override_settings(RAZORPAY_KEY_ID="rzp_test_demo", RAZORPAY_KEY_SECRET="secret",
                               RZP_PLAN_IDS={"monthly": "plan_monthly", "yearly": "plan_yearly"},
                               PLATFORM_UPI_ID="loop@upi", GRACE_DAYS=30, RETENTION_MONTHS=12):
            response = self.client.get("/api/billing/")

        self.assertEqual(response.data["state"], "grace")
        self.assertEqual(response.data["grace_days"], 30)
        self.assertEqual(response.data["retention_months"], 12)
        self.assertEqual(response.data["payment_methods"], {"online": True, "upi": True})
        self.assertTrue(response.data["autopay"])
        self.assertFalse(response.data["autorenew"])
        self.assertEqual(response.data["payment_mode"], "test")
        self.assertEqual(response.data["pending_payment"]["plan"], "monthly")
        self.assertGreater(response.data["days_until_data_deletion"], 0)

    def test_status_disables_unconfigured_payment_methods(self):
        owner = User.objects.create_user("9999999934", "secret1", role="owner")
        self.client.force_authenticate(user=owner)
        with override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="", PLATFORM_UPI_ID=""):
            response = self.client.get("/api/billing/")
        self.assertEqual(response.data["payment_methods"], {"online": False, "upi": False})
        with override_settings(RAZORPAY_KEY_ID="rzp_test_demo", RAZORPAY_KEY_SECRET="secret",
                               RZP_PLAN_IDS={"monthly": "plan_monthly", "yearly": ""}):
            incomplete = self.client.get("/api/billing/")
        self.assertTrue(incomplete.data["autopay"])  # missing plan ids no longer hide AutoPay: plans are created on demand
        self.assertEqual(incomplete.data["payment_methods"]["online"], True)

    def test_active_yearly_plan_blocks_monthly_plan_changes(self):
        owner = User.objects.create_user("9999999943", "secret1", role="owner")
        subscription = get_sub(owner)
        subscription.paid_until = timezone.now() + _td(days=100)
        subscription.save(update_fields=["paid_until"])
        Payment.objects.create(owner=owner, plan="yearly", amount=99900, method="gateway", status="paid")
        self.client.force_authenticate(user=owner)

        with override_settings(RAZORPAY_KEY_ID="rzp_test_demo", RAZORPAY_KEY_SECRET="test-secret",
                               PLATFORM_UPI_ID="platform@upi"):
            with patch("core.billing._rzp_post") as gateway:
                status = self.client.get("/api/billing/")
                order = self.client.post("/api/billing/order/", {"plan": "monthly"}, format="json")
                autopay = self.client.post("/api/billing/autopay/", {"plan": "monthly"}, format="json")
                upi = self.client.post("/api/billing/upi/", {"plan": "monthly", "utr": "UPI123456"}, format="multipart")

        self.assertEqual(status.data["active_plan"], "yearly")
        self.assertEqual((order.status_code, autopay.status_code, upi.status_code), (400, 400, 400))
        gateway.assert_not_called()

    def test_one_time_razorpay_order_activates_with_valid_signature(self):
        owner = User.objects.create_user("9999999932", "secret1", role="owner")
        self.client.force_authenticate(user=owner)
        with override_settings(RAZORPAY_KEY_ID="rzp_test_demo", RAZORPAY_KEY_SECRET="test-secret"):
            with patch("core.billing._rzp_post", return_value={"id": "order_test_123"}) as gateway:
                order = self.client.post("/api/billing/order/", {"plan": "monthly"}, format="json")
            self.assertEqual(order.status_code, 200)
            self.assertEqual(order.data, {
                "order_id": "order_test_123", "amount": 9900, "currency": "INR", "key": "rzp_test_demo",
            })
            gateway.assert_called_once_with("orders", {
                "amount": 9900, "currency": "INR", "receipt": gateway.call_args.args[1]["receipt"],
                "notes": {"owner_id": str(owner.pk), "plan": "monthly"},
            })
            payment_id = "pay_test_123"
            signature = hmac.new(b"test-secret",
                f"order_test_123|{payment_id}".encode(), hashlib.sha256).hexdigest()
            invalid = self.client.post("/api/billing/verify/", {
                "razorpay_order_id": "order_test_123", "razorpay_payment_id": payment_id,
                "razorpay_signature": "bad",
            }, format="json")
            self.assertEqual(invalid.status_code, 400)
            self.assertEqual(get_sub(owner).state, "trial")
            verified = self.client.post("/api/billing/verify/", {
                "razorpay_order_id": "order_test_123", "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            }, format="json")

        self.assertEqual(verified.status_code, 200)
        self.assertEqual(get_sub(owner).state, "active")
        payment = Payment.objects.get(owner=owner, order_id="order_test_123")
        self.assertEqual((payment.status, payment.payment_id), ("paid", payment_id))

    def test_customer_donation_order_is_bounded_and_signature_verified(self):
        customer = User.objects.create_user("9999999935", "secret1", role="customer")
        self.client.force_authenticate(user=customer)
        with override_settings(RAZORPAY_KEY_ID="rzp_test_demo", RAZORPAY_KEY_SECRET="test-secret",
                               PLATFORM_UPI_ID=""):
            with patch("core.billing._rzp_post", return_value={"id": "order_donation_123"}) as gateway:
                too_small = self.client.post("/api/billing/donation/order/", {"amount": "0"}, format="json")
                too_precise = self.client.post("/api/billing/donation/order/", {"amount": "1.001"}, format="json")
                order = self.client.post("/api/billing/donation/order/", {"amount": "50.50"}, format="json")
            self.assertEqual(too_small.status_code, 400)
            self.assertEqual(too_precise.status_code, 400)
            self.assertEqual(order.status_code, 201)
            self.assertEqual(order.data, {
                "order_id": "order_donation_123", "amount": 5050, "currency": "INR", "key": "rzp_test_demo",
            })
            gateway.assert_called_once()
            self.assertEqual(gateway.call_args.args[0], "orders")
            self.assertEqual(gateway.call_args.args[1]["amount"], 5050)
            self.assertEqual(gateway.call_args.args[1]["currency"], "INR")
            self.assertEqual(gateway.call_args.args[1]["notes"], {
                "purpose": "voluntary_support", "donor_id": str(customer.pk),
            })

            donation = Donation.objects.get(donor=customer, order_id="order_donation_123")
            payment_id = "pay_donation_123"
            invalid = self.client.post("/api/billing/donation/verify/", {
                "razorpay_order_id": donation.order_id, "razorpay_payment_id": payment_id,
                "razorpay_signature": "invalid",
            }, format="json")
            self.assertEqual(invalid.status_code, 400)
            self.assertEqual(donation.status, "created")
            signature = hmac.new(b"test-secret",
                f"{donation.order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
            verified = self.client.post("/api/billing/donation/verify/", {
                "razorpay_order_id": donation.order_id, "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            }, format="json")
            repeated = self.client.post("/api/billing/donation/verify/", {
                "razorpay_order_id": donation.order_id, "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            }, format="json")

        self.assertEqual(verified.status_code, 200)
        self.assertEqual(repeated.status_code, 200)
        donation.refresh_from_db()
        self.assertEqual((donation.status, donation.payment_id), ("paid", payment_id))

    def test_donation_uses_superadmin_upi_when_razorpay_is_unconfigured(self):
        from urllib.parse import parse_qs, urlparse
        customer = User.objects.create_user("9999999940", "secret1", role="customer")
        self.client.force_authenticate(user=customer)
        with override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="",
                               PLATFORM_UPI_ID="platform@upi", PLATFORM_UPI_NAME="OFFLet Admin"):
            response = self.client.post("/api/billing/donation/order/", {"amount": "50.25"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["method"], "upi")
        self.assertEqual(urlparse(response.data["upi_link"]).scheme, "upi")
        self.assertEqual(parse_qs(urlparse(response.data["upi_link"]).query), {
            "pa": ["platform@upi"], "pn": ["OFFLet Admin"], "am": ["50.25"], "cu": ["INR"],
            "tn": [f"OFFLet donation {customer.pk}"],
        })
        self.assertFalse(Donation.objects.filter(donor=customer).exists())

    def test_donation_falls_back_to_upi_when_razorpay_order_fails(self):
        customer = User.objects.create_user("9999999941", "secret1", role="customer")
        self.client.force_authenticate(user=customer)
        with override_settings(RAZORPAY_KEY_ID="rzp_live_demo", RAZORPAY_KEY_SECRET="secret",
                               PLATFORM_UPI_ID="platform@upi"):
            with patch("core.billing._rzp_post", side_effect=ValidationError("The payment service could not be reached.")):
                response = self.client.post("/api/billing/donation/order/", {"amount": "25"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["method"], "upi")
        self.assertIn("pa=platform%40upi", response.data["upi_link"])

    def test_donation_webhook_marks_matching_payment_paid(self):
        customer = User.objects.create_user("9999999936", "secret1", role="customer")
        donation = Donation.objects.create(donor=customer, amount=2500, order_id="order_donation_webhook")
        body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
            "id": "pay_donation_webhook", "order_id": donation.order_id, "amount": donation.amount,
            "currency": "INR",
        }}}})
        signature = hmac.new(b"whsec", body.encode(), hashlib.sha256).hexdigest()
        response = self.client.generic("POST", "/api/billing/webhook/", body,
                                       content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=signature)
        self.assertEqual(response.status_code, 200)
        donation.refresh_from_db()
        self.assertEqual((donation.status, donation.payment_id), ("paid", "pay_donation_webhook"))

    @patch("core.billing.DonationThrottle.allow_request", return_value=True)
    def test_only_customers_can_create_donations(self, _allow_request):
        owner = User.objects.create_user("9999999937", "secret1", role="owner")
        self.client.force_authenticate(user=owner)
        with override_settings(RAZORPAY_KEY_ID="rzp_test_demo", RAZORPAY_KEY_SECRET="test-secret"):
            response = self.client.post("/api/billing/donation/order/", {"amount": "25"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_upi_requires_screenshot_and_admin_can_view_it_privately(self):
        from django.urls import reverse
        owner = User.objects.create_user("9999999931", "secret1", role="owner")
        self.client.force_authenticate(user=owner)
        with override_settings(PLATFORM_UPI_ID="platform@upi"):
            status = self.client.get("/api/billing/")
            self.assertTrue(status.data["payment_methods"]["upi"])
            self.assertIn("platform%40upi", status.data["upi_links"]["monthly"])
            missing = self.client.post("/api/billing/upi/", {
                "plan": "monthly", "utr": "UPI123456",
            }, format="multipart")
            self.assertEqual(missing.status_code, 400)

            image = Image.new("RGB", (4, 4), "white")
            content = BytesIO()
            image.save(content, format="PNG")
            upload = SimpleUploadedFile("proof.png", content.getvalue(), content_type="image/png")
            submitted = self.client.post("/api/billing/upi/", {
                "plan": "monthly", "utr": "UPI123456", "proof": upload,
            }, format="multipart")
            self.assertEqual(submitted.status_code, 201)
            payment = Payment.objects.get(pk=submitted.data["payment_id"])
            self.addCleanup(payment.proof.delete, save=False)
            self.assertEqual(payment.status, "pending")
            self.assertTrue(str(payment.proof.name).startswith("payment-proofs/"))
            self.assertFalse(str(payment.proof.path).startswith(str(settings.MEDIA_ROOT)))

            staff = User.objects.create_superuser("9999999930", "staff@example.com", "secret1")
            self.client.force_authenticate(user=None)
            self.assertEqual(self.client.get(reverse("admin:core_payment_proof", args=[payment.pk])).status_code, 302)
            self.client.force_login(staff)
            proof_response = self.client.get(reverse("admin:core_payment_proof", args=[payment.pk]))
            self.assertEqual(proof_response.status_code, 200)
            self.assertTrue(proof_response["Cache-Control"].startswith("private, no-store"))
            proof_response.close()
            from django.contrib import admin
            admin.site._registry[Payment].approve(None, Payment.objects.filter(pk=payment.pk))
            payment.refresh_from_db()
            self.assertEqual(payment.status, "paid")
            self.assertEqual(get_sub(owner).state, "active")
            payment.proof.delete(save=False)

    def test_payment_captured_webhook_activates_one_time_order_once(self):
        owner = User.objects.create_user("9999999929", "secret1", role="owner")
        payment = Payment.objects.create(owner=owner, plan="monthly", amount=9900,
            method="gateway", status="created", order_id="order_webhook_1")
        body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
            "id": "pay_webhook_1", "order_id": payment.order_id, "amount": 9900, "currency": "INR",
        }}}}).encode()
        signature = hmac.new(b"whsec", body, hashlib.sha256).hexdigest()
        with override_settings(RAZORPAY_WEBHOOK_SECRET="whsec"):
            for _ in range(2):
                response = self.client.generic("POST", "/api/billing/webhook/", body,
                    HTTP_X_RAZORPAY_SIGNATURE=signature)
                self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, "paid")
        self.assertEqual(get_sub(owner).state, "active")

    def test_autopay_authorization_is_required_to_subscribe(self):
        owner = User.objects.create_user("9999999935", "secret1", role="owner")
        self.client.force_authenticate(user=owner)
        with override_settings(RAZORPAY_KEY_ID="rzp_test_example", RAZORPAY_KEY_SECRET="test-secret",
                               RZP_PLAN_IDS={"monthly": "plan_monthly", "yearly": "plan_yearly"}):
            with patch("core.billing._rzp_post", return_value={"id": "sub_test_123"}) as gateway:
                setup = self.client.post("/api/billing/autopay/", {"plan": "monthly"}, format="json")

            self.assertEqual(setup.status_code, 200)
            self.assertEqual(setup.data, {
                "subscription_id": "sub_test_123",
                "key": "rzp_test_example",
            })
            gateway.assert_called_once()
            self.assertEqual(gateway.call_args.args[0], "subscriptions")
            body = gateway.call_args.args[1]
            self.assertEqual((body["plan_id"], body["total_count"]), ("plan_monthly", 120))
            self.assertEqual(body["customer_notify"], 1)
            self.assertEqual(body["start_at"], int(get_sub(owner).trial_ends.timestamp()))

            subscription = get_sub(owner)
            self.assertEqual(subscription.rzp_sub_id, "sub_test_123")
            self.assertFalse(subscription.rzp_autorenew_active)

            payment_id = "pay_test_123"
            signature = hmac.new(
                b"test-secret",
                f"sub_test_123|{payment_id}".encode(),
                hashlib.sha256,
            ).hexdigest()
            invalid = self.client.post("/api/billing/autopay/verify/", {
                "razorpay_subscription_id": "sub_test_123",
                "razorpay_payment_id": payment_id,
                "razorpay_signature": "invalid",
            }, format="json")
            self.assertEqual(invalid.status_code, 400)
            self.assertFalse(get_sub(owner).rzp_autorenew_active)
            verified = self.client.post("/api/billing/autopay/verify/", {
                "razorpay_subscription_id": "sub_test_123",
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            }, format="json")

        self.assertEqual(verified.status_code, 200)
        self.assertTrue(get_sub(owner).rzp_autorenew_active)
        self.assertEqual(self.client.post("/api/billing/order/", {"plan": "monthly"}).status_code, 400)
        self.assertEqual(self.client.post("/api/billing/upi/", {
            "plan": "monthly", "utr": "123456789012",
        }).status_code, 400)

    def test_webhook_activates_once(self):
        u = User.objects.create_user("9999999993", password="x", role="owner")
        subscription = get_sub(u)
        subscription.rzp_sub_id = "sub_1"
        subscription.rzp_autorenew_active = True
        subscription.save()
        body = json.dumps({"event": "subscription.charged", "payload": {
            "subscription": {"entity": {"id": "sub_1", "plan_id": "plan_monthly"}},
            "payment": {"entity": {"id": "pay_1", "order_id": "order_1", "amount": 9900}},
        }}).encode()
        sig = hmac.new(b"whsec", body, hashlib.sha256).hexdigest()
        with override_settings(RZP_PLAN_IDS={"monthly": "plan_monthly", "yearly": "plan_yearly"}):
            for _ in range(2):  # replayed webhook must not extend twice
                r = self.client.generic("POST", "/api/billing/webhook/", body, HTTP_X_RAZORPAY_SIGNATURE=sig)
                self.assertEqual(r.status_code, 200)
            self.assertEqual(self.client.generic("POST", "/api/billing/webhook/", body, HTTP_X_RAZORPAY_SIGNATURE="bad").status_code, 400)
        s = get_sub(u)
        self.assertEqual(s.state, "active")
        self.assertLess((s.paid_until - s.trial_ends).days, 31)
        payment = Payment.objects.get(owner=u, payment_id="pay_1")
        self.assertEqual(payment.status, "paid")


from datetime import timedelta as _td
from django.core.management import call_command
from .models import ReminderLog


class ReminderTest(APITestCase):
    def test_sent_once(self):
        u = User.objects.create_user("9999999994", password="x", role="owner")
        s = get_sub(u); s.trial_ends = timezone.now() + _td(days=1); s.save()
        call_command("send_reminders"); call_command("send_reminders")
        self.assertEqual(ReminderLog.objects.filter(owner=u).count(), 1)


from .models import Commission, Vendor
from .vendors import reverse


class VendorTest(APITestCase):
    def test_vendor_account_without_application_has_explicit_setup_state(self):
        vendor_user = User.objects.create_user("8888888876", "secret1", role="vendor")
        self.client.force_authenticate(user=vendor_user)
        dashboard = self.client.get("/api/vendor/dashboard/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.data["status"], "not_applied")
        self.assertNotIn("referral_url", dashboard.data)

    def test_referral_link_activates_after_approval_and_tracks_owner_signup(self):
        from django.contrib import admin
        from django.test import RequestFactory

        vendor_user = User.objects.create_user("8888888877", "secret1", role="vendor")
        self.assertIn("vendor", dict(User.ROLES))
        self.client.force_authenticate(user=vendor_user)
        applied = self.client.post("/api/vendor/apply/", {
            "pan": "ABCDE1234F", "upi_id": "vendor@upi",
        }, format="json")
        self.assertEqual(applied.status_code, 201)
        vendor = Vendor.objects.get(user=vendor_user)
        self.assertIsNotNone(vendor.applied_at)
        pending_dashboard = self.client.get("/api/vendor/dashboard/")
        self.assertEqual(pending_dashboard.data["status"], "pending")
        self.assertEqual(pending_dashboard.data["applied_at"], vendor.applied_at)
        self.assertNotIn("referral_url", pending_dashboard.data)

        self.client.force_authenticate(user=None)
        pending_signup = self.client.post("/api/auth/register/", {
            "mobile": "9999999877", "password": "secret1", "role": "owner",
            "name": "Before approval", "accepted": True, "ref": vendor.code,
        })
        self.assertEqual(pending_signup.status_code, 201)
        self.assertIsNone(User.objects.get(username="9999999877").referred_by_id)

        request = RequestFactory().post("/admin/core/vendor/")
        request.user = vendor_user
        from .admin import VendorAdmin
        VendorAdmin(Vendor, admin.site).approve(request, Vendor.objects.filter(pk=vendor.pk))
        vendor.refresh_from_db()
        self.assertEqual(vendor.status, "approved")
        self.assertTrue(Notification.objects.filter(
            user=vendor_user, text__contains="referral link is now active",
        ).exists())
        vendor_user.refresh_from_db()
        self.client.force_authenticate(user=vendor_user)
        dashboard = self.client.get("/api/vendor/dashboard/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.data["referral_url"], f"http://testserver/app/?ref={vendor.code}")
        self.assertEqual(dashboard.data["referred_owner_count"], 0)
        self.assertEqual(dashboard.data["referred_shop_count"], 0)
        self.assertEqual(dashboard.data["commission_paise"], {
            "hold": 0, "payable": 0, "paid": 0, "reversed": 0,
        })
        self.assertGreater(dashboard.data["minimum_payout_paise"], 0)

        self.client.force_authenticate(user=None)
        referred_signup = self.client.post("/api/auth/register/", {
            "mobile": "9999999878", "password": "secret1", "role": "owner",
            "name": "Referred owner", "accepted": True, "ref": vendor.code,
        })
        self.assertEqual(referred_signup.status_code, 201)
        referred_owner = User.objects.get(username="9999999878")
        self.assertEqual(referred_owner.referred_by_id, vendor.id)

        payment = Payment.objects.create(owner=referred_owner, plan="monthly", amount=9900,
                                         method="gateway", status="pending")
        mark_paid(payment.pk)
        commission = Commission.objects.get(payment=payment)
        self.assertEqual(commission.vendor_id, vendor.id)
        self.client.force_authenticate(user=vendor_user)
        dashboard = self.client.get("/api/vendor/dashboard/")
        self.assertEqual(dashboard.data["commission_paise"]["hold"], commission.amount)
        self.assertEqual(len(dashboard.data["recent_commissions"]), 1)

    def test_assisted_registration_sets_the_password_the_partner_chose(self):
        vendor_user = User.objects.create_user("8888888878", "secret1", role="vendor")
        vendor = Vendor.objects.create(user=vendor_user, code="AGENT7", pan="ABCDE1234F",
                                       upi_id="agent@upi", status="approved")
        self.client.force_authenticate(user=vendor_user)
        response = self.client.post("/api/vendor/assist/", {
            "mobile": "9999999879",
            "owner_name": "Assisted owner",
            "name": "Assisted shop",
            "category": "cafe",
            "password": "Chai@2026",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("temp_password", response.data)
        self.assertNotIn("password", response.data)
        owner = User.objects.get(username="9999999879")
        self.assertTrue(owner.check_password("Chai@2026"))
        login = APIClient().post("/api/auth/login/", {"username": "9999999879", "password": "Chai@2026"}, format="json")
        self.assertEqual(login.status_code, 200, login.data)
        self.assertEqual(owner.referred_by_id, vendor.id)
        self.assertTrue(owner.businesses.filter(name="Assisted shop", category="cafe").exists())

    def test_vendor_profile_update_and_deletion_suspend_partner_access(self):
        vendor_user = User.objects.create_user("8888888879", "secret1", role="vendor")
        vendor_user.email = "agent@example.test"
        vendor_user.email_verified = True
        vendor_user.save(update_fields=["email", "email_verified"])
        vendor = Vendor.objects.create(user=vendor_user, code="AGENT8", pan="ABCDE1234F",
                                       upi_id="agent@upi", status="approved")
        self.client.force_authenticate(user=vendor_user)
        response = self.client.patch("/api/vendor/profile/", {
            "name": "Updated Agent", "pan": "FGHIJ5678K", "upi_id": "updated@upi",
        }, format="json")
        self.assertEqual(response.status_code, 200)
        vendor.refresh_from_db()
        vendor_user.refresh_from_db()
        self.assertEqual(vendor_user.first_name, "Updated Agent")
        self.assertEqual(vendor.pan, "FGHIJ5678K")
        self.assertEqual(vendor.upi_id, "updated@upi")
        self.assertEqual(self.client.delete("/api/me/").status_code, 204)
        vendor.refresh_from_db()
        vendor_user.refresh_from_db()
        self.assertEqual(vendor.status, "suspended")
        self.assertEqual(vendor_user.email, "")
        self.assertFalse(vendor_user.email_verified)

    def test_commission_accrual_and_reversal(self):
        vu = User.objects.create_user("8888888888", password="x", role="vendor")
        v = Vendor.objects.create(user=vu, code="ABC123", pan="ABCDE1234F", upi_id="v@upi", status="approved", rate=20)
        u = User.objects.create_user("9999999995", password="x", role="owner", referred_by=v)
        p = Payment.objects.create(owner=u, plan="monthly", amount=9900, method="upi", status="pending")
        mark_paid(p.pk); mark_paid(p.pk)  # idempotent
        c = Commission.objects.get()
        self.assertEqual(c.amount, 1678)  # 20% of 9900/1.18 paise
        reverse(p)
        c.refresh_from_db(); self.assertEqual(c.status, "reversed")


class StaffCodeTest(APITestCase):
    def test_staff_and_counter_code(self):
        self._login = FlowTest._login.__get__(self)
        self._login("9999999996", "owner")
        code = self.client.post("/api/businesses/", {"name": "Chai Point"}).data["shop_code"]
        self.client.post(f"/api/b/{code}/programs/", {"title": "L", "tasks": [{"title": "8 chai", "type": "count",
            "target": 8, "rewards": [{"title": "Free chai", "type": "free_item"}]}]}, format="json")
        tid = self.client.get(f"/api/b/{code}/").data["programs"][0]["tasks"][0]["id"]
        self.assertEqual(self.client.post(f"/api/b/{code}/staff/", {"mobile": "9999999997", "password": "secret1"}).status_code, 201)
        token = self.client.post("/api/auth/login/", {"username": "9999999997", "password": "secret1"}).data["token"]
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token)  # staff
        cc = self.client.get(f"/api/b/{code}/counter-code/").data["code"]
        self.assertEqual(self.client.post(f"/api/b/{code}/staff/", {"mobile": "9999999998", "password": "secret1"}).status_code, 404)
        self._login("9999999999", "customer")
        self.client.post(f"/api/b/{code}/join/")
        self.assertEqual(self.client.post("/api/entries/", {"task": tid, "value": 1, "counter_code": "000000"}).status_code, 400)
        r = self.client.post("/api/entries/", {"task": tid, "value": 1, "counter_code": cc})
        self.assertEqual(r.data["status"], "approved")  # code auto-validates even in manual mode


from .models import Notification


class ReportNotifyTest(APITestCase):
    def test_report_and_notifications(self):
        self._login = FlowTest._login.__get__(self)
        self._login("9000000001", "owner")
        code = self.client.post("/api/businesses/", {"name": "Dairy", "daily_cap": 5, "cooldown_minutes": 0}).data["shop_code"]
        self.client.post(f"/api/b/{code}/programs/", {"title": "L", "tasks": [{"title": "2 visits", "type": "visit",
            "target": 2, "rewards": [{"title": "Free milk", "type": "free_item"}]}]}, format="json")
        tid = self.client.get(f"/api/b/{code}/").data["programs"][0]["tasks"][0]["id"]
        owner_auth = self.client._credentials["HTTP_AUTHORIZATION"]
        self._login("9000000002", "customer")
        self.client.post(f"/api/b/{code}/join/")
        ids = [self.client.post("/api/entries/", {"task": tid}).data["id"] for _ in range(2)]
        cust_auth = self.client._credentials["HTTP_AUTHORIZATION"]
        self.client.credentials(HTTP_AUTHORIZATION=owner_auth)
        alerts = self.client.get("/api/notifications/").data
        self.assertGreaterEqual(len(alerts), 2)  # pending alerts
        self.assertTrue(all("id" in alert for alert in alerts))
        for i in ids:
            self.client.post(f"/api/entries/{i}/review/", {"action": "approve"})
        rep = self.client.get(f"/api/b/{code}/report/").data
        self.assertEqual((rep["customers"], rep["repeat_rate"], rep["rewards_issued"]), (1, 100, 1))
        self.assertEqual(self.client.get(rep["csv_url"]).status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=cust_auth)
        self.assertTrue(any("Reward unlocked" in n["text"] for n in self.client.get("/api/notifications/").data))

    def test_owner_can_view_customers_grouped_by_reward(self):
        from .models import Reward, RewardGrant, TaskProgress, get_sub

        owner = User.objects.create_user("9000000031", "secret1", role="owner")
        business = Business.objects.create(owner=owner, name="Reward Activity Cafe")
        get_sub(owner)
        task = Task.objects.create(
            program=Program.objects.create(business=business, title="Coffee club"),
            title="Buy five coffees", type="count", target=5,
        )
        reward = Reward.objects.create(task=task, title="Free coffee", type="free_item")
        progressing = User.objects.create_user("9000000032", "secret1", first_name="Asha")
        ready = User.objects.create_user("9000000033", "secret1", first_name="Ravi")
        redeemed = User.objects.create_user("9000000034", "secret1", first_name="Mina")
        profiles = [
            CustomerProfile.objects.create(user=user, business=business)
            for user in (progressing, ready, redeemed)
        ]
        TaskProgress.objects.create(profile=profiles[0], task=task, current_value=3, target=5)
        TaskProgress.objects.create(profile=profiles[1], task=task, completed_count=1, target=5)
        TaskProgress.objects.create(profile=profiles[2], task=task, completed_count=1, target=5)
        ready_grant = RewardGrant.objects.create(
            profile=profiles[1], reward=reward, expires_at=timezone.now() + _td(days=5)
        )
        RewardGrant.objects.create(
            profile=profiles[2], reward=reward, status="used",
            expires_at=timezone.now() + _td(days=5), redeemed_at=timezone.now()
        )

        self.client.force_authenticate(owner)
        response = self.client.get(f"/api/b/{business.shop_code}/reward-activity/")
        self.assertEqual(response.status_code, 200)
        item = response.data["rewards"][0]
        self.assertEqual(item["title"], "Free coffee")
        self.assertEqual(item["stats"], {
            "participants": 3, "in_progress": 1, "available": 1, "issued": 2, "redeemed": 1,
        })
        customers = {customer["name"]: customer for customer in item["customers"]}
        self.assertEqual(customers["Asha"]["current"], "3.00")
        self.assertEqual(customers["Asha"]["mobile"], "9000000032")
        self.assertEqual(customers["Ravi"]["available"], 1)
        self.assertEqual(customers["Mina"]["redeemed"], 1)
        self.assertNotIn("code", customers["Ravi"])
        self.assertEqual(ready_grant.status, "active")

        other_owner = User.objects.create_user("9000000035", "secret1", role="owner")
        self.client.force_authenticate(other_owner)
        denied = self.client.get(f"/api/b/{business.shop_code}/reward-activity/")
        self.assertEqual(denied.status_code, 403)

    def test_notifications_can_be_marked_read_individually(self):
        from .models import Notification, User

        user = User.objects.create_user("9000000005", "secret1", role="owner")
        first = Notification.objects.create(user=user, text="Purchase needs review")
        second = Notification.objects.create(user=user, text="Other update")
        other_user = User.objects.create_user("9000000006", "secret1", role="owner")
        other = Notification.objects.create(user=other_user, text="Private update")
        self.client.force_authenticate(user=user)

        response = self.client.post("/api/notifications/read/", {"ids": [first.pk]}, format="json")
        self.assertEqual(response.data, {"updated": 1})
        first.refresh_from_db()
        second.refresh_from_db()
        other.refresh_from_db()
        self.assertTrue(first.read)
        self.assertFalse(second.read)
        self.assertFalse(other.read)
        response = self.client.post("/api/notifications/read/", format="json")
        self.assertEqual(response.status_code, 204)
        second.refresh_from_db()
        other.refresh_from_db()
        self.assertTrue(second.read)
        self.assertFalse(other.read)


class HindiPrintTest(APITestCase):
    def test_offlet_app_branding(self):
        icon = self.client.get("/icon.svg")
        self.assertEqual(icon.status_code, 200)
        self.assertEqual(icon["Content-Type"], "image/svg+xml")
        self.assertIn(b'viewBox="0 0 128 128"', icon.content)
        manifest = self.client.get("/manifest.json")
        self.assertEqual(manifest.json()["name"], "OFFLet")
        self.assertEqual(manifest.json()["short_name"], "OFFLet")
        icons = manifest.json()["icons"]
        self.assertIn({"src": "/static/app/offlet-icon-192.png", "sizes": "192x192",
                       "type": "image/png", "purpose": "any"}, icons)
        self.assertIn({"src": "/static/app/offlet-icon-maskable-512.png", "sizes": "512x512",
                       "type": "image/png", "purpose": "maskable"}, icons)
        app = self.client.get("/app/")
        self.assertContains(app, 'rel="apple-touch-icon" href="/static/app/offlet-icon-180.png"')
        self.assertContains(app, 'name="apple-mobile-web-app-status-bar-style"')
        self.assertContains(self.client.get("/app/classic/"),
                            'rel="apple-touch-icon" href="/static/app/offlet-icon-180.png"')

    def test_hindi_print_card(self):
        self._login = FlowTest._login.__get__(self)
        self._login("9000000003", "owner")
        code = self.client.post("/api/businesses/", {"name": "Chai", "language": "hi"}).data["shop_code"]
        response = self.client.get(f"/print/{code}/?size=tent")
        html = response.content.decode()
        self.assertIn("स्कैन करें", html)
        self.assertEqual(html.count(">OFFLet</span>"), 2)
        self.assertEqual(html.count('class="brand-mark"'), 2)
        self.assertEqual(html.count('<svg viewBox="0 0 40 40"'), 2)
        self.assertIn('background:url("/icon.svg")', html)

    def test_print_card_has_four_feature_callouts_around_a_compact_qr(self):
        self._login = FlowTest._login.__get__(self)
        self._login("9000000003", "owner")
        code = self.client.post("/api/businesses/", {"name": "Chai"}).data["shop_code"]
        html = self.client.get(f"/print/{code}/?size=a6").content.decode()
        for label in ("Earn Rewards", "Collect stamps", "Spin &amp; Win", "Shop Offers", "Refer &amp; Earn"):
            self.assertIn(label, html)
        self.assertEqual(html.count('class="feature '), 4)
        self.assertIn("width:28mm", html)
        self.assertIn("width:32%;height:25%", html)
        self.assertIn("height:75mm", html)

    def test_offlet_brand_is_on_all_shop_print_sizes(self):
        self._login = FlowTest._login.__get__(self)
        self._login("9000000003", "owner")
        code = self.client.post("/api/businesses/", {
            "name": "Chai", "category": "cafe", "tagline": "Coffee and good company"
        }).data["shop_code"]
        for size in ("a6", "a5", "a4", "tent"):
            with self.subTest(size=size):
                response = self.client.get(f"/print/{code}/?size={size}&bw=1")
                html = response.content.decode()
                panels = 2 if size == "tent" else 1
                self.assertEqual(html.count(">OFFLet</span>"), panels)
                self.assertEqual(html.count('class="brand-mark"'), panels)
                self.assertEqual(html.count("Coffee and good company"), panels)
                self.assertIn("Cafe &amp; coffee", html)
                self.assertIn("--accent:#111", html)
                self.assertIn(".brand{position:absolute;z-index:1;top:7mm;left:7mm", html)
                self.assertIn(".rot .brand{top:auto;right:7mm;bottom:7mm;left:auto}", html)
                self.assertIn('class="category-art" role="img"', html)
                self.assertNotIn("@keyframes", html)
                self.assertNotIn("animation:", html)

    def test_category_themes_fall_back_for_unknown_business_category(self):
        from .models import Business

        owner = User.objects.create_user("9000000004", "secret1", role="owner")
        business = Business.objects.create(owner=owner, name="Custom Shop", category="custom")
        response = self.client.get(f"/print/{business.shop_code}/")
        self.assertContains(response, "Shop &amp; rewards")

    def test_salon_qr_template_has_hair_and_hairdressing_art(self):
        from .models import Business

        owner = User.objects.create_user("9000000005", "secret1", role="owner")
        business = Business.objects.create(owner=owner, name="Mira Hair Studio", category="salon")
        response = self.client.get(f"/print/{business.shop_code}/")
        self.assertContains(response, 'class="salon-hair"')
        self.assertContains(response, 'class="salon-scissors"')
        self.assertContains(response, "salon-hair-stroke")
        self.assertNotContains(response, "@keyframes")
        self.assertNotContains(response, "animation:")


class SafetyFeaturesTest(APITestCase):
    def test_program_delete_removes_program_without_customer_activity(self):
        from .models import Business, Program, Task

        owner = User.objects.create_user("9000000042", "secret1", role="owner")
        business = Business.objects.create(owner=owner, name="Unused Program Shop")
        program = Program.objects.create(business=business, title="Unused rewards")
        Task.objects.create(program=program, title="Buy once", type="count", target=1)
        self.client.force_authenticate(user=owner)

        response = self.client.delete(f"/api/programs/{program.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["archived"])
        self.assertFalse(Program.objects.filter(pk=program.pk).exists())

    def test_program_delete_archives_program_with_customer_history(self):
        from .models import (Business, CustomerProfile, Program, PurchaseEntry, Reward, RewardGrant,
                             Task, TaskProgress)

        owner = User.objects.create_user("9000000043", "secret1", role="owner")
        business = Business.objects.create(owner=owner, name="Loyal Customers Shop")
        program = Program.objects.create(business=business, title="Coffee club")
        task = Task.objects.create(program=program, title="Buy coffee", type="count", target=5)
        reward = Reward.objects.create(task=task, title="Free coffee", type="free_item")
        customer = User.objects.create_user("9000000044", "secret1")
        profile = CustomerProfile.objects.create(user=customer, business=business)
        progress = TaskProgress.objects.create(profile=profile, task=task, current_value=2, target=5)
        entry = PurchaseEntry.objects.create(profile=profile, task=task, value=2)
        grant = RewardGrant.objects.create(profile=profile, reward=reward, expires_at=timezone.now() + _td(days=7))
        self.client.force_authenticate(user=owner)

        response = self.client.delete(f"/api/programs/{program.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["archived"])
        program.refresh_from_db()
        self.assertFalse(program.active)
        self.assertLess(program.end, timezone.localdate())
        self.assertTrue(TaskProgress.objects.filter(pk=progress.pk).exists())
        self.assertTrue(PurchaseEntry.objects.filter(pk=entry.pk).exists())
        self.assertTrue(RewardGrant.objects.filter(pk=grant.pk, status="active").exists())
        self.assertTrue(self.client.get(f"/api/b/{business.shop_code}/").data["programs"] == [])
        programs = self.client.get("/api/owner/businesses/").data[0]["programs"]
        self.assertTrue(programs[0]["archived"])
        self.assertEqual(self.client.patch(f"/api/programs/{program.pk}/", {"active": True},
                                           format="json").status_code, 400)

    def test_program_delete_requires_owner(self):
        from .models import Business, Program

        owner = User.objects.create_user("9000000045", "secret1", role="owner")
        other = User.objects.create_user("9000000046", "secret1", role="owner")
        program = Program.objects.create(
            business=Business.objects.create(owner=owner, name="Private Shop"), title="Private rewards"
        )
        self.client.force_authenticate(user=other)

        self.assertEqual(self.client.delete(f"/api/programs/{program.pk}/").status_code, 404)
        self.assertTrue(Program.objects.filter(pk=program.pk).exists())

    def test_gps_reverse_broadcast_delete(self):
        self._login = FlowTest._login.__get__(self)
        self._login("9000000010", "owner")
        code = self.client.post("/api/businesses/", {"name": "Kirana", "lat": 19.0, "lng": 72.8,
                                "cooldown_minutes": 0, "daily_cap": 9}).data["shop_code"]
        self.client.post(f"/api/b/{code}/programs/", {"title": "L", "tasks": [{"title": "2 buys", "type": "count",
            "target": 2, "rewards": [{"title": "Gift", "type": "gift"}]}]}, format="json")
        tid = self.client.get(f"/api/b/{code}/").data["programs"][0]["tasks"][0]["id"]
        oa = self.client._credentials["HTTP_AUTHORIZATION"]
        cc = self.client.get(f"/api/b/{code}/counter-code/").data["code"]
        self._login("9000000011", "customer")
        self.client.post(f"/api/b/{code}/join/", {"consent": True})
        far = self.client.post("/api/entries/", {"task": tid, "value": 1, "counter_code": cc, "lat": 28.6, "lng": 77.2})
        self.assertEqual((far.data["status"], far.data["far"]), ("pending", True))  # far: code does not auto-approve
        self._login("9000000013", "customer")  # a counter code is single-use per customer
        self.client.post(f"/api/b/{code}/join/")
        near = self.client.post("/api/entries/", {"task": tid, "value": 2, "counter_code": cc, "lat": 19.0001, "lng": 72.8001})
        self.assertEqual(near.data["status"], "approved")
        self.assertEqual(len(self.client.get("/api/me/shops/").data[0]["rewards"]), 1)
        ca = self.client._credentials["HTTP_AUTHORIZATION"]
        self.client.credentials(HTTP_AUTHORIZATION=oa)
        self.assertEqual(self.client.post(f"/api/entries/{near.data['id']}/reverse/").status_code, 200)  # undo revokes reward
        self.assertEqual(self.client.post(f"/api/b/{code}/broadcast/", {"text": "10% off today"}).data["sent"], 1)
        self.assertEqual(self.client.post(f"/api/b/{code}/broadcast/", {"text": "again"}).status_code, 400)
        self.client.credentials(HTTP_AUTHORIZATION=ca)
        self.assertEqual(self.client.get("/api/me/shops/").data[0]["rewards"][0]["status"], "revoked")
        self.assertEqual(self.client.delete("/api/me/").status_code, 204)
        self.assertFalse(User.objects.filter(username="9000000013").exists())

    def test_otp_reset(self):
        user = User.objects.create_user("9000000012", password="oldpass1", email="asha@example.test")
        user.email_verified = True
        user.save(update_fields=["email_verified"])
        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
            EMAIL_HOST="smtp.example.test",
            DEFAULT_FROM_EMAIL="noreply@example.test",
            EMAIL_OTP_ENABLED=True,
        ):
            self.client.post("/api/auth/reset/request/", {"mobile": "9000000012"})
        from .models import OtpCode
        self.assertEqual(mail.outbox[-1].to, ["asha@example.test"])
        o = OtpCode.objects.get(user=user, purpose="password_reset")
        o.code_hash = __import__("core.extras", fromlist=["_h"])._h("123456"); o.save()
        self.assertEqual(self.client.post("/api/auth/reset/confirm/", {"mobile": "9000000012", "otp": "000000", "new": "newpass1"}).status_code, 400)
        self.assertEqual(self.client.post("/api/auth/reset/confirm/", {"mobile": "9000000012", "otp": "123456", "new": "newpass1"}).status_code, 200)
        self.assertEqual(self.client.post("/api/auth/login/", {"mobile": "9000000012", "password": "newpass1"}).status_code, 200)

    @patch("core.extras.notify")
    @override_settings(NOTIFY_WEBHOOK_URL="https://sms.example.test")
    def test_password_reset_uses_sms_when_a_gateway_is_configured(self, send_sms):
        user = User.objects.create_user("9000000015", password="oldpass1")
        response = self.client.post("/api/auth/reset/request/", {"mobile": user.username})
        self.assertEqual(response.status_code, 200)
        send_sms.assert_called_once()
        from .models import OtpCode
        self.assertTrue(OtpCode.objects.filter(user=user, purpose="password_reset").exists())

    def test_password_reset_does_not_send_to_an_unverified_email(self):
        user = User.objects.create_user("9000000016", password="oldpass1", email="unverified@example.test")
        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
            EMAIL_HOST="smtp.example.test",
            DEFAULT_FROM_EMAIL="noreply@example.test",
            EMAIL_OTP_ENABLED=True,
        ):
            response = self.client.post("/api/auth/reset/request/", {"mobile": user.username})
        self.assertEqual(response.status_code, 200)
        from .models import OtpCode
        self.assertFalse(OtpCode.objects.filter(user=user, purpose="password_reset").exists())

    def test_recovery_email_is_not_changed_until_otp_is_confirmed(self):
        user = User.objects.create_user("9000000014", password="oldpass1", email="old@example.test")
        user.email_verified = True
        user.save(update_fields=["email_verified"])
        self.client.force_authenticate(user=user)
        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
            EMAIL_HOST="smtp.example.test",
            DEFAULT_FROM_EMAIL="noreply@example.test",
            EMAIL_OTP_ENABLED=True,
        ):
            response = self.client.post("/api/auth/email/request/", {"email": "new@example.test"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(mail.outbox[-1].to, ["new@example.test"])
        user.refresh_from_db()
        self.assertEqual(user.email, "old@example.test")
        self.assertTrue(user.email_verified)
        from .models import OtpCode
        from .extras import _h
        otp = OtpCode.objects.get(user=user, purpose="email_verify")
        self.assertEqual(otp.target_email, "new@example.test")
        otp.code_hash = _h("123456")
        otp.save(update_fields=["code_hash"])

        confirmed = self.client.post("/api/auth/email/confirm/", {"otp": "123456"}, format="json")
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        user.refresh_from_db()
        self.assertEqual(user.email, "new@example.test")
        self.assertTrue(user.email_verified)
        self.assertEqual(self.client.get("/api/me/profile/").data["email"], "new@example.test")


class LifecycleLegalTest(APITestCase):
    def test_legal_pages_and_consent(self):
        for p in ("about", "privacy", "terms", "refund", "pricing", "contact", "shipping-delivery"):
            page = self.client.get(f"/{p}/")
            self.assertEqual(page.status_code, 200)
            self.assertContains(page, 'id="legalLogin"')
            self.assertContains(page, "Log in</a>")
        about = self.client.get("/about/")
        self.assertContains(about, "digital loyalty and rewards platform")
        delivery = self.client.get("/shipping-delivery/")
        self.assertContains(delivery, "do not sell, pack, or ship physical products")
        self.assertContains(delivery, "payment reference")
        terms = self.client.get("/terms/")
        self.assertContains(terms, "request clarification")
        self.assertContains(terms, "warn, limit, suspend or block")
        self.assertContains(terms, "consumer or legal remedies")
        privacy = self.client.get("/privacy/")
        self.assertContains(privacy, "review support requests, suspected fraud")
        self.assertContains(privacy, "Support and complaint records")
        contact = self.client.get("/contact/")
        self.assertContains(contact, "Report a shop or customer-safety concern")
        self.assertContains(contact, "Grievance Officer")
        refunds = self.client.get("/refund/")
        self.assertContains(refunds, "cannot issue a refund for that transaction")
        app = self.client.get("/app/")
        self.assertContains(app, 'href="/shipping-delivery/"')
        self.assertContains(app, "viewport-fit=cover")
        self.assertContains(app, "/static/app/core.js")  # v2 shell loads the modular frontend
        self.assertContains(app, "/static/app/install.js")
        classic = self.client.get("/app/classic/")  # previous single-file UI kept as a fallback
        self.assertContains(classic, "viewport-fit=cover")
        self.assertContains(classic, "/static/app/install.js")
        self.assertContains(classic, "[hidden]{display:none!important}")
        self.assertContains(classic, ".topbar{position:sticky;top:0;z-index:33")
        self.assertContains(classic, ".sidebar{z-index:31")
        self.assertContains(classic, ".platform-nav-toggle{position:relative;z-index:32")
        self.assertContains(classic, 'id="loginBtn"')
        self.assertContains(classic, "$('#loginBtn').hidden=!!T")
        self.assertContains(classic, "Subscribe with AutoPay · ")
        self.assertContains(classic, "AutoPay is required for subscriptions.")
        self.assertContains(classic, "if(R==='customer')location.reload();else location.replace('/app/')")
        self.assertContains(classic, "if(m&&T&&R!=='customer')location.replace('/app/')")
        self.assertContains(classic, "['offers','Rewards','tag']")
        self.assertContains(classic, "['more','More','more']")
        r = self.client.post("/api/auth/register/", {"mobile": "9000000020", "password": "secret1"})
        self.assertEqual(r.status_code, 400)  # must accept Terms + Privacy
        r = self.client.post("/api/auth/register/", {"mobile": "9000000020", "password": "secret1", "accepted": True})
        self.assertEqual(r.status_code, 201)
        self.assertIsNotNone(User.objects.get(username="9000000020").consent_at)

    def test_lapse_then_return_keeps_everything(self):
        from .models import Business, CustomerProfile, RewardGrant, Reward, Program, Task
        o = User.objects.create_user("9000000021", password="x", role="owner")
        b = Business.objects.create(owner=o, name="Chai", pay_upi_id="chai@upi")
        pr = Program.objects.create(business=b, title="L")
        t = Task.objects.create(program=pr, title="5 chai", type="count", target=5)
        rw = Reward.objects.create(task=t, title="Free chai", type="free_item")
        c = User.objects.create_user("9000000022", password="x")
        prof = CustomerProfile.objects.create(user=c, business=b)
        s = get_sub(o)
        s.paid_until = timezone.now() - _td(days=20)  # shop is paused during the 30-day renewal window
        s.save()
        g = RewardGrant.objects.create(profile=prof, reward=rw, expires_at=timezone.now() + _td(days=10))
        self.assertEqual((s.state, b.is_live), ("grace", False))
        before = g.expires_at
        p = Payment.objects.create(owner=o, plan="monthly", amount=9900, method="upi", status="pending", utr="123456789012")
        mark_paid(p.pk)
        s.refresh_from_db(); g.refresh_from_db(); b = Business.objects.get(pk=b.pk)
        self.assertEqual((s.state, b.is_live), ("active", True))
        self.assertGreater((g.expires_at - before).days, 18)  # extended by the paused time
        self.assertTrue(CustomerProfile.objects.filter(pk=prof.pk).exists())  # customers kept
        s.paid_until = timezone.now() - _td(days=30 + 400)  # long gone
        s.save()
        from django.core.management import call_command
        call_command("purge_lapsed", "--apply")
        self.assertFalse(Business.objects.filter(pk=b.pk).exists())  # deleted after retention


class PublicShopOffersBasicsTest(APITestCase):
    def test_customer_shop_qr_can_be_downloaded_as_png(self):
        from .models import Business

        owner = User.objects.create_user("9000000038", "secret1", role="owner")
        business = Business.objects.create(owner=owner, name="QR Cafe")

        response = self.client.get(f"/api/b/{business.shop_code}/qr.png?download=1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response["Content-Disposition"],
                         f'attachment; filename="{business.shop_code}-shop-qr.png"')

    def test_paused_shop_stops_new_earning_but_keeps_customer_history(self):
        from .models import Business, CustomerProfile, Program, Task, TaskProgress, get_sub

        owner = User.objects.create_user("9000000036", "secret1", role="owner")
        business = Business.objects.create(owner=owner, name="Paused Cafe")
        subscription = get_sub(owner)
        subscription.paid_until = timezone.now() - _td(days=1)
        subscription.save()
        task = Task.objects.create(
            program=Program.objects.create(business=business, title="Visit rewards"),
            title="Visit five times", type="visit", target=5,
        )
        customer = User.objects.create_user("9000000037", "secret1")
        profile = CustomerProfile.objects.create(user=customer, business=business)
        TaskProgress.objects.create(profile=profile, task=task, current_value=2, target=5)

        public = self.client.get(f"/api/b/{business.shop_code}/")
        self.assertEqual(public.data, {"name": "Paused Cafe", "paused": True})

        self.client.force_authenticate(user=customer)
        saved = self.client.get("/api/me/shops/")
        self.assertEqual(saved.data[0]["progress"][0]["current"], 2)
        self.assertEqual(saved.data[0]["shop_code"], business.shop_code)

    def test_owner_can_publish_repeatable_reward_with_expiry_and_terms(self):
        from .models import Business, get_sub

        owner = User.objects.create_user("9000000035", "secret1", role="owner")
        business = Business.objects.create(owner=owner, name="Cafe")
        get_sub(owner)
        self.client.force_authenticate(user=owner)
        response = self.client.post(f"/api/b/{business.shop_code}/programs/", {
            "title": "Weekend coffee club",
            "tasks": [{
                "title": "Visit 5 times", "type": "visit", "target": 5,
                "repeatable": True, "max_per_customer": 3,
                "rewards": [{
                    "title": "10% off", "type": "percent_off", "value": 10,
                    "expiry_days": 14, "terms": "Valid on weekdays",
                }],
            }],
        }, format="json")

        self.assertEqual(response.status_code, 201)
        task = response.data["tasks"][0]
        self.assertEqual((task["repeatable"], task["max_per_customer"]), (True, 3))
        self.assertEqual(task["rewards"][0]["terms"], "Valid on weekdays")
        self.assertEqual(task["rewards"][0]["expiry_days"], 14)


class CoinAndScratchRewardsTest(APITestCase):
    def setUp(self):
        from .models import CoinProgram, Program, ScratchCampaign, Task

        self.owner = User.objects.create_user("9000000881", "secret1", role="owner")
        self.customer = User.objects.create_user("9000000882", "secret1", role="customer")
        self.business = Business.objects.create(owner=self.owner, name="Rewards Cafe")
        self.profile = CustomerProfile.objects.create(user=self.customer, business=self.business)
        program = Program.objects.create(business=self.business, title="Spend club")
        self.task = Task.objects.create(program=program, title="Spend", type="amount", target=100000)
        CoinProgram.objects.create(business=self.business, enabled=True, spend_per_coin=10, daily_cap=1000)
        self.campaign = ScratchCampaign.objects.create(
            business=self.business, active=True, prize_title="Free tea", cards_per_deck=3, winning_cards=1,
        )

    def _approve_purchase(self, value=125):
        entry = PurchaseEntry.objects.create(profile=self.profile, task=self.task, value=value)
        self.client.force_authenticate(self.owner)
        response = self.client.post(f"/api/entries/{entry.pk}/review/", {"action": "approve"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        return entry

    def test_approved_spend_earns_coins_once_and_issues_one_bounded_scratch_ticket(self):
        from .models import CoinAccount, CoinTransaction, Notification, ScratchTicket

        self.client.force_authenticate(self.owner)
        with patch("core.services.secrets.randbelow", return_value=0):
            entries = [self._approve_purchase() for _ in range(3)]
        account = CoinAccount.objects.get(profile=self.profile)
        self.assertEqual(account.balance, 36)
        self.assertEqual(CoinTransaction.objects.filter(account=account, kind="purchase").count(), 3)
        tickets = list(ScratchTicket.objects.filter(purchase_entry__in=entries).order_by("id"))
        self.assertEqual([ticket.is_winner for ticket in tickets], [True, False, False])
        self.assertEqual({ticket.deck_number for ticket in tickets}, {self.campaign.deck_number})
        scratch_notices = Notification.objects.filter(user=self.customer, text__startswith="Scratch card ready at")
        self.assertEqual(scratch_notices.count(), 3)
        self.assertFalse(scratch_notices.exclude(link=f"/b/{self.business.shop_code}/?tab=rewards").exists())
        duplicate = self.client.post(f"/api/entries/{entries[0].pk}/review/", {"action": "approve"}, format="json")
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(CoinTransaction.objects.filter(account=account, kind="purchase").count(), 3)

    def test_coin_redemption_reserves_balance_and_decline_refunds_it(self):
        from .models import CoinAccount, CoinReward, CoinTransaction

        self._approve_purchase()
        reward = CoinReward.objects.create(business=self.business, title="Free coffee", cost=10)
        self.client.force_authenticate(self.customer)
        request = self.client.post(f"/api/coin-rewards/{reward.pk}/request/", {}, format="json")
        self.assertEqual(request.status_code, 201, request.data)
        self.assertEqual(request.data["balance"], 2)

        self.client.force_authenticate(self.owner)
        review = self.client.post(
            f"/api/b/{self.business.shop_code}/coin-redemptions/{request.data['id']}/",
            {"action": "decline"}, format="json",
        )
        self.assertEqual(review.status_code, 200, review.data)
        account = CoinAccount.objects.get(profile=self.profile)
        self.assertEqual(account.balance, 12)
        self.assertEqual(list(CoinTransaction.objects.filter(account=account).order_by("id").values_list("delta", flat=True)),
                         [12, -10, 10])

    def test_coin_balances_and_shop_listed_rewards_are_isolated_per_shop(self):
        from .models import CoinAccount, CoinProgram, CoinReward, Program, Task

        self._approve_purchase()
        other_business = Business.objects.create(owner=self.owner, name="Other shop")
        other_profile = CustomerProfile.objects.create(user=self.customer, business=other_business)
        other_program = Program.objects.create(business=other_business, title="Other spend club")
        other_task = Task.objects.create(program=other_program, title="Spend", type="amount", target=100000)
        CoinProgram.objects.create(business=other_business, enabled=True, spend_per_coin=10, daily_cap=1000)
        reward = CoinReward.objects.create(business=other_business, title="Shop-only tea", cost=10)

        self.client.force_authenticate(self.customer)
        other_shop = self.client.get(f"/api/me/shop/{other_business.shop_code}/")
        self.assertEqual(other_shop.data["coins"]["balance"], 0)
        self.assertEqual([item["id"] for item in other_shop.data["coins"]["rewards"]], [reward.id])
        unavailable = self.client.post(f"/api/coin-rewards/{reward.pk}/request/", {}, format="json")
        self.assertEqual(unavailable.status_code, 400)
        original_shop = self.client.get(f"/api/me/shop/{self.business.shop_code}/")
        self.assertEqual(original_shop.data["coins"]["balance"], 12)

        entry = PurchaseEntry.objects.create(profile=other_profile, task=other_task, value=125)
        self.client.force_authenticate(self.owner)
        approved = self.client.post(f"/api/entries/{entry.pk}/review/", {"action": "approve"}, format="json")
        self.assertEqual(approved.status_code, 200, approved.data)

        self.client.force_authenticate(self.customer)
        redeemed = self.client.post(f"/api/coin-rewards/{reward.pk}/request/", {}, format="json")
        self.assertEqual(redeemed.status_code, 201, redeemed.data)
        self.assertEqual(CoinAccount.objects.get(profile=self.profile).balance, 12)
        self.assertEqual(CoinAccount.objects.get(profile=other_profile).balance, 2)

    def test_daily_coin_cap_applies_across_approved_purchases(self):
        from .models import CoinAccount, CoinProgram

        CoinProgram.objects.filter(business=self.business).update(daily_cap=20)
        for _ in range(3):
            self._approve_purchase()
        self.assertEqual(CoinAccount.objects.get(profile=self.profile).balance, 20)

    def test_owner_can_configure_coin_and_scratch_rewards(self):
        self.client.force_authenticate(self.owner)
        coins = self.client.put(
            f"/api/b/{self.business.shop_code}/coin-program/",
            {"enabled": True, "spend_per_coin": 25, "daily_cap": 500}, format="json",
        )
        self.assertEqual(coins.status_code, 200, coins.data)
        self.assertEqual((coins.data["spend_per_coin"], coins.data["daily_cap"]), (25, 500))
        reward = self.client.post(f"/api/b/{self.business.shop_code}/coin-rewards/", {
            "title": "Free tea", "description": "Small tea", "cost": 30,
        }, format="json")
        self.assertEqual(reward.status_code, 201, reward.data)
        scratch = self.client.put(f"/api/b/{self.business.shop_code}/scratch-campaign/configure/", {
            "active": True, "prize_title": "10% off", "prize_type": "percent_off", "prize_value": 10,
            "cards_per_deck": 20, "winning_cards": 2, "expiry_days": 14,
        }, format="json")
        self.assertEqual(scratch.status_code, 200, scratch.data)
        self.assertEqual((scratch.data["cards_per_deck"], scratch.data["winning_cards"]), (20, 2))
        invalid = self.client.put(f"/api/b/{self.business.shop_code}/scratch-campaign/configure/", {
            "active": True, "prize_title": "Too much", "prize_type": "percent_off", "prize_value": 150,
            "cards_per_deck": 20, "winning_cards": 2, "expiry_days": 14,
        }, format="json")
        self.assertEqual(invalid.status_code, 400)

    def test_coin_reward_delete_preserves_redemption_history(self):
        from .models import CoinReward

        self._approve_purchase()
        unused = CoinReward.objects.create(business=self.business, title="Unused item", cost=5)
        used = CoinReward.objects.create(business=self.business, title="Redeemed item", cost=5)
        self.client.force_authenticate(self.customer)
        redemption = self.client.post(f"/api/coin-rewards/{used.pk}/request/", {}, format="json")
        self.assertEqual(redemption.status_code, 201, redemption.data)

        self.client.force_authenticate(self.owner)
        listing = self.client.get(f"/api/b/{self.business.shop_code}/coin-program/")
        counts = {reward["id"]: reward["redemptions_count"] for reward in listing.data["rewards"]}
        self.assertEqual((counts[unused.id], counts[used.id]), (0, 1))

        deleted = self.client.delete(f"/api/b/{self.business.shop_code}/coin-rewards/{unused.pk}/")
        self.assertEqual(deleted.status_code, 204)
        blocked = self.client.delete(f"/api/b/{self.business.shop_code}/coin-rewards/{used.pk}/")
        self.assertEqual(blocked.status_code, 400)
        self.assertTrue(CoinReward.objects.filter(pk=used.pk).exists())
        hidden = self.client.patch(
            f"/api/b/{self.business.shop_code}/coin-rewards/{used.pk}/", {"active": False}, format="json",
        )
        self.assertEqual(hidden.status_code, 200, hidden.data)
        self.assertFalse(hidden.data["active"])

    def test_purchase_undo_is_blocked_after_earned_coins_are_spent(self):
        from .models import CoinReward, ScratchTicket

        entry = self._approve_purchase()
        reward = CoinReward.objects.create(business=self.business, title="Free coffee", cost=10)
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.post(f"/api/coin-rewards/{reward.pk}/request/", {}, format="json").status_code, 201)
        self.client.force_authenticate(self.owner)
        response = self.client.post(f"/api/entries/{entry.pk}/reverse/", {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(ScratchTicket.objects.get(purchase_entry=entry).valid)

    def test_scratch_reveal_is_idempotent_and_creates_a_reward(self):
        from .models import RewardGrant, ScratchTicket

        with patch("core.services.secrets.randbelow", return_value=0):
            entry = self._approve_purchase()
        ticket = ScratchTicket.objects.get(purchase_entry=entry)
        self.client.force_authenticate(self.customer)
        first = self.client.post(f"/api/scratch-tickets/{ticket.pk}/reveal/", {}, format="json")
        second = self.client.post(f"/api/scratch-tickets/{ticket.pk}/reveal/", {}, format="json")
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(second.data["reward_code"], first.data["reward_code"])
        self.assertEqual(RewardGrant.objects.filter(profile=self.profile).count(), 1)

    def test_undo_reverses_unspent_coins_and_invalidates_unrevealed_scratch_ticket(self):
        from .models import CoinAccount, CoinTransaction, ScratchTicket

        with patch("core.services.secrets.randbelow", return_value=0):
            entry = self._approve_purchase()
        ticket = ScratchTicket.objects.get(purchase_entry=entry)
        self.client.force_authenticate(self.owner)
        reversed_entry = self.client.post(f"/api/entries/{entry.pk}/reverse/", {}, format="json")
        self.assertEqual(reversed_entry.status_code, 200, reversed_entry.data)
        self.assertEqual(CoinAccount.objects.get(profile=self.profile).balance, 0)
        self.assertEqual(CoinTransaction.objects.filter(kind="reversal").count(), 1)
        ticket.refresh_from_db()
        self.assertFalse(ticket.valid)
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.post(f"/api/scratch-tickets/{ticket.pk}/reveal/", {}, format="json").status_code, 400)
        self.assertEqual(self.client.delete("/api/me/").status_code, 204)


class PublicShopOffersTest(APITestCase):
    def test_public_shop_lists_only_running_offers_and_returns_upi_intent(self):
        from urllib.parse import parse_qs, urlparse
        from .models import Business, CustomerProfile, Program, Task, Reward, get_sub

        owner = User.objects.create_user("9000000030", "secret1", role="owner")
        business = Business.objects.create(owner=owner, name="Cafe & Tea", pay_upi_id="cafe@upi")
        get_sub(owner)
        today = timezone.localdate()
        running = Program.objects.create(business=business, title="Lunch rewards",
                                         start=today, end=today)
        task = Task.objects.create(program=running, title="Buy lunch", type="amount", target=500)
        Reward.objects.create(task=task, title="Free tea", type="free_item")
        Program.objects.create(business=business, title="Expired", start=today - _td(days=2),
                               end=today - _td(days=1))
        Program.objects.create(business=business, title="Coming soon", start=today + _td(days=1))

        response = self.client.get(f"/api/b/{business.shop_code}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([p["title"] for p in response.data["programs"]], ["Lunch rewards"])
        self.assertEqual(response.data["programs"][0]["tasks"][0]["rewards"][0]["title"], "Free tea")
        self.assertTrue(response.data["require_bill_photo"] is False)
        self.assertEqual(parse_qs(urlparse(response.data["pay_link"]).query),
                         {"pa": ["cafe@upi"], "pn": ["Cafe & Tea"], "cu": ["INR"]})

    def test_customer_progress_includes_task_id(self):
        from .models import Business, CustomerProfile, Program, Task, TaskProgress, get_sub

        owner = User.objects.create_user("9000000031", "secret1", role="owner")
        business = Business.objects.create(owner=owner, name="Cafe")
        get_sub(owner)
        task = Task.objects.create(program=Program.objects.create(business=business, title="Visits"),
                                   title="Visit 5 times", type="visit", target=5)
        customer = User.objects.create_user("9000000032", "secret1")
        profile = CustomerProfile.objects.create(user=customer, business=business)
        TaskProgress.objects.create(profile=profile, task=task, current_value=2, target=5)
        self.client.force_authenticate(user=customer)

        response = self.client.get("/api/me/shops/")
        self.assertEqual(response.data[0]["progress"][0]["task_id"], task.id)
        self.assertEqual(response.data[0]["progress"][0]["task_type"], "visit")

    def test_customer_purchase_entry_updates_progress_after_shop_approval(self):
        from .models import Business, CustomerProfile, Program, Task, Reward, get_sub

        owner = User.objects.create_user("9000000033", "secret1", role="owner")
        business = Business.objects.create(owner=owner, name="Cafe")
        get_sub(owner)
        task = Task.objects.create(program=Program.objects.create(business=business, title="Spend rewards"),
                                   title="Spend ₹100", type="amount", target=100)
        Reward.objects.create(task=task, title="Free tea", type="free_item")
        customer = User.objects.create_user("9000000034", "secret1")
        CustomerProfile.objects.create(user=customer, business=business)
        self.client.force_authenticate(user=customer)

        entry = self.client.post("/api/entries/", {"task": task.id, "value": "125.50"}, format="json")
        self.assertEqual((entry.status_code, entry.data["status"]), (201, "pending"))
        pending_history = self.client.get("/api/me/shops/").data[0]["entries"]
        self.assertEqual(pending_history[0]["status"], "pending")
        self.assertEqual((pending_history[0]["task_id"], pending_history[0]["task_type"]), (task.id, "amount"))
        self.client.force_authenticate(user=owner)
        approved = self.client.post(f"/api/entries/{entry.data['id']}/review/",
                                    {"action": "approve"}, format="json")
        self.assertEqual(approved.data["status"], "approved")

        self.client.force_authenticate(user=customer)
        customer_shop = self.client.get("/api/me/shops/").data[0]
        self.assertEqual(customer_shop["entries"][0]["id"], entry.data["id"])
        self.assertEqual(customer_shop["entries"][0]["status"], "approved")
        self.assertEqual(customer_shop["progress"][0]["task_id"], task.id)
        self.assertEqual(str(customer_shop["progress"][0]["current"]), "25.50")
        self.assertEqual(customer_shop["progress"][0]["completed"], 1)
        self.assertEqual(customer_shop["rewards"][0]["title"], "Free tea")
        self.assertEqual(customer_shop["rewards"][0]["type"], "free_item")
