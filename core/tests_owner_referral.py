"""Tests for business owners referring other businesses and earning in a wallet."""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from . import vendors
from .models import (Business, BusinessReferralSettings, Commission, Notification, Payment, Payout, Subscription,
                     User, Vendor, get_sub)


class OwnerReferralBase(APITestCase):
    def make_owner(self, mobile, upi="", referred_by=None):
        u = User.objects.create_user(username=mobile, password="secret1", role="owner", first_name="Own" + mobile[-2:],
                                     referred_by=referred_by)
        Business.objects.create(owner=u, name="Shop" + mobile[-2:], pay_upi_id=upi)
        return u

    def login(self, user):
        from rest_framework.authtoken.models import Token
        self.client.credentials(HTTP_AUTHORIZATION="Token " + Token.objects.get_or_create(user=user)[0].key)

    def enrol(self, user, status="approved", upi="ref@upi"):
        self.login(user)
        r = self.client.post("/api/vendor/apply/", {"pan": "ABCDE1234F", "upi_id": upi})
        self.assertEqual(r.status_code, 201, r.data)
        Vendor.objects.filter(user=user).update(status=status, rate=20)
        return Vendor.objects.get(user=user)

    def pay(self, owner, amount=9900):
        p = Payment.objects.create(owner=owner, plan="monthly", amount=amount, method="gateway", status="paid")
        vendors.accrue(p)
        return p


class EnrolmentTests(OwnerReferralBase):
    def test_owner_sees_not_applied_then_pending_after_applying(self):
        owner = self.make_owner("9300000001")
        self.login(owner)
        self.assertEqual(self.client.get("/api/vendor/dashboard/").data["status"], "not_applied")
        self.assertEqual(self.client.get("/api/vendor/wallet/").data["status"], "not_applied")
        r = self.client.post("/api/vendor/apply/", {"pan": "ABCDE1234F", "upi_id": "own@upi"})
        self.assertEqual((r.status_code, r.data["status"]), (201, "pending"))
        self.assertEqual(self.client.get("/api/vendor/wallet/").data["status"], "pending")

    @override_settings(OWNER_REFERRAL_AUTO_APPROVE=True)
    def test_auto_approve_setting_activates_owner_immediately(self):
        owner = self.make_owner("9300000002")
        self.login(owner)
        r = self.client.post("/api/vendor/apply/", {"pan": "ABCDE1234F", "upi_id": "own@upi"})
        self.assertEqual(r.data["status"], "approved")
        self.assertEqual(self.client.get("/api/vendor/wallet/").data["status"], "approved")

    def test_owner_cannot_apply_twice_and_customers_cannot_apply_or_open_wallet(self):
        owner = self.make_owner("9300000003")
        self.enrol(owner)
        self.assertEqual(self.client.post("/api/vendor/apply/", {"pan": "ABCDE1234F", "upi_id": "x@upi"}).status_code, 400)
        cust = User.objects.create_user(username="9300000004", password="x", role="customer")
        self.login(cust)
        self.assertEqual(self.client.post("/api/vendor/apply/", {"pan": "ABCDE1234F", "upi_id": "x@upi"}).status_code, 400)
        self.assertEqual(self.client.get("/api/vendor/wallet/").status_code, 403)

    def test_pending_owner_gets_no_attribution_but_approved_owner_does(self):
        owner = self.make_owner("9300000005")
        v = self.enrol(owner, status="pending")
        body = {"mobile": "9300000006", "password": "secret1", "role": "owner", "name": "A", "accepted": True, "ref": v.code}
        self.client.credentials()
        self.assertEqual(self.client.post("/api/auth/register/", body).status_code, 201)
        self.assertIsNone(User.objects.get(username="9300000006").referred_by)
        Vendor.objects.filter(pk=v.pk).update(status="approved")
        body["mobile"] = "9300000007"
        self.assertEqual(self.client.post("/api/auth/register/", body).status_code, 201)
        self.assertEqual(User.objects.get(username="9300000007").referred_by_id, v.pk)


class WalletTests(OwnerReferralBase):
    def setUp(self):
        self.referrer = self.make_owner("9310000001", upi="refshop@upi")
        self.v = self.enrol(self.referrer, upi="ref@upi")
        subscription = get_sub(self.referrer)
        subscription.paid_until = timezone.now() + timedelta(days=365)
        subscription.save(update_fields=["paid_until"])
        Payment.objects.create(owner=self.referrer, plan="yearly", amount=99900, method="gateway", status="paid")
        self.friend = self.make_owner("9310000002", upi="friend@upi", referred_by=self.v)

    def amount(self):
        return int((Decimal(9900) * 100 / 118 * 20 / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def test_referred_business_payment_credits_wallet_on_hold_and_notifies(self):
        self.pay(self.friend)
        c = Commission.objects.get()
        self.assertEqual(c.amount, self.amount())
        self.login(self.referrer)
        w = self.client.get("/api/vendor/wallet/").data
        self.assertEqual((w["balance"], w["clearing"], w["ready"], w["processing"], w["paid_net"]),
                         (self.amount(), self.amount(), 0, 0, 0))
        self.assertEqual(len(w["ledger"]), 1)
        self.assertEqual((w["ledger"][0]["kind"], w["ledger"][0]["label"]), ("credit", "Shop02"))
        self.assertTrue(Notification.objects.filter(user=self.referrer, text__contains="You earned").exists())

    def test_accrue_is_idempotent_for_the_same_payment(self):
        p = self.pay(self.friend)
        vendors.accrue(p)
        self.assertEqual(Commission.objects.count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.referrer, text__contains="You earned").count(), 1)

    def test_owner_referral_earning_stops_when_yearly_plan_expires(self):
        Subscription.objects.filter(owner=self.referrer).update(paid_until=timezone.now() - timedelta(seconds=1))
        self.pay(self.friend)
        self.assertEqual(Commission.objects.count(), 0)

    def test_owner_referral_requires_yearly_plan_not_monthly(self):
        Payment.objects.create(owner=self.referrer, plan="monthly", amount=9900, method="gateway", status="paid")
        self.pay(self.friend)
        self.assertEqual(Commission.objects.count(), 0)

    def test_superadmin_program_switch_stops_new_owner_referral_earning(self):
        BusinessReferralSettings.objects.filter(pk=1).update(enabled=False)
        self.pay(self.friend)
        self.assertEqual(Commission.objects.count(), 0)

    def test_buckets_move_from_clearing_to_ready_to_processing_to_paid(self):
        self.pay(self.friend)
        Commission.objects.update(payable_on=timezone.now() - timedelta(days=1))
        self.login(self.referrer)
        w = self.client.get("/api/vendor/wallet/").data
        self.assertEqual((w["clearing"], w["ready"], w["balance"]), (0, self.amount(), self.amount()))
        po = Payout.objects.create(vendor=self.v, amount=self.amount())
        Commission.objects.update(status="payable", payout=po)
        w = self.client.get("/api/vendor/wallet/").data
        self.assertEqual((w["ready"], w["processing"], w["balance"]), (0, self.amount(), self.amount()))
        vendors.mark_payout_paid(po, "UTR123")
        w = self.client.get("/api/vendor/wallet/").data
        self.assertEqual((w["balance"], w["paid_net"], w["paid_gross"]), (0, self.amount(), self.amount()))
        kinds = {r["kind"] for r in w["ledger"]}
        self.assertEqual(kinds, {"credit", "payout"})

    def test_refund_reverses_a_held_commission_and_removes_it_from_the_balance(self):
        p = self.pay(self.friend)
        vendors.reverse(p)
        self.login(self.referrer)
        w = self.client.get("/api/vendor/wallet/").data
        self.assertEqual((w["balance"], w["reversed"]), (0, self.amount()))

    def test_self_referral_through_matching_shop_upi_earns_nothing(self):
        sneaky = self.make_owner("9310000003", upi="REFSHOP@upi", referred_by=self.v)  # same UPI as the referrer's own shop
        self.pay(sneaky)
        self.assertEqual(Commission.objects.count(), 0)
        also = self.make_owner("9310000004", upi="ref@upi", referred_by=self.v)  # same UPI as the payout UPI
        self.pay(also)
        self.assertEqual(Commission.objects.count(), 0)

    def test_suspended_owner_vendor_earns_nothing_and_sees_no_wallet_numbers(self):
        Vendor.objects.filter(pk=self.v.pk).update(status="suspended")
        self.pay(self.friend)
        self.assertEqual(Commission.objects.count(), 0)
        self.login(self.referrer)
        self.assertEqual(self.client.get("/api/vendor/wallet/").data, {"status": "suspended"})

    def test_each_partner_only_sees_their_own_wallet(self):
        self.pay(self.friend)
        other = self.make_owner("9310000005", upi="o@upi")
        self.enrol(other, upi="other@upi")
        w = self.client.get("/api/vendor/wallet/").data
        self.assertEqual((w["balance"], w["ledger"]), (0, []))
