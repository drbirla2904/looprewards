import csv
import re
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from .models import (Business, BusinessReferralSettings, Commission, Payment, Payout, Subscription, User, Vendor,
                     get_sub, new_shop_code)


def active_paying_shops(v):
    """Referred owners whose subscription is currently paid up (retention counts, not sign-ups)."""
    return Subscription.objects.filter(owner__referred_by=v, paid_until__gt=timezone.now()).count()


def tier_for(v):
    n = active_paying_shops(v)
    ladder = sorted(settings.VENDOR_TIERS)
    cur = max((t for t in ladder if n >= t[0]), key=lambda t: t[0])
    nxt = next((t for t in ladder if t[0] > n), None)
    return {"name": cur[1], "bonus": cur[2], "active_shops": n, "next": nxt[1] if nxt else None,
            "next_at": nxt[0] if nxt else None, "to_next": (nxt[0] - n) if nxt else 0,
            "next_bonus": nxt[2] if nxt else None,
            "ladder": [{"name": t[1], "shops": t[0], "bonus": t[2]} for t in ladder]}


def effective_rate(v):
    """Base rate (set by admin) plus the tier bonus. Stored on each Commission, so past earnings never change."""
    return Decimal(v.rate) + Decimal(tier_for(v)["bonus"])


def business_referral_eligibility(v):
    """Return whether an owner can currently earn from businesses they referred."""
    enabled = BusinessReferralSettings.objects.get_or_create(pk=1)[0].enabled
    subscription = Subscription.objects.filter(owner=v.user, paid_until__gt=timezone.now()).first()
    latest_payment = Payment.objects.filter(owner=v.user, status="paid").order_by("-id").first()
    yearly_plan_active = bool(subscription and latest_payment and latest_payment.plan == "yearly")
    return {
        "enabled": enabled and yearly_plan_active,
        "program_enabled": enabled,
        "yearly_plan_active": yearly_plan_active,
    }


def _upi_ids(user):
    return {b.pay_upi_id.strip().lower() for b in user.businesses.all() if b.pay_upi_id.strip()}


def accrue(p):
    """Called when a payment is marked paid. Never on trials; single level; idempotent."""
    v = Vendor.objects.filter(pk=p.owner.referred_by_id, status="approved").select_related("user").first()
    if not v or v.user_id == p.owner_id:
        return
    if v.user.role == "owner" and not business_referral_eligibility(v)["enabled"]:
        return
    # self-referral guard: the partner's payout UPI or any of the partner's own shop UPIs must not match the payer's
    mine = {v.upi_id.strip().lower()} | _upi_ids(v.user)
    if mine & _upi_ids(p.owner):
        return
    if settings.COMMISSION_FIRST_YEAR_ONLY:
        first = p.owner.payments.filter(status="paid").order_by("id").first()
        if first and (p.created_at - first.created_at).days >= 365:
            return
    base = Decimal(p.amount) * 100 / (100 + settings.GST_RATE)  # paise ex-GST
    rate = effective_rate(v)
    commission_paise = int((base * rate / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    com, created = Commission.objects.get_or_create(payment=p, defaults={
        "vendor": v, "rate": rate, "amount": commission_paise,
        "payable_on": timezone.now() + timedelta(days=settings.COMMISSION_HOLD_DAYS)})
    if created:
        from .notify import push
        shop = p.owner.businesses.first()
        push(v.user, f"You earned \u20b9{com.amount / 100:,.2f} from {shop.name if shop else 'a business you referred'}. "
                     f"It is held for {settings.COMMISSION_HOLD_DAYS} days, then added to your wallet payout.",
             link="/app/#/refer" if v.user.role == "owner" else "/app/#/statements")


def reverse(p):  # refunded payment -> commission reversed unless already in a payout
    Commission.objects.filter(payment=p, status__in=("hold",)).update(status="reversed")


def _vendor(request, approved=True):
    v = getattr(request.user, "vendor", None)
    if not v or (approved and v.status != "approved"):
        raise PermissionDenied("Approved vendor account required.")
    return v


@api_view(["POST"])
def apply(request):
    pan, upi = str(request.data.get("pan", "")).upper().strip(), str(request.data.get("upi_id", "")).strip()
    if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan):
        raise ValidationError("Enter a valid 10-character PAN.")
    if not re.fullmatch(r"[^@\s]+@[^\s@]+", upi):
        raise ValidationError("Enter a valid UPI ID.")
    if request.user.role not in ("vendor", "owner") or hasattr(request.user, "vendor"):
        raise ValidationError("Not allowed.")
    auto = request.user.role == "owner" and settings.OWNER_REFERRAL_AUTO_APPROVE
    v = Vendor.objects.create(user=request.user, code=new_shop_code().upper(), pan=pan, upi_id=upi,
                              status="approved" if auto else "pending")
    return Response({"detail": "You can start referring now." if auto else "Submitted for approval.",
                     "status": v.status}, status=201)


@api_view(["PATCH"])
def profile(request):
    v = _vendor(request, approved=False)
    pan = str(request.data.get("pan", v.pan)).upper().strip()
    upi = str(request.data.get("upi_id", v.upi_id)).strip()
    name = str(request.data.get("name", request.user.first_name)).strip()
    if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan):
        raise ValidationError("Enter a valid 10-character PAN.")
    if not re.fullmatch(r"[^@\s]+@[^\s@]+", upi):
        raise ValidationError("Enter a valid UPI ID.")
    if len(name) > 150:
        raise ValidationError("Name is too long.")
    v.pan, v.upi_id = pan, upi
    v.save(update_fields=["pan", "upi_id"])
    request.user.first_name = name
    request.user.save(update_fields=["first_name"])
    return Response({"name": name, "pan": pan, "upi_id": upi, "status": v.status})


@api_view(["GET"])
def dashboard(request):
    v = getattr(request.user, "vendor", None)
    if not v:
        if request.user.role in ("vendor", "owner"):
            return Response({"status": "not_applied", "name": request.user.first_name,
                             "mobile": request.user.username})
        raise PermissionDenied("Vendor account required.")
    out = {"status": v.status, "code": v.code, "rate": v.rate, "effective_rate": effective_rate(v), "tier": tier_for(v),
           "name": request.user.first_name, "pan": v.pan, "upi_id": v.upi_id,
           "mobile": request.user.username, "applied_at": v.applied_at}
    if v.user.role == "owner":
        out["business_referral_earning"] = business_referral_eligibility(v)
    if v.status != "approved":
        return Response(out)
    totals = dict(v.commissions.values("status").annotate(total=Sum("amount")).values_list("status", "total"))
    owners = v.referrals.filter(role="owner").prefetch_related("businesses")
    owner_stats = owners.aggregate(
        total=Count("id", distinct=True),
        with_business=Count("id", filter=Q(businesses__isnull=False), distinct=True),
    )
    payouts = list(v.payouts.order_by("-created_at")[:12])
    commissions = v.commissions.select_related("payment").order_by("-payment__created_at")[:10]
    out["referral_url"] = request.build_absolute_uri(f"/app/?ref={v.code}")
    out["commission_paise"] = {status: totals.get(status, 0) or 0
                               for status in ("hold", "payable", "paid", "reversed")}
    out["referred_owner_count"] = owner_stats["total"]
    out["referred_shop_count"] = owner_stats["with_business"]
    out["commission_hold_days"] = settings.COMMISSION_HOLD_DAYS
    out["minimum_payout_paise"] = settings.MIN_PAYOUT_PAISE
    out["payout_schedule"] = "Monthly, on or after the 1st, once eligible commissions reach the minimum."
    out["payouts"] = [{"amount": p.amount, "status": p.status, "reference": p.reference,
                       "date": p.created_at.date()} for p in payouts]
    out["recent_commissions"] = [{
        "amount": c.amount, "status": c.status, "date": c.payment.created_at.date(),
        "plan": c.payment.plan, "payable_on": c.payable_on.date(),
    } for c in commissions]
    businesses = []
    since, now = timezone.now() - timedelta(days=30), timezone.now()
    approved = Q(customers__entries__status="approved")
    for owner in owners:
        subscription = get_sub(owner)
        until = subscription.paid_until or subscription.trial_ends
        shops = owner.businesses.annotate(
            customers_n=Count("customers", distinct=True), programs_n=Count("programs", distinct=True),
            last=Max("customers__entries__created_at", filter=approved),
            visits=Count("customers__entries", filter=approved & Q(customers__entries__created_at__gte=since), distinct=True))
        for business in shops:
            days = (now - business.last).days if business.last else None
            # aggregate numbers only: a partner never sees a shop's customers
            health = "new" if business.customers_n == 0 else "live" if days is not None and days <= 14 else "quiet" if days is not None and days <= 30 else "idle"
            businesses.append({"name": business.name, "owner": owner.first_name, "state": subscription.state, "until": until,
                               "customers": business.customers_n, "programs": business.programs_n, "visits_30d": business.visits,
                               "last_activity": business.last, "health": health})
    out["businesses"] = businesses
    return Response(out)


def _total(qs):
    return qs.aggregate(t=Sum("amount"))["t"] or 0


def wallet_summary(v):
    """Wallet view of a partner's earnings (all amounts in paise). Commission lifecycle:
    clearing (30-day hold) -> ready (waiting for the monthly payout run) -> processing (payout created, transfer
    pending) -> paid. `balance` is everything earned and not yet paid out."""
    now = timezone.now()
    c, paid = v.commissions, v.payouts.filter(status="paid")
    clearing = _total(c.filter(status="hold", payable_on__gt=now))
    ready = _total(c.filter(status="hold", payable_on__lte=now))
    processing = _total(c.filter(status="payable"))
    tds = paid.aggregate(t=Sum("tds"))["t"] or 0
    paid_gross = _total(paid)
    today = timezone.localdate()
    nxt = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    return {"balance": clearing + ready + processing, "clearing": clearing, "ready": ready, "processing": processing,
            "paid_gross": paid_gross, "tds": tds, "paid_net": paid_gross - tds, "reversed": _total(c.filter(status="reversed")),
            "minimum_payout": settings.MIN_PAYOUT_PAISE, "hold_days": settings.COMMISSION_HOLD_DAYS,
            "meets_minimum": ready >= settings.MIN_PAYOUT_PAISE, "next_payout": nxt}


def wallet_ledger(v, limit=40):
    rows = []
    coms = v.commissions.select_related("payment").prefetch_related("payment__owner__businesses").order_by("-payment__created_at")[:limit]
    for c in coms:
        shops = list(c.payment.owner.businesses.all())
        rows.append({"kind": "credit", "at": c.payment.created_at, "amount": c.amount, "status": c.status,
                     "label": shops[0].name if shops else "", "plan": c.payment.plan, "payable_on": c.payable_on.date()})
    for p in v.payouts.order_by("-created_at")[:limit]:
        rows.append({"kind": "payout", "at": p.paid_at or p.created_at, "amount": p.amount, "status": p.status,
                     "tds": p.tds, "net": (p.amount - p.tds) if p.status == "paid" else None, "reference": p.reference})
    rows.sort(key=lambda r: r["at"], reverse=True)
    return rows[:limit]


@api_view(["GET"])
def wallet(request):
    """Referral wallet for any approved partner: an agent (vendor) or a business owner who refers other businesses."""
    v = getattr(request.user, "vendor", None)
    if not v:
        if request.user.role in ("vendor", "owner"):
            return Response({"status": "not_applied"})
        raise PermissionDenied("Referral account required.")
    if v.status != "approved":
        return Response({"status": v.status})
    return Response({"status": "approved", **wallet_summary(v), "ledger": wallet_ledger(v)})


@api_view(["POST"])
@transaction.atomic
def assist(request):
    """Assisted registration: vendor creates the owner account + shop, owner gets the temp password."""
    v, d = _vendor(request), request.data
    mobile = str(d.get("mobile", "")).strip()
    if not mobile.isdigit() or len(mobile) < 10 or User.objects.filter(username=mobile).exists():
        raise ValidationError("Valid, unused owner mobile required.")
    upi = d.get("pay_upi_id", "")
    if upi and Business.objects.filter(pay_upi_id=upi).exists():
        raise ValidationError("This UPI ID is already registered.")
    owner_name = str(d.get("owner_name", "")).strip()
    if not owner_name:
        raise ValidationError("Owner name is required.")
    password = d.get("password")
    if not isinstance(password, str) or len(password) < 6:
        raise ValidationError("Set a password for the owner (at least 6 characters). They use it with their mobile number to log in.")
    if password == mobile:
        raise ValidationError("The password cannot be the same as the mobile number.")
    u = User.objects.create_user(username=mobile, password=password, first_name=owner_name,
                                 role="owner", referred_by=v)
    biz = Business.objects.create(owner=u, name=d.get("name", "My Shop"), category=d.get("category", "other"),
                                  address=d.get("address", ""), pay_upi_id=upi)
    from . import blueprints  # same ready-made starter program the owner wizard creates
    blueprints.apply(biz, d.get("category") if d.get("category") in blueprints.BLUEPRINTS else "other")
    return Response({"mobile": mobile, "shop_code": biz.shop_code}, status=201)  # the password is never sent back


@api_view(["POST"])
def change_password(request):
    old_password, new_password = request.data.get("old", ""), request.data.get("new", "")
    if (not isinstance(old_password, str) or not request.user.check_password(old_password)
            or not isinstance(new_password, str) or len(new_password) < 6):
        raise ValidationError("Wrong old password or new password too short.")
    request.user.set_password(new_password)
    request.user.save()
    return Response({"detail": "Changed."})


# ---------------------------------------------------------------- marketing kit
@api_view(["GET"])
def kit(request):
    v = _vendor(request)
    plans = {k: {"label": p["label"], "price": p["amount"] // 100, "days": p["days"]} for k, p in settings.PLANS.items()}
    return Response({"referral_url": request.build_absolute_uri(f"/app/?ref={v.code}"),
                     "flyer_url": f"/kit/{v.code}/", "flyer_url_hi": f"/kit/{v.code}/?lang=hi",
                     "plans": plans, "trial_days": settings.TRIAL_DAYS, "name": request.user.first_name})


# ---------------------------------------------------------------- payouts, TDS, statements
def fy_bounds(start_year):
    """Indian financial year: 1 April start_year to 31 March start_year+1, as aware datetimes."""
    tz = timezone.get_current_timezone()
    return (timezone.make_aware(datetime(start_year, 4, 1), tz), timezone.make_aware(datetime(start_year + 1, 4, 1), tz))


def fy_of(when):
    d = timezone.localtime(when)
    return d.year if d.month >= 4 else d.year - 1


@transaction.atomic
def mark_payout_paid(po, reference=""):
    """Record a payout as paid and withhold TDS if configured (VENDOR_TDS_RATE > 0 and the vendor's financial-year
    total crosses VENDOR_TDS_THRESHOLD_PAISE; once crossed, TDS also covers earlier untaxed payouts that year)."""
    po = Payout.objects.select_for_update().get(pk=po.pk)
    if po.status == "paid":
        return po
    now = timezone.now()
    rate = Decimal(str(settings.VENDOR_TDS_RATE or 0))
    tds = 0
    if rate > 0:
        start, end = fy_bounds(fy_of(now))
        prior = Payout.objects.filter(vendor=po.vendor, status="paid", paid_at__gte=start, paid_at__lt=end).exclude(pk=po.pk)
        before = prior.aggregate(t=Sum("amount"))["t"] or 0
        withheld = prior.aggregate(t=Sum("tds"))["t"] or 0
        total = before + po.amount
        if total > settings.VENDOR_TDS_THRESHOLD_PAISE:
            # once the yearly threshold is crossed TDS is due on the whole year's total, so catch up on earlier payouts
            tds = max(0, min(po.amount, int(total * rate / 100) - withheld))
    po.status, po.paid_at, po.tds = "paid", now, tds
    if reference:
        po.reference = reference
    po.save()
    po.commission_set.update(status="paid")
    from .notify import push
    push(po.vendor.user, f"Payout of \u20b9{(po.amount - tds) / 100:,.2f} has been sent" + (f" after TDS of \u20b9{tds / 100:,.2f}." if tds else "."))
    return po


@api_view(["GET"])
def statement(request):
    """Earnings statement for one financial year. ?fy=2026 means 1 Apr 2026 - 31 Mar 2027. ?download=csv for a file."""
    v = _vendor(request, approved=False)
    try:
        fy = int(request.GET.get("fy", fy_of(timezone.now())))
    except ValueError:
        raise ValidationError("Invalid financial year.")
    start, end = fy_bounds(fy)
    coms = v.commissions.filter(payment__created_at__gte=start, payment__created_at__lt=end).select_related(
        "payment__owner").order_by("payment__created_at")
    pays = v.payouts.filter(status="paid", paid_at__gte=start, paid_at__lt=end).order_by("paid_at")
    rows = []
    for c in coms:
        shop = c.payment.owner.businesses.first()
        rows.append({"date": timezone.localtime(c.payment.created_at).date().isoformat(), "shop": shop.name if shop else "",
                     "plan": c.payment.plan, "base": int(Decimal(c.payment.amount) * 100 / (100 + settings.GST_RATE)),
                     "rate": str(c.rate), "commission": c.amount, "status": c.status})
    payouts = [{"date": timezone.localtime(p.paid_at).date().isoformat(), "gross": p.amount, "tds": p.tds,
                "net": p.amount - p.tds, "reference": p.reference} for p in pays]
    totals = {"earned": sum(r["commission"] for r in rows if r["status"] != "reversed"),
              "reversed": sum(r["commission"] for r in rows if r["status"] == "reversed"),
              "paid_gross": sum(p["gross"] for p in payouts), "tds": sum(p["tds"] for p in payouts),
              "paid_net": sum(p["net"] for p in payouts)}
    if request.GET.get("download") == "csv":
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="partner-statement-{v.code}-FY{fy}-{str(fy + 1)[2:]}.csv"'
        w = csv.writer(resp)
        w.writerow(["Partner", request.user.first_name, "Code", v.code, "PAN", v.pan, f"FY {fy}-{str(fy + 1)[2:]}"])
        w.writerow([]); w.writerow(["COMMISSIONS (amounts in INR)"])
        w.writerow(["Payment date", "Shop", "Plan", "Subscription ex-GST", "Rate %", "Commission", "Status"])
        for r in rows:
            w.writerow([r["date"], r["shop"], r["plan"], f"{r['base'] / 100:.2f}", r["rate"], f"{r['commission'] / 100:.2f}", r["status"]])
        w.writerow([]); w.writerow(["PAYOUTS (amounts in INR)"])
        w.writerow(["Paid on", "Gross", "TDS withheld", "Net received", "Reference"])
        for p in payouts:
            w.writerow([p["date"], f"{p['gross'] / 100:.2f}", f"{p['tds'] / 100:.2f}", f"{p['net'] / 100:.2f}", p["reference"]])
        w.writerow(["Total", f"{totals['paid_gross'] / 100:.2f}", f"{totals['tds'] / 100:.2f}", f"{totals['paid_net'] / 100:.2f}", ""])
        return resp
    first = v.commissions.order_by("payment__created_at").first()
    years = sorted({fy_of(timezone.now())} | ({fy_of(first.payment.created_at)} if first else set()), reverse=True)
    years = list(range(max(years), min(years) - 1, -1))
    return Response({"fy": fy, "years": years, "pan": v.pan, "commissions": rows, "payouts": payouts, "totals": totals,
                     "tds_note": "TDS withheld is reported to the tax department against your PAN; check it in Form 26AS / AIS."})
