import base64, hashlib, hmac, json, urllib.parse, urllib.request
from datetime import timedelta
from math import ceil
import io
import uuid
import segno
from django import forms
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from decimal import Decimal
from django.core import signing
from django.shortcuts import get_object_or_404, render
from django.db.models import F
from .models import GatewayPlan, Payment, RewardGrant, Subscription, get_sub
from .notify import push
import logging
log = logging.getLogger("billing")


@transaction.atomic
def mark_paid(pk, gateway_payment_id=""):
    p = Payment.objects.select_for_update().get(pk=pk)
    if p.status == "paid":
        return p  # idempotent (webhook + client verify can both arrive)
    p.status, p.payment_id = "paid", gateway_payment_id or p.payment_id
    p.invoice_no = f"LR/{timezone.now():%y}/{p.id:06d}"
    p.save()
    sub = get_sub(p.owner)
    now = timezone.now()
    old_end = sub.paid_until or sub.trial_ends
    lapse = max(timedelta(0), now - old_end)  # how long the shop was paused
    base = max(now, old_end)  # no back-charge for the gap, no overlap with trial
    sub.paid_until = base + timedelta(days=settings.PLANS[p.plan]["days"])
    sub.save()
    if lapse > timedelta(0):  # returning shop: keep customers whole, extend their reward dates by the paused time
        RewardGrant.objects.filter(profile__business__owner=p.owner, status="active", expires_at__gt=old_end).update(
            expires_at=F("expires_at") + lapse)
        push(p.owner, "Welcome back! Your shop is live again with all your customers and rewards.", link="/app/#/")
    from .vendors import accrue
    accrue(p)
    if lapse <= timedelta(0):
        push(p.owner, f"Payment received. Your plan is active until {sub.paid_until:%d %b %Y}. Invoice {p.invoice_no}.", link="/app/#/billing")
    return p


@transaction.atomic
def revoke_period(pk):
    """Refund: take the paid period back (never below the end of the free trial) and tell the owner."""
    p = Payment.objects.select_for_update().get(pk=pk)
    if p.status != "paid":
        return p
    p.status = "refunded"
    p.save()
    sub = get_sub(p.owner)
    if sub.paid_until:
        new_end = sub.paid_until - timedelta(days=settings.PLANS.get(p.plan, {}).get("days", 0))
        still_paid = Payment.objects.filter(owner=p.owner, status="paid").exists()
        sub.paid_until = new_end if (still_paid or new_end > sub.trial_ends) else None
        sub.save(update_fields=["paid_until"])
    push(p.owner, f"Your payment {p.invoice_no or '#' + str(p.pk)} was refunded and the paid period was removed.", link="/app/#/billing")
    from .vendors import reverse
    reverse(p)
    return p


def _plan(name):
    if name not in settings.PLANS:
        raise ValidationError("Unknown plan.")
    return settings.PLANS[name]


def upi_link(plan, owner_id):
    if not settings.PLATFORM_UPI_ID:
        raise ValidationError("Manual UPI payments are not configured.")
    q = urllib.parse.urlencode({"pa": settings.PLATFORM_UPI_ID, "pn": settings.PLATFORM_UPI_NAME,
        "am": _plan(plan)["amount"] / 100, "cu": "INR", "tn": f"LOOP{owner_id}"})
    return "upi://pay?" + q


@api_view(["GET"])
def status(request):
    s = get_sub(request.user)
    now = timezone.now()
    end = s.paid_until or s.trial_ends
    grace_ends = end + timedelta(days=settings.GRACE_DAYS)
    data_until = grace_ends + timedelta(days=30 * settings.RETENTION_MONTHS)
    pending = request.user.payments.filter(method="upi", status="pending").order_by("-created_at").values(
        "plan", "amount", "created_at", "utr").first()
    gateway_available = bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)
    autopay_available = gateway_available  # plans are created on demand, so the API keys are all that is needed
    rej = request.user.payments.filter(method="upi", status="rejected").order_by("-created_at").first()
    newer_paid = rej and request.user.payments.filter(status__in=("paid", "pending"), created_at__gt=rej.created_at).exists()
    rejected = {"plan": rej.plan, "amount": rej.amount, "utr": rej.utr, "created_at": rej.created_at} \
        if rej and not newer_paid and now - rej.created_at < timedelta(days=14) else None
    m, y = settings.PLANS.get("monthly"), settings.PLANS.get("yearly")
    yearly_saving = max(0, m["amount"] * 12 - y["amount"]) if m and y else 0
    payment_mode = "test" if settings.RAZORPAY_KEY_ID.startswith("rzp_test_") else "live" if gateway_available else "unconfigured"
    return Response({"state": s.state, "ends": end, "grace_ends": grace_ends,
        "data_until": data_until, "days_until_end": max(0, ceil((end - now).total_seconds() / 86400)),
        "days_until_data_deletion": max(0, ceil((data_until - now).total_seconds() / 86400)),
        "grace_days": settings.GRACE_DAYS, "retention_months": settings.RETENTION_MONTHS,
        "plans": settings.PLANS, "payment_methods": {
            "online": gateway_available, "upi": bool(settings.PLATFORM_UPI_ID)},
        "upi_links": {plan: upi_link(plan, request.user.pk) for plan in settings.PLANS}
                    if settings.PLATFORM_UPI_ID else {},
        "payment_mode": payment_mode,
        "pending_payment": pending,
        "razorpay_key": settings.RAZORPAY_KEY_ID, "upi_id": settings.PLATFORM_UPI_ID,
        "owner_ref": request.user.id, "autopay": autopay_available,
        "autopay_pending": bool(s.rzp_sub_id and not s.rzp_autorenew_active),
        "autorenew": bool(s.rzp_sub_id and s.rzp_autorenew_active),
        "invoices": [{"no": p.invoice_no, "url": "/invoice/" + signing.dumps(p.pk, salt="inv") + "/"}
                     for p in request.user.payments.filter(status="paid").order_by("-id")[:12]],
        "payments": [{"id": p.pk, "plan": p.plan, "amount": p.amount, "method": p.method, "status": p.status,
                      "created_at": p.created_at, "invoice_no": p.invoice_no}
                     for p in request.user.payments.exclude(status="created").order_by("-id")[:10]],
        "last_rejected": rejected, "trial_days": settings.TRIAL_DAYS,
        "trial_ends": s.trial_ends, "yearly_saving": yearly_saving,
        "next_charge": s.paid_until or s.trial_ends if (s.rzp_sub_id and s.rzp_autorenew_active) else None})


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def public_plans(request):
    """Prices for the logged-out landing page. Same numbers the billing screen charges."""
    return Response({"plans": settings.PLANS, "trial_days": settings.TRIAL_DAYS, "gst_included": True})


@api_view(["POST"])
def create_order(request):
    if request.user.role != "owner":
        raise PermissionDenied("Owner account required.")
    plan = request.data.get("plan")
    selected_plan = _plan(plan)
    if not (settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET):
        raise ValidationError("Razorpay checkout is not configured.")
    order = _rzp_post("orders", {"amount": selected_plan["amount"], "currency": "INR",
        "receipt": f"lr-{request.user.pk}-{uuid.uuid4().hex[:12]}",
        "notes": {"owner_id": str(request.user.pk), "plan": plan}})
    Payment.objects.create(owner=request.user, plan=plan, amount=selected_plan["amount"],
        method="gateway", status="created", order_id=order["id"])
    return Response({"order_id": order["id"], "amount": selected_plan["amount"],
        "currency": "INR", "key": settings.RAZORPAY_KEY_ID})


@api_view(["POST"])
def verify(request):
    if request.user.role != "owner":
        raise PermissionDenied("Owner account required.")
    order_id = str(request.data.get("razorpay_order_id", ""))
    payment_id = str(request.data.get("razorpay_payment_id", ""))
    signature = str(request.data.get("razorpay_signature", ""))
    payment = Payment.objects.filter(owner=request.user, method="gateway", order_id=order_id).first()
    expected = hmac.new(settings.RAZORPAY_KEY_SECRET.encode(),
        f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
    if not payment or not order_id or not payment_id or not hmac.compare_digest(expected, signature):
        raise ValidationError("Payment could not be verified.")
    if payment.status == "paid" and payment.payment_id == payment_id:
        return Response({"detail": "Payment already confirmed.", "status": "paid"})
    if payment.status != "created":
        raise ValidationError("This payment order is no longer payable.")
    if Payment.objects.filter(payment_id=payment_id).exclude(pk=payment.pk).exists():
        raise ValidationError("This payment has already been applied.")
    mark_paid(payment.pk, payment_id)
    return Response({"detail": "Payment confirmed.", "status": "paid"})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([])  # never throttle the payment gateway
def webhook(request):
    """Razorpay -> us. Set events payment.captured / order.paid. Source of truth for payments."""
    sig = request.headers.get("X-Razorpay-Signature", "")
    good = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), request.body, hashlib.sha256).hexdigest()
    if not settings.RAZORPAY_WEBHOOK_SECRET or not hmac.compare_digest(good, sig):
        return HttpResponse(status=400)
    try:
        ev = json.loads(request.body)
    except ValueError:
        return HttpResponse(status=400)
    pay = ev.get("payload", {}).get("payment", {}).get("entity", {})
    if ev.get("event") in ("subscription.cancelled", "subscription.halted", "subscription.completed"):
        se = ev["payload"].get("subscription", {}).get("entity", {})
        for s in Subscription.objects.filter(rzp_sub_id=se.get("id", "x")).select_related("owner"):
            s.rzp_sub_id = ""
            s.rzp_autorenew_active = False
            s.save()
            if ev["event"] == "subscription.halted":
                push(s.owner, "Your auto-renew payment failed. Please renew from the dashboard to keep your shop live.", link="/app/#/billing")
    if ev.get("event") in ("subscription.authenticated", "subscription.activated"):
        se = ev.get("payload", {}).get("subscription", {}).get("entity", {})
        Subscription.objects.filter(rzp_sub_id=se.get("id", "x")).update(rzp_autorenew_active=True)
    if ev.get("event") == "subscription.charged":  # auto-renew charge
        se = ev["payload"].get("subscription", {}).get("entity", {})
        plan = plan_for_rzp_id(se.get("plan_id"))
        with transaction.atomic():  # the row lock makes a duplicate webhook delivery wait, then see the payment and stop
            sub = Subscription.objects.select_for_update().filter(rzp_sub_id=se.get("id", "x")).select_related("owner").first()
            if sub and plan and pay.get("id") and not Payment.objects.filter(payment_id=pay["id"]).exists():
                p = Payment.objects.create(owner=sub.owner, plan=plan, method="gateway", status="pending",
                    amount=pay.get("amount") or settings.PLANS[plan]["amount"], order_id=pay.get("order_id") or "")
                mark_paid(p.pk, pay["id"])
    if ev.get("event") == "payment.failed":  # tell the owner right away instead of leaving them guessing
        order_id = pay.get("order_id")
        failed = Payment.objects.filter(method="gateway", order_id=order_id, status="created").select_related("owner").first() if order_id else None
        if failed:
            push(failed.owner, "Your payment did not go through, so you were not charged for a new plan. Please try again from Billing.", link="/app/#/billing")
    if ev.get("event") in ("payment.captured", "order.paid"):
        order = ev.get("payload", {}).get("order", {}).get("entity", {})
        order_id = pay.get("order_id") or order.get("id")
        captured_amount = pay.get("amount") or order.get("amount_paid")
        payment = Payment.objects.filter(method="gateway", order_id=order_id, status="created").first()
        if (payment and pay.get("id") and captured_amount == payment.amount
                and pay.get("currency", "INR") == "INR"):
            mark_paid(payment.pk, pay["id"])
    return HttpResponse("ok")


@api_view(["POST"])
def upi_submit(request):
    if request.user.role != "owner":
        raise PermissionDenied("Owner account required.")
    if not settings.PLATFORM_UPI_ID:
        raise ValidationError("Manual UPI payments are not configured.")
    plan = request.data.get("plan")
    selected_plan = _plan(plan)
    utr = str(request.data.get("utr", "")).strip()
    proof = request.FILES.get("proof")
    if not utr or len(utr) > 20:
        raise ValidationError({"utr": "Enter the UPI transaction reference (up to 20 characters)."})
    if not proof:
        raise ValidationError({"proof": "Upload a screenshot of the completed UPI payment."})
    if proof.size > 5 * 1024 * 1024:
        raise ValidationError({"proof": "Screenshot must be 5 MB or smaller."})
    try:
        proof = forms.ImageField().clean(proof)
    except forms.ValidationError as exc:
        raise ValidationError({"proof": "Upload a valid image screenshot."}) from exc
    extension = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}.get(proof.image.format)
    if not extension:
        raise ValidationError({"proof": "Screenshot must be a JPEG, PNG, or WebP image."})
    proof.name = "payment" + extension
    if Payment.objects.filter(owner=request.user, method="upi", status="pending").exists():
        raise ValidationError("A UPI payment is already awaiting review.")
    if Payment.objects.filter(utr__iexact=utr, status__in=("pending", "paid")).exists():
        raise ValidationError({"utr": "This transaction reference has already been submitted."})
    payment = Payment.objects.create(owner=request.user, plan=plan, amount=selected_plan["amount"],
        method="upi", status="pending", utr=utr, proof=proof)
    return Response({"detail": "UPI payment submitted for admin verification.",
        "payment_id": payment.pk, "status": payment.status}, status=201)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def upi_qr(request):
    if not settings.PLATFORM_UPI_ID:
        raise ValidationError("Manual UPI payments are not configured.")
    buf = io.BytesIO()
    try:
        owner_id = int(request.GET.get("ref", 0) or 0)
    except ValueError as exc:
        raise ValidationError("Invalid payment reference.") from exc
    segno.make(upi_link(request.GET.get("plan"), owner_id), error="m").save(
        buf, kind="png", scale=8, border=3)
    return HttpResponse(buf.getvalue(), content_type="image/png")


def invoice(request, token):
    try:
        pk = signing.loads(token, salt="inv")
    except signing.BadSignature:
        return HttpResponse(status=404)
    p = get_object_or_404(Payment, pk=pk, status="paid")
    gross = Decimal(p.amount) / 100
    base = (gross * 100 / (100 + settings.GST_RATE)).quantize(Decimal("0.01"))
    return render(request, "invoice.html", {"p": p, "seller": settings.SELLER, "rate": settings.GST_RATE,
                  "gross": gross, "base": base, "gst": gross - base})


def plan_id(plan):
    """Razorpay plan id for one of our plans. A value in the environment wins; otherwise the plan is created once through the
    API and remembered (and re-created if the price changes). Raises a friendly error if Razorpay cannot be reached."""
    configured = settings.RZP_PLAN_IDS.get(plan)
    if configured:
        return configured
    spec = settings.PLANS[plan]
    cached = GatewayPlan.objects.filter(plan=plan).first()
    if cached and cached.amount == spec["amount"]:
        return cached.rzp_plan_id
    created = _rzp_post("plans", {"period": "monthly" if plan == "monthly" else "yearly", "interval": 1,
        "item": {"name": f"OFFLet {spec['label']}", "amount": spec["amount"], "currency": "INR",
                 "description": f"OFFLet {spec['label']} subscription (GST included)"}})
    GatewayPlan.objects.update_or_create(plan=plan, defaults={"rzp_plan_id": created["id"], "amount": spec["amount"]})
    return created["id"]


def plan_for_rzp_id(rzp_id):
    """Our plan key for a Razorpay plan id (webhooks), whether it came from the environment or was auto-created."""
    if not rzp_id:
        return None
    for k, v in settings.RZP_PLAN_IDS.items():
        if v and v == rzp_id:
            return k
    row = GatewayPlan.objects.filter(rzp_plan_id=rzp_id).first()
    return row.plan if row else None


def _rzp_post(path, body):
    auth = base64.b64encode(f"{settings.RAZORPAY_KEY_ID}:{settings.RAZORPAY_KEY_SECRET}".encode()).decode()
    req = urllib.request.Request("https://api.razorpay.com/v1/" + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Basic " + auth})
    try:
        return json.load(urllib.request.urlopen(req, timeout=15))
    except Exception as exc:  # network error, 4xx/5xx from Razorpay: never leak a 500 to the owner
        log.exception("razorpay %s failed", path)
        raise ValidationError("The payment service could not be reached. Please try again in a minute.") from exc


@api_view(["POST"])
def autopay(request):
    """Auto-renew via Razorpay Subscriptions (UPI AutoPay / cards). First charge happens after the trial/paid period."""
    if request.user.role != "owner":
        raise PermissionDenied("Owner account required.")
    plan = request.data.get("plan")
    _plan(plan)
    if not (settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET):
        raise ValidationError("Auto-renew is not configured.")
    pid = plan_id(plan)
    sub = get_sub(request.user)
    if sub.rzp_sub_id:
        raise ValidationError("An AutoPay setup is already active or pending. Cancel it before starting another.")
    body = {"plan_id": pid, "total_count": 120 if plan == "monthly" else 10, "customer_notify": 1}
    start = sub.paid_until or sub.trial_ends
    if start > timezone.now() + timedelta(minutes=5):
        body["start_at"] = int(start.timestamp())
    sub.rzp_sub_id = _rzp_post("subscriptions", body)["id"]
    sub.rzp_autorenew_active = False
    sub.save()
    return Response({"subscription_id": sub.rzp_sub_id, "key": settings.RAZORPAY_KEY_ID})


@api_view(["POST"])
def autopay_verify(request):
    if request.user.role != "owner":
        raise PermissionDenied("Owner account required.")
    subscription_id = str(request.data.get("razorpay_subscription_id", ""))
    payment_id = str(request.data.get("razorpay_payment_id", ""))
    signature = str(request.data.get("razorpay_signature", ""))
    expected = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(),
        f"{subscription_id}|{payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    sub = get_sub(request.user)
    if not subscription_id or not payment_id or not hmac.compare_digest(expected, signature):
        raise ValidationError("AutoPay authorization could not be verified.")
    if sub.rzp_sub_id != subscription_id:
        raise ValidationError("AutoPay authorization does not match this account.")
    sub.rzp_autorenew_active = True
    sub.save(update_fields=["rzp_autorenew_active"])
    return Response({"autorenew": True})


@api_view(["POST"])
def autopay_cancel(request):
    if request.user.role != "owner":
        raise PermissionDenied("Owner account required.")
    sub = get_sub(request.user)
    if sub.rzp_sub_id:
        _rzp_post(f"subscriptions/{sub.rzp_sub_id}/cancel", {"cancel_at_cycle_end": 0})
        sub.rzp_sub_id = ""
        sub.rzp_autorenew_active = False
        sub.save()
    return Response({"detail": "Auto-renew cancelled."})
