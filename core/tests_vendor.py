"""Tests for partner tiers, shop activity, marketing kit, TDS payouts and statements."""
from decimal import Decimal

from django.test import override_settings
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APITestCase

from . import vendors
from .models import (Business, Commission, CustomerProfile, Payment, Payout, Program, PurchaseEntry, Subscription, Task,
                     User, Vendor, get_sub)


class VendorBase(APITestCase):
    def make_vendor(self, mobile="9200000001", status="approved"):
        r = self.client.post("/api/auth/register/", {"mobile": mobile, "password": "secret1", "role": "vendor", "name": "Vik", "accepted": True})
        self.client.credentials(HTTP_AUTHORIZATION="Token " + r.data["token"])
        self.client.post("/api/vendor/apply/", {"pan": "ABCDE1234F", "upi_id": "vik@upi"})
        Vendor.objects.update(status=status, rate=20)
        self.vendor = Vendor.objects.get(user__username=mobile)
        self.tok = "Token " + r.data["token"]
        return self.vendor

    def referred_owner(self, mobile, paid=True, shop=True):
        o = User.objects.create_user(username=mobile, password="x", role="owner", first_name="Own" + mobile[-2:], referred_by=self.vendor)
        if shop:
            Business.objects.create(owner=o, name="Shop" + mobile[-2:], pay_upi_id=f"s{mobile}@upi")
        if paid:
            s = get_sub(o)
            s.paid_until = timezone.now() + timedelta(days=20)
            s.save()
        return o

    def pay(self, owner, amount=9900):
        return Payment.objects.create(owner=owner, plan="monthly", amount=amount, method="gateway", status="paid")

    def auth(self):
        self.client.credentials(HTTP_AUTHORIZATION=self.tok)


class TierTests(VendorBase):
    def test_starter_rate_is_the_base_rate_and_commission_amount_is_exact(self):
        v = self.make_vendor()
        vendors.accrue(self.pay(self.referred_owner("9200000010")))
        c = Commission.objects.get()
        self.assertEqual(c.rate, Decimal("20"))
        base = Decimal(9900) * 100 / 118
        self.assertEqual(c.amount, int(base * 20 / 100))
        self.assertEqual(vendors.tier_for(v)["name"], "Starter")

    def test_tier_bonus_applies_from_active_paying_shops_and_is_frozen_on_each_commission(self):
        v = self.make_vendor()
        owners = [self.referred_owner(f"92000001{i:02d}") for i in range(5)]
        t = vendors.tier_for(v)
        self.assertEqual((t["name"], t["bonus"], t["active_shops"], t["next"], t["to_next"]), ("Silver", 2, 5, "Gold", 10))
        vendors.accrue(self.pay(owners[0]))
        self.assertEqual(Commission.objects.get().rate, Decimal("22"))
        for o in owners[1:]:  # shops lapse: tier drops, the earlier commission keeps its rate
            Subscription.objects.filter(owner=o).update(paid_until=timezone.now() - timedelta(days=1))
        Subscription.objects.filter(owner=owners[0]).update(paid_until=timezone.now() - timedelta(days=1))
        self.assertEqual(vendors.tier_for(v)["name"], "Starter")
        self.assertEqual(Commission.objects.get().rate, Decimal("22"))

    def test_trial_shops_do_not_count(self):
        v = self.make_vendor()
        for i in range(6):
            self.referred_owner(f"92000002{i:02d}", paid=False)
        self.assertEqual(vendors.active_paying_shops(v), 0)

    def test_dashboard_exposes_tier_and_effective_rate(self):
        self.make_vendor()
        for i in range(5):
            self.referred_owner(f"92000003{i:02d}")
        d = self.client.get("/api/vendor/dashboard/").data
        self.assertEqual(d["tier"]["name"], "Silver")
        self.assertEqual(Decimal(d["effective_rate"]), Decimal("22"))
        self.assertEqual(Decimal(d["rate"]), Decimal("20"))


class ShopActivityTests(VendorBase):
    def test_health_levels_and_no_customer_details_leak(self):
        self.make_vendor()
        quiet = self.referred_owner("9200000400")
        biz = quiet.businesses.first()
        d = self.client.get("/api/vendor/dashboard/").data["businesses"][0]
        self.assertEqual((d["health"], d["customers"], d["visits_30d"]), ("new", 0, 0))
        prog = Program.objects.create(business=biz, title="P")
        task = Task.objects.create(program=prog, title="T", type="visit", target=5)
        cust = User.objects.create_user(username="9200000401", password="x", role="customer", first_name="Secret Name")
        prof = CustomerProfile.objects.create(user=cust, business=biz)
        PurchaseEntry.objects.create(profile=prof, task=task, value=1, status="approved")
        d = self.client.get("/api/vendor/dashboard/").data["businesses"][0]
        self.assertEqual((d["health"], d["customers"], d["visits_30d"], d["programs"]), ("live", 1, 1, 1))
        self.assertNotIn("Secret Name", str(d))
        self.assertNotIn("9200000401", str(d))
        PurchaseEntry.objects.update(created_at=timezone.now() - timedelta(days=20))
        self.assertEqual(self.client.get("/api/vendor/dashboard/").data["businesses"][0]["health"], "quiet")
        PurchaseEntry.objects.update(created_at=timezone.now() - timedelta(days=50))
        self.assertEqual(self.client.get("/api/vendor/dashboard/").data["businesses"][0]["health"], "idle")


class KitTests(VendorBase):
    def test_kit_requires_approved_vendor(self):
        self.make_vendor(status="pending")
        self.assertEqual(self.client.get("/api/vendor/kit/").status_code, 403)
        Vendor.objects.update(status="approved")
        d = self.client.get("/api/vendor/kit/").data
        self.assertIn(self.vendor.code, d["referral_url"])
        self.assertEqual(d["plans"]["monthly"]["price"], 99)

    def test_flyer_is_public_for_approved_vendors_only_and_escapes_names(self):
        v = self.make_vendor()
        User.objects.filter(pk=v.user_id).update(first_name='<script>x</script>')
        self.client.credentials()
        r = self.client.get(f"/kit/{v.code}/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "<svg")
        self.assertContains(r, v.code)
        self.assertNotContains(r, "<script>x</script>")
        self.assertContains(self.client.get(f"/kit/{v.code}/?lang=hi"), "ग्राहकों को वापस लाइए")
        self.assertEqual(self.client.get("/kit/NOPE/").status_code, 404)
        Vendor.objects.update(status="suspended")
        self.assertEqual(self.client.get(f"/kit/{v.code}/").status_code, 404)

    def test_assisted_shop_gets_a_starter_program(self):
        self.make_vendor()
        r = self.client.post("/api/vendor/assist/", {"owner_name": "Mina", "mobile": "9200000500", "name": "Glow", "category": "salon", "password": "secret1"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        biz = Business.objects.get(name="Glow")
        self.assertEqual(biz.programs.count(), 1)
        self.assertEqual(biz.services.count(), 4)
        self.assertTrue(biz.bookings_enabled)
        r = self.client.post("/api/vendor/assist/", {"owner_name": "Z", "mobile": "9200000501", "name": "Odd", "category": "weird", "password": "secret1"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Business.objects.get(name="Odd").programs.count(), 1)  # unknown type falls back to "other"
        r = self.client.post("/api/vendor/assist/", {"owner_name": "Ravi", "mobile": "9200000502", "name": "Green Fields", "category": "agri_inputs", "password": "secret1"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        agricultural_shop = Business.objects.get(name="Green Fields")
        self.assertEqual(agricultural_shop.category, "agri_inputs")
        self.assertEqual(agricultural_shop.programs.count(), 1)


class PayoutTdsTests(VendorBase):
    def payout(self, amount):
        return Payout.objects.create(vendor=self.vendor, amount=amount)

    def test_tds_off_by_default(self):
        self.make_vendor()
        po = vendors.mark_payout_paid(self.payout(60000))
        self.assertEqual((po.status, po.tds), ("paid", 0))
        self.assertIsNotNone(po.paid_at)

    @override_settings(VENDOR_TDS_RATE="10", VENDOR_TDS_THRESHOLD_PAISE=100000)
    def test_tds_starts_after_yearly_threshold_and_catches_up(self):
        self.make_vendor()
        self.assertEqual(vendors.mark_payout_paid(self.payout(60000)).tds, 0)       # 60,000 total: below threshold
        self.assertEqual(vendors.mark_payout_paid(self.payout(60000)).tds, 12000)   # 120,000 total: 10% of everything
        self.assertEqual(vendors.mark_payout_paid(self.payout(10000)).tds, 1000)    # only this payout's share is new
        self.assertEqual(sum(Payout.objects.values_list("tds", flat=True)), 13000)  # = 10% of 130,000

    @override_settings(VENDOR_TDS_RATE="10", VENDOR_TDS_THRESHOLD_PAISE=0)
    def test_marking_paid_twice_is_a_no_op_and_commissions_become_paid(self):
        v = self.make_vendor()
        c = Commission.objects.create(payment=self.pay(self.referred_owner("9200000600")), vendor=v, rate=20, amount=5000, status="payable", payable_on=timezone.now())
        po = self.payout(5000)
        Commission.objects.filter(pk=c.pk).update(payout=po)
        vendors.mark_payout_paid(po)
        vendors.mark_payout_paid(po)
        po.refresh_from_db()
        self.assertEqual(po.tds, 500)
        c.refresh_from_db()
        self.assertEqual(c.status, "paid")

    def test_admin_action_uses_tds_logic(self):
        from django.contrib import admin
        from .admin import PayoutAdmin
        self.make_vendor()
        po = self.payout(1000)
        with override_settings(VENDOR_TDS_RATE="10", VENDOR_TDS_THRESHOLD_PAISE=0):
            PayoutAdmin(Payout, admin.site).paid(None, Payout.objects.filter(pk=po.pk))
        po.refresh_from_db()
        self.assertEqual((po.status, po.tds), ("paid", 100))


class StatementTests(VendorBase):
    def test_statement_totals_csv_and_privacy(self):
        v = self.make_vendor()
        o = self.referred_owner("9200000700")
        vendors.accrue(self.pay(o))
        po = Payout.objects.create(vendor=v, amount=60000, status="paid", paid_at=timezone.now(), tds=3000, reference="UTR9")
        other = User.objects.create_user(username="9200000799", password="x", role="vendor")
        d = self.client.get("/api/vendor/statement/").data
        self.assertEqual(len(d["commissions"]), 1)
        self.assertEqual(d["totals"]["paid_gross"], 60000)
        self.assertEqual((d["totals"]["tds"], d["totals"]["paid_net"]), (3000, 57000))
        self.assertEqual(d["commissions"][0]["shop"], "Shop00")
        self.assertIn(vendors.fy_of(timezone.now()), d["years"])
        r = self.client.get("/api/vendor/statement/?download=csv")
        self.assertEqual(r["Content-Type"], "text/csv")
        body = r.content.decode()
        self.assertIn("UTR9", body)
        self.assertIn("ABCDE1234F", body)
        self.assertEqual(self.client.get("/api/vendor/statement/?fy=abc").status_code, 400)
        self.assertEqual(self.client.get("/api/vendor/statement/?fy=1999").data["commissions"], [])

    def test_other_vendor_sees_only_their_own_statement_and_customers_are_blocked(self):
        v = self.make_vendor()
        vendors.accrue(self.pay(self.referred_owner("9200000710")))
        r = self.client.post("/api/auth/register/", {"mobile": "9200000711", "password": "secret1", "role": "vendor", "name": "B", "accepted": True})
        self.client.credentials(HTTP_AUTHORIZATION="Token " + r.data["token"])
        self.client.post("/api/vendor/apply/", {"pan": "ABCDE1234G", "upi_id": "b@upi"})
        self.assertEqual(self.client.get("/api/vendor/statement/").data["commissions"], [])
        c = self.client.post("/api/auth/register/", {"mobile": "9200000712", "password": "secret1", "role": "customer", "name": "C", "accepted": True})
        self.client.credentials(HTTP_AUTHORIZATION="Token " + c.data["token"])
        self.assertEqual(self.client.get("/api/vendor/statement/").status_code, 403)

    def test_fy_bounds(self):
        s, e = vendors.fy_bounds(2026)
        self.assertEqual((timezone.localtime(s).month, timezone.localtime(s).day, timezone.localtime(e).year), (4, 1, 2027))
        self.assertEqual(vendors.fy_of(timezone.make_aware(timezone.datetime(2027, 3, 31, 12))), 2026)
        self.assertEqual(vendors.fy_of(timezone.make_aware(timezone.datetime(2027, 4, 1, 1))), 2027)
