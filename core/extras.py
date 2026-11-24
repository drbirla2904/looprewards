import hashlib, logging, secrets, smtplib
from datetime import timedelta
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from .throttles import AuthThrottle
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from . import services
from decimal import Decimal, InvalidOperation
from django.db.models import Q
from .models import (AuditLog, Business, CustomerProfile, OtpCode, Payment, Program, PurchaseEntry, Reward, RewardGrant,
                     Subscription, Task, TaskProgress, User, Vendor)
from .notify import announce_shop_customers, notify, push
from .serializers import BusinessSerializer, EntrySerializer, ProfileImageSerializer

log = logging.getLogger(__name__)


@api_view(["PATCH"])
def business_settings(request, code):
    biz = get_object_or_404(Business, shop_code=code, owner=request.user)
    upi = request.data.get("pay_upi_id")
    if upi and Business.objects.filter(pay_upi_id=upi).exclude(pk=biz.pk).exists():
        raise ValidationError("This UPI ID is already registered.")
    s = BusinessSerializer(biz, data=request.data, partial=True)
    s.is_valid(raise_exception=True)
    s.save()
    return Response(s.data)


@api_view(["PATCH", "DELETE"])
@transaction.atomic
def program_update(request, pk):  # pause / resume / end / rename
    pr = get_object_or_404(Program.objects.select_for_update(), pk=pk, business__owner=request.user)
    archived = AuditLog.objects.filter(
        business=pr.business, action="program_archived", ref=str(pr.pk)
    ).exists()
    if request.method == "DELETE":
        if archived:
            return Response({"archived": True, "detail": "This program is already archived."})
        task_ids = pr.tasks.values_list("id", flat=True)
        has_customer_data = (
            PurchaseEntry.objects.filter(task_id__in=task_ids).exists()
            or TaskProgress.objects.filter(task_id__in=task_ids).exists()
            or RewardGrant.objects.filter(reward__task_id__in=task_ids).exists()
        )
        if has_customer_data:
            pr.active = False
            pr.end = timezone.localdate() - timedelta(days=1)
            pr.save(update_fields=["active", "end"])
            AuditLog.objects.create(
                business=pr.business, actor=request.user, action="program_archived", ref=str(pr.pk)
            )
            return Response({
                "archived": True,
                "detail": "This program has customer history, so it was archived. Existing progress and reward codes are preserved.",
            })
        pr.delete()
        return Response({"archived": False, "detail": "Program deleted."})
    if archived and request.data.get("active") is True:
        raise ValidationError("Archived programs cannot be resumed. Create a new program instead.")
    for k in ("title", "active", "start", "end"):
        if k in request.data:
            setattr(pr, k, request.data[k])
    pr.save()
    return Response({"active": pr.active})


REWARD_TYPES = ("free_item", "percent_off", "flat_off", "gift", "cashback", "special_offer", "custom")
TASK_TYPES = ("count", "amount", "visit")


def _num(v, label, lo, hi):
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError):
        raise ValidationError(f"{label} must be a number.")
    if not d.is_finite() or d < lo or d > hi:
        raise ValidationError(f"{label} must be between {lo} and {hi}.")
    return d


def _text(v, label, maxlen, required=True):
    v = str(v if v is not None else "").strip()
    if required and not v:
        raise ValidationError(f"{label} is required.")
    if len(v) > maxlen:
        raise ValidationError(f"{label} is too long (max {maxlen}).")
    return v


def _clean_reward(d, partial=False):
    out = {}
    if not partial or "title" in d:
        out["title"] = _text(d.get("title"), "Reward name", 120)
    if not partial or "type" in d:
        if d.get("type") not in REWARD_TYPES:
            raise ValidationError("Choose a valid reward type.")
        out["type"] = d["type"]
    if not partial or "value" in d:
        out["value"] = _num(d.get("value", 0), "Value", 0, 1_000_000)
    if not partial or "expiry_days" in d:
        out["expiry_days"] = int(_num(d.get("expiry_days", 30), "Valid days", 1, 365))
    if "terms" in d:
        out["terms"] = _text(d.get("terms"), "Terms", 500, required=False)
    if out.get("type") == "percent_off" and out.get("value", 0) > 100:
        raise ValidationError("A percentage cannot be more than 100.")
    return out


@api_view(["PATCH", "DELETE"])
@transaction.atomic
def reward_update(request, pk):
    """Edit a reward or delete an unused task reward without disturbing customer activity."""
    r = get_object_or_404(Reward.objects.select_for_update(), Q(task__program__business__owner=request.user) | Q(business__owner=request.user), pk=pk)
    if request.method == "DELETE":
        if not r.task_id:
            raise ValidationError("Only task rewards can be deleted here.")
        task = get_object_or_404(Task.objects.select_for_update(), pk=r.task_id)
        has_customer_data = (
            PurchaseEntry.objects.filter(task=task).exists()
            or TaskProgress.objects.filter(task=task).exists()
            or RewardGrant.objects.filter(reward__task=task).exists()
        )
        if has_customer_data:
            raise ValidationError("This reward cannot be deleted because customers have started collecting it or received a reward code.")
        business = task.program.business
        reward_id = r.pk
        r.delete()
        if not task.rewards.exists():
            task.delete()
        AuditLog.objects.create(business=business, actor=request.user, action="reward_delete", ref=str(reward_id))
        return Response({"id": reward_id, "deleted": True})
    for k, v in _clean_reward(request.data, partial=True).items():
        setattr(r, k, v)
    r.save()
    biz = r.task.program.business if r.task_id else r.business
    AuditLog.objects.create(business=biz, actor=request.user, action="reward_edit", ref=str(r.pk))
    return Response({"id": r.pk, "title": r.title, "type": r.type, "value": str(r.value), "expiry_days": r.expiry_days, "terms": r.terms})


@api_view(["POST"])
@transaction.atomic
def program_add_task(request, pk):
    """Add another stamp card (and its reward) to a running program without touching anyone's progress."""
    from .serializers import ProgramSerializer
    pr = get_object_or_404(Program.objects.select_for_update(), pk=pk, business__owner=request.user)
    if AuditLog.objects.filter(business=pr.business, action="program_archived", ref=str(pr.pk)).exists():
        raise ValidationError("This program is archived. Create a new program instead.")
    d = request.data
    if d.get("type") not in TASK_TYPES:
        raise ValidationError("Choose how customers earn: count, amount or visit.")
    t = Task.objects.create(program=pr, title=_text(d.get("title"), "Name", 120), type=d["type"],
        target=_num(d.get("target"), "Target", 1, 1_000_000), item_name=_text(d.get("item_name"), "Item", 80, required=False),
        repeatable=bool(d.get("repeatable", True)), max_per_customer=int(_num(d.get("max_per_customer", 0), "Limit", 0, 1000)))
    if d.get("reward"):
        reward = _clean_reward(d["reward"])
        Reward.objects.create(task=t, **reward)
        announce_shop_customers(
            pr.business, f"New reward at {pr.business.name}: {reward['title']}.",
            link=f"/b/{pr.business.shop_code}/?tab=earn",
        )
    return Response(ProgramSerializer(pr).data, status=201)


QUICK_TEMPLATES = {"stamps": "count", "spend": "amount", "visits": "visit"}


@api_view(["POST"])
@transaction.atomic
def quick_reward(request, code):
    """The easy way to add a reward: pick how customers earn, two numbers, what they get. Creates the stamp card and the reward
    together inside the shop's running program (or starts one), and writes a clear title so the owner never has to."""
    from .serializers import ProgramSerializer
    biz = get_object_or_404(Business.objects.select_for_update(), shop_code=code, owner=request.user)
    d = request.data
    tpl = d.get("template")
    if tpl not in QUICK_TEMPLATES:
        raise ValidationError("Choose how customers earn: buy and get, spend and save, or visit and get.")
    n = _num(d.get("n"), "The number", 1, 1_000_000 if tpl == "spend" else 100)
    if tpl != "spend" and n != n.to_integral_value():
        raise ValidationError("Use a whole number.")
    n = int(n) if n == n.to_integral_value() else n
    item = _text(d.get("item"), "Item", 80, required=False) if tpl == "stamps" else ""
    gtype = d.get("give_type", "free_item")
    if gtype not in ("free_item", "percent_off", "flat_off"):
        raise ValidationError("Choose what customers get: a free item, a percentage off, or money off.")
    value = _num(d.get("give_value", 0), "The discount", 1 if gtype != "free_item" else 0, 100 if gtype == "percent_off" else 1_000_000)
    give = _text(d.get("give"), "What customers get", 120)
    reward = _clean_reward({"title": give, "type": gtype, "value": value, "expiry_days": d.get("expiry_days", 30), "terms": d.get("terms", "")})
    title = {"stamps": f"Buy {n} {item}".strip() if item else f"Buy {n} times", "spend": f"Spend ₹{n:,}", "visits": f"Visit {n} times"}[tpl]
    archived = set(AuditLog.objects.filter(business=biz, action="program_archived").values_list("ref", flat=True))
    pr = next((p for p in biz.programs.order_by("-active", "id") if str(p.pk) not in archived), None) or Program.objects.create(business=biz, title="Rewards")
    if Reward.objects.filter(task__program=pr, task__title=title, title=give).exists():
        raise ValidationError("You already have this exact reward.")
    t = Task.objects.create(program=pr, title=title, type=QUICK_TEMPLATES[tpl], target=n, item_name=item, repeatable=bool(d.get("repeatable", True)))
    Reward.objects.create(task=t, **reward)
    AuditLog.objects.create(business=biz, actor=request.user, action="reward_quick_add", ref=str(t.pk))
    announce_shop_customers(
        biz, f"New reward at {biz.name}: {give}.",
        link=f"/b/{biz.shop_code}/?tab=earn",
    )
    return Response(ProgramSerializer(pr).data, status=201)


@api_view(["PATCH"])
def task_update(request, pk):
    """Edits never hurt in-progress customers: their TaskProgress keeps the target it started with."""
    t = get_object_or_404(Task, pk=pk, program__business__owner=request.user)
    clean = {}
    if "title" in request.data:
        clean["title"] = _text(request.data["title"], "Name", 120)
    if "target" in request.data:
        clean["target"] = _num(request.data["target"], "Target", 1, 1_000_000)
    for k in ("title", "target", "item_name", "repeatable", "max_per_customer"):
        if k in request.data:
            setattr(t, k, clean.get(k, request.data[k]))
    t.version += 1
    t.save()
    return Response({"version": t.version})


@api_view(["POST"])
def reverse(request, pk):
    e = services.reverse_entry(get_object_or_404(PurchaseEntry, pk=pk), request.user)
    return Response(EntrySerializer(e).data)


@api_view(["GET"])
def recent(request):
    from django.db.models import Q
    qs = PurchaseEntry.objects.filter(status="approved").filter(
        Q(profile__business__owner=request.user) | Q(profile__business__staff__user=request.user)).order_by("-id")[:8]
    return Response(EntrySerializer(qs, many=True).data)


@api_view(["POST"])
def block(request, code, pid):
    biz = get_object_or_404(Business, shop_code=code, owner=request.user)
    p = get_object_or_404(CustomerProfile, pk=pid, business=biz)
    p.status = "blocked" if request.data.get("blocked", True) else "active"
    p.save()
    return Response({"status": p.status})


@api_view(["POST"])
def broadcast(request, code):
    """Offer to customers who opted in (marketing consent). Max one per 24h per shop."""
    biz = get_object_or_404(Business, shop_code=code, owner=request.user)
    text = str(request.data.get("text", "")).strip()[:200]
    if not text:
        raise ValidationError("Write the offer text.")
    if AuditLog.objects.filter(business=biz, action="broadcast", at__gte=timezone.now() - timedelta(hours=24)).exists():
        raise ValidationError("You can send one offer per day.")
    users = [p.user for p in biz.customers.filter(marketing_consent=True, status="active").select_related("user")]
    for u in users:
        push(u, f"{biz.name}: {text}", link=f"/b/{biz.shop_code}/?tab=earn")
    AuditLog.objects.create(business=biz, actor=request.user, action="broadcast", ref=str(len(users)))
    return Response({"sent": len(users)})


@api_view(["DELETE"])
def delete_me(request):
    """DPDP erasure. Customers are deleted; owners/vendors are anonymised (invoices/commissions must be retained)."""
    u = request.user
    if u.role == "customer":
        u.delete()
    else:
        Token.objects.filter(user=u).delete()
        OtpCode.objects.filter(user=u).delete()
        u.is_active, u.username, u.first_name = False, f"deleted-{u.id}", ""
        u.email, u.email_verified = "", False
        u.set_unusable_password()
        u.save()
        u.businesses.update(status="closed")
        if hasattr(u, "vendor"):
            u.vendor.status = "suspended"
            u.vendor.save(update_fields=["status"])
    return Response(status=204)


@api_view(["GET", "PATCH", "DELETE"])
def profile_image(request):
    user = request.user
    if request.method == "GET":
        return Response({"profile_image_url": user.profile_image.url if user.profile_image else ""})
    if request.method == "DELETE":
        if user.profile_image:
            user.profile_image.delete(save=False)
            user.profile_image = ""
            user.save(update_fields=["profile_image"])
        return Response({"profile_image_url": ""})
    serializer = ProfileImageSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    previous_name = user.profile_image.name
    user.profile_image = serializer.validated_data["profile_image"]
    user.save(update_fields=["profile_image"])
    if previous_name and previous_name != user.profile_image.name:
        user.profile_image.storage.delete(previous_name)
    return Response({"profile_image_url": user.profile_image.url})


def _h(code):
    return hashlib.sha256((code + settings.SECRET_KEY).encode()).hexdigest()


def _send_email_otp(address, code, purpose):
    if not settings.EMAIL_OTP_ENABLED:
        return False
    subject = "Verify your OFFLet recovery email" if purpose == "email_verify" else "OFFLet password reset code"
    message = f"Your OFFLet verification code is {code}. It expires in 10 minutes. Do not share it."
    try:
        sent = send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [address], fail_silently=False)
    except (OSError, smtplib.SMTPException) as error:
        log.error("Account email OTP delivery failed: %s", type(error).__name__)
        return False
    if sent != 1:
        log.error("Email backend did not deliver an account OTP")
        return False
    return True


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthThrottle])
def otp_request(request):
    u = User.objects.filter(username=str(request.data.get("mobile", "")).strip(), is_active=True).first()
    if u and not OtpCode.objects.filter(
        user=u, purpose="password_reset", created_at__gte=timezone.now() - timedelta(seconds=60)
    ).exists():
        if not settings.NOTIFY_WEBHOOK_URL and not (u.email and u.email_verified and settings.EMAIL_OTP_ENABLED):
            return Response({"detail": "If a recovery method is available, a code was sent."})
        code = f"{secrets.randbelow(10**6):06d}"
        otp = OtpCode.objects.create(
            user=u, code_hash=_h(code), purpose="password_reset", expires=timezone.now() + timedelta(minutes=10)
        )
        if settings.NOTIFY_WEBHOOK_URL:
            notify(u, f"OFFLet OTP {code}. Valid for 10 minutes. Do not share it.", sensitive=True)
        elif not _send_email_otp(u.email, code, "password_reset"):
            otp.delete()
    return Response({"detail": "If a recovery method is available, a code was sent."})


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthThrottle])
def otp_confirm(request):
    u = User.objects.filter(username=str(request.data.get("mobile", "")).strip(), is_active=True).first()
    o = OtpCode.objects.filter(
        user=u, purpose="password_reset", expires__gt=timezone.now()
    ).order_by("-id").first() if u else None
    new = request.data.get("new", "")
    if not o or o.attempts >= 5 or len(new) < 6:
        raise ValidationError("Wrong or expired OTP.")
    if o.code_hash != _h(str(request.data.get("otp", "")).strip()):
        o.attempts += 1; o.save()
        raise ValidationError("Wrong or expired OTP.")
    u.set_password(new); u.save()
    OtpCode.objects.filter(user=u, purpose="password_reset").delete()
    Token.objects.filter(user=u).delete()  # sign out other devices
    return Response({"detail": "Password changed."})


@api_view(["POST"])
@throttle_classes([AuthThrottle])
def recovery_email_request(request):
    email = str(request.data.get("email", "")).strip().lower()
    try:
        validate_email(email)
    except DjangoValidationError:
        raise ValidationError({"email": "Enter a valid email address."})
    user = request.user
    if email == user.email.lower() and user.email_verified:
        return Response({"verified": True})
    if User.objects.filter(email__iexact=email, email_verified=True).exclude(pk=user.pk).exists():
        raise ValidationError({"email": "This email is already connected to another account."})
    now = timezone.now()
    recent = OtpCode.objects.filter(
        user=user, purpose="email_verify", created_at__gte=now - timedelta(seconds=60)
    ).exists()
    if recent:
        raise ValidationError("Wait one minute before requesting another code.")
    if not settings.EMAIL_OTP_ENABLED:
        raise ValidationError("Email delivery is not configured. Contact support.")
    OtpCode.objects.filter(user=user, purpose="email_verify").delete()
    code = f"{secrets.randbelow(10**6):06d}"
    otp = OtpCode.objects.create(
        user=user, code_hash=_h(code), purpose="email_verify", target_email=email,
        expires=now + timedelta(minutes=10),
    )
    if not _send_email_otp(email, code, "email_verify"):
        otp.delete()
        raise ValidationError("Could not send the verification email. Please try again later.")
    return Response({"verified": False, "detail": "Verification code sent."})


@api_view(["POST"])
@throttle_classes([AuthThrottle])
def recovery_email_confirm(request):
    user = request.user
    otp = OtpCode.objects.filter(
        user=user, purpose="email_verify", expires__gt=timezone.now()
    ).order_by("-id").first()
    if not otp or otp.attempts >= 5:
        raise ValidationError("Wrong or expired verification code.")
    if otp.code_hash != _h(str(request.data.get("otp", "")).strip()):
        otp.attempts += 1
        otp.save(update_fields=["attempts"])
        raise ValidationError("Wrong or expired verification code.")
    if User.objects.filter(email__iexact=otp.target_email, email_verified=True).exclude(pk=user.pk).exists():
        otp.delete()
        raise ValidationError("This email is already connected to another account.")
    user.email = otp.target_email
    user.email_verified = True
    user.save(update_fields=["email", "email_verified"])
    OtpCode.objects.filter(user=user, purpose__in=("email_verify", "password_reset")).delete()
    return Response({"email": user.email, "email_verified": True})


@api_view(["POST"])
def accept_terms(request):
    request.user.consent_at = timezone.now()
    request.user.save(update_fields=["consent_at"])
    return Response(status=204)


@api_view(["GET"])
def admin_stats(request):
    if not request.user.is_staff:
        raise PermissionDenied()
    states = {}
    for s in Subscription.objects.all():
        states[s.state] = states.get(s.state, 0) + 1
    rev = Payment.objects.filter(status="paid", created_at__gte=timezone.now() - timedelta(days=30)).aggregate(t=Sum("amount"))["t"] or 0
    return Response({"shops": Business.objects.count(), "subscriptions": states, "revenue_30d_rupees": rev / 100,
        "customers": User.objects.filter(role="customer").count(),
        "entries_today": PurchaseEntry.objects.filter(created_at__date=timezone.localdate()).count(),
        "vendors_pending": Vendor.objects.filter(status="pending").count()})
