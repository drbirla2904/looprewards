import io
import math
import segno
from urllib.parse import urlencode
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.db.models import Avg, Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from .throttles import AuthThrottle
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from . import services
from .models import (Vendor, Business, CustomerProfile, Feedback, Program, PurchaseEntry, Reward, Task, User,
                     new_shop_code)
from .notify import announce_shop_customers
from .serializers import BusinessSerializer, EntrySerializer, ProgramSerializer, ShopOfferSerializer


def _mgr_only(user):
    if user.role not in ("owner", "staff"):
        raise PermissionDenied("Owner or staff account required.")


def _owner_only(user):
    if user.role != "owner":
        raise PermissionDenied("Owner account required.")


def _customer_only(user):
    if user.role != "customer":
        raise PermissionDenied("Customer account required.")


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthThrottle])
def register(request):
    d = request.data
    mobile, pw = str(d.get("mobile", "")).strip(), d.get("password", "")
    if not mobile.isdigit() or len(mobile) < 10 or len(pw) < 6:
        raise ValidationError("Valid mobile and 6+ char password required.")
    if User.objects.filter(username=mobile).exists():
        raise ValidationError("Mobile already registered.")
    role = d.get("role") if d.get("role") in ("owner", "vendor") else "customer"
    if str(d.get("accepted")).lower() not in ("true", "1", "on"):
        raise ValidationError("Please accept the Terms and Privacy Policy.")
    ref = Vendor.objects.filter(
        code=str(d.get("ref", "")).upper(),
        status="approved",
        user__is_active=True,
    ).first() if role == "owner" else None
    u = User.objects.create_user(username=mobile, password=pw, first_name=d.get("name", ""), role=role, referred_by=ref, consent_at=timezone.now())
    return Response({"token": Token.objects.create(user=u).key, "role": role}, status=201)


@api_view(["POST"])
def create_business(request):
    _owner_only(request.user)
    upi = request.data.get("pay_upi_id")
    if upi and Business.objects.filter(pay_upi_id=upi).exists():
        raise ValidationError("This UPI ID is already registered.")
    s = BusinessSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    return Response(BusinessSerializer(s.save(owner=request.user)).data, status=201)


@api_view(["POST"])
def regenerate_qr(request, code):
    biz = get_object_or_404(Business, shop_code=code, owner=request.user)
    biz.shop_code = new_shop_code()
    biz.save()
    return Response({"shop_code": biz.shop_code})


@api_view(["POST"])
@transaction.atomic
def create_program(request, code):
    """Body: {title, tasks:[{title,type,target,item_name,repeatable,max_per_customer,
    rewards:[{title,type,value,expiry_days,terms}]}]}"""
    biz = get_object_or_404(Business, shop_code=code, owner=request.user)
    d = request.data
    prog = Program.objects.create(business=biz, title=d.get("title", "Rewards"))
    reward_titles = []
    for t in d.get("tasks", []):
        rewards = t.pop("rewards", [])
        task = Task.objects.create(program=prog, **{k: t[k] for k in t if k in
            ("title", "type", "target", "item_name", "repeatable", "max_per_customer")})
        for r in rewards:
            reward = Reward.objects.create(task=task, **{k: r[k] for k in r if k in
                ("title", "type", "value", "expiry_days", "terms")})
            reward_titles.append(reward.title)
    if reward_titles:
        names = ", ".join(reward_titles[:3]) + (" and more" if len(reward_titles) > 3 else "")
        announce_shop_customers(
            biz, f"New rewards at {biz.name}: {names}.",
            link=f"/b/{biz.shop_code}/?tab=earn",
        )
    return Response(ProgramSerializer(prog).data, status=201)


@api_view(["GET"])
@permission_classes([AllowAny])
def discover_shops(request):
    """Search live shops by name/address and optionally order them by customer distance."""
    query = str(request.GET.get("q", "")).strip()[:120]
    shops = Business.objects.filter(status="active")
    if query:
        shops = shops.filter(Q(name__icontains=query) | Q(address__icontains=query) | Q(category__icontains=query))
    try:
        lat = float(request.GET.get("lat")) if request.GET.get("lat") else None
        lng = float(request.GET.get("lng")) if request.GET.get("lng") else None
    except (TypeError, ValueError):
        lat = lng = None
    out = []
    joined_ids = set()
    if request.user.is_authenticated:
        joined_ids = set(request.user.profiles.filter(hidden_from_customer=False).values_list("business_id", flat=True))
    businesses = list(shops.select_related("owner").order_by("name")[:200])
    rating_rows = Feedback.objects.filter(
        profile__business_id__in=[biz.id for biz in businesses]
    ).filter(
        Q(entry__status="approved") | Q(booking__status="completed")
    ).values("profile__business_id").annotate(
        average=Avg("rating"), count=Count("id")
    )
    ratings = {row["profile__business_id"]: row for row in rating_rows}
    for biz in businesses:
        if not biz.is_live:
            continue
        rating = ratings.get(biz.id)
        distance_km = None
        if lat is not None and lng is not None and biz.lat is not None and biz.lng is not None:
            rad = math.pi / 180
            dlat, dlng = (biz.lat - lat) * rad, (biz.lng - lng) * rad
            a = math.sin(dlat / 2) ** 2 + math.cos(lat * rad) * math.cos(biz.lat * rad) * math.sin(dlng / 2) ** 2
            distance_km = 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0, 1 - a)))
        out.append({
            "name": biz.name, "category": biz.category, "tagline": biz.tagline,
            "address": biz.address, "shop_code": biz.shop_code, "brand_color": biz.brand_color,
            "logo_url": biz.logo.url if biz.logo else "", "lat": biz.lat, "lng": biz.lng,
            "distance_km": round(distance_km, 1) if distance_km is not None else None,
            "joined": biz.id in joined_ids,
            "rating_average": round(float(rating["average"]), 1) if rating else None,
            "rating_count": rating["count"] if rating else 0,
        })
    if lat is not None and lng is not None:
        out.sort(key=lambda x: (x["distance_km"] is None, x["distance_km"] if x["distance_km"] is not None else 0, x["name"]))
    return Response({"shops": out})


@api_view(["GET"])
@permission_classes([AllowAny])
def public_business(request, code):
    """Landing page data for the scanned QR: profile, active programs, Pay link."""
    biz = get_object_or_404(Business, shop_code=code)
    if not biz.is_live:
        return Response({"name": biz.name, "paused": True})
    data = BusinessSerializer(biz).data
    rating = Feedback.objects.filter(profile__business=biz).filter(
        Q(entry__status="approved") | Q(booking__status="completed")
    ).aggregate(average=Avg("rating"), count=Count("id"))
    data["rating_average"] = round(float(rating["average"]), 1) if rating["average"] is not None else None
    data["rating_count"] = rating["count"]
    today = timezone.localdate()
    active_programs = biz.programs.filter(active=True).filter(
        Q(start__isnull=True) | Q(start__lte=today)
    ).filter(Q(end__isnull=True) | Q(end__gte=today))
    data["programs"] = ProgramSerializer(active_programs, many=True).data
    if biz.pay_upi_id:
        data["pay_link"] = "upi://pay?" + urlencode({"pa": biz.pay_upi_id, "pn": biz.name, "cu": "INR"})
    from . import engage
    from .serializers import ServiceSerializer
    data["boosts_now"] = [engage.boost_dict(b) for b in engage.active_boosts(biz)]
    data["services"] = ServiceSerializer(biz.services.filter(active=True), many=True).data if biz.bookings_enabled else []
    data["perks"] = {r.trigger: {"title": r.title} for r in biz.perk_rewards.filter(
        trigger__in=("welcome", "referral", "social")
    )}
    data["offers"] = ShopOfferSerializer(
        biz.offers.filter(active=True).prefetch_related("items"), many=True
    ).data
    data["tiers"] = [{"tier": t, "visits": n, "perk": perk} for t, n, perk in engage.tier_ladder(biz)[1:]]
    return Response(data)


@api_view(["GET"])
@permission_classes([AllowAny])
def business_qr(request, code):
    biz = get_object_or_404(Business, shop_code=code)
    buf = io.BytesIO()
    segno.make(f"{settings.BASE_URL}/b/{biz.shop_code}", error="m").save(buf, kind="png", scale=10, border=4)
    response = HttpResponse(buf.getvalue(), content_type="image/png")
    if request.GET.get("download") == "1":
        response["Content-Disposition"] = f'attachment; filename="{biz.shop_code}-shop-qr.png"'
    return response


@api_view(["POST"])
def join(request, code):
    biz = get_object_or_404(Business, shop_code=code)
    if not biz.is_live:
        raise ValidationError("This shop is paused.")
    p, created = CustomerProfile.objects.get_or_create(user=request.user, business=biz)
    ref = str(request.data.get("ref", "")).strip().upper()
    if created and ref:  # invited by another customer of this shop
        friend = CustomerProfile.objects.filter(business=biz, referral_code=ref, status="active").exclude(
            user=request.user).first()
        if friend:
            p.referred_by = friend
            p.save(update_fields=["referred_by"])
    if p.hidden_from_customer:
        p.hidden_from_customer = False
        p.save(update_fields=["hidden_from_customer"])
    if "consent" in request.data:
        p.marketing_consent = bool(request.data["consent"])
        p.save()
    return Response({"profile": p.id}, status=201)


@api_view(["POST"])
def submit_entry(request):
    task = get_object_or_404(Task, pk=request.data.get("task"))
    profile = get_object_or_404(CustomerProfile, user=request.user, business=task.program.business)
    e = services.submit_entry(profile, task, request.data.get("value", 1), request.FILES.get("bill_photo"), request.data.get("counter_code", ""),
                             _f(request.data.get("lat")), _f(request.data.get("lng")))
    return Response(EntrySerializer(e).data, status=201)


@api_view(["GET"])
def pending(request):
    _mgr_only(request.user)
    qs = PurchaseEntry.objects.filter(status="pending").filter(
        Q(profile__business__owner=request.user) | Q(profile__business__staff__user=request.user)
    ).select_related("profile__user", "profile__business", "task")
    return Response(EntrySerializer(qs.order_by("created_at"), many=True).data)


@api_view(["POST"])
def review(request, pk):
    _mgr_only(request.user)
    action = request.data.get("action")
    if action not in ("approve", "reject"):
        raise ValidationError("Choose approve or reject.")
    entry = get_object_or_404(PurchaseEntry, pk=pk)  # services.review_entry enforces owner/staff of that shop
    e = services.review_entry(entry, request.user, approve=action == "approve")
    return Response(EntrySerializer(e).data)


@api_view(["POST"])
def redeem(request):
    _mgr_only(request.user)
    g = services.redeem(request.data.get("code", ""), request.user)
    return Response({"status": g.status, "reward": g.reward.title})


@api_view(["POST"])
def redeem_lookup(request):
    _mgr_only(request.user)
    return Response(services.lookup_grant(request.data.get("code", ""), request.user))


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def reward_qr(request, code):
    """QR of the redeem link for a reward code. No database lookup: it only encodes a link, the code itself is the secret."""
    import re
    code = code.upper()
    if not re.fullmatch(r"[0-9A-F]{8}", code):
        return HttpResponse(status=404)
    buf = io.BytesIO()
    segno.make(f"{settings.BASE_URL}/app/?redeem={code}", error="m").save(buf, kind="png", scale=8, border=2)
    resp = HttpResponse(buf.getvalue(), content_type="image/png")
    resp["Cache-Control"] = "private, max-age=3600"
    return resp


@api_view(["GET"])
def my_shops(request):
    out = []
    for p in request.user.profiles.filter(hidden_from_customer=False).select_related("business"):
        entries = p.entries.select_related("task").order_by("-created_at", "-id")
        if p.history_hidden_before:
            entries = entries.filter(created_at__gte=p.history_hidden_before)
        out.append({
            "shop": p.business.name, "shop_code": p.business.shop_code, "consent": p.marketing_consent,
            "history_hidden_before": p.history_hidden_before,
            "progress": [{"task_id": t.task_id, "task": t.task.title, "task_type": t.task.type,
                          "current": t.current_value, "target": t.target or t.task.target,
                          "completed": t.completed_count} for t in p.progress.select_related("task")],
            "rewards": [{"title": g.reward.title, "type": g.reward.type, "value": g.reward.value,
                         "terms": g.reward.terms, "code": g.code, "status": g.status,
                         "expires_at": g.expires_at, "item_name": g.reward.item_name,
                         "original_price": g.reward.original_price, "offer_price": g.reward.offer_price,
                         "image": g.reward.image.url if g.reward.image else ""} for g in p.grants.select_related("reward")],
            "entries": [{"id": e.id, "task_id": e.task_id, "task_title": e.task.title,
                         "task_type": e.task.type, "value": e.value, "status": e.status,
                         "created_at": e.created_at, "reviewed_at": e.reviewed_at}
                        for e in entries[:10]],
        })
    return Response(out)


@api_view(["GET"])
def hidden_shops(request):
    _customer_only(request.user)
    return Response(list(request.user.profiles.filter(hidden_from_customer=True).select_related(
        "business"
    ).values("business__name", "business__shop_code")))


@api_view(["DELETE"])
def hide_shop(request, code):
    _customer_only(request.user)
    profile = get_object_or_404(CustomerProfile, user=request.user, business__shop_code=code)
    if not profile.hidden_from_customer:
        profile.hidden_from_customer = True
        profile.save(update_fields=["hidden_from_customer"])
    return Response(status=204)


@api_view(["POST"])
def restore_shop(request, code):
    _customer_only(request.user)
    profile = get_object_or_404(CustomerProfile, user=request.user, business__shop_code=code)
    if profile.hidden_from_customer:
        profile.hidden_from_customer = False
        profile.save(update_fields=["hidden_from_customer"])
    return Response({"shop_code": code, "hidden": False})


@api_view(["DELETE", "POST"])
def customer_history(request, code):
    _customer_only(request.user)
    profile = get_object_or_404(CustomerProfile, user=request.user, business__shop_code=code)
    if request.method == "DELETE":
        profile.history_hidden_before = timezone.now()
        profile.save(update_fields=["history_hidden_before"])
    else:
        profile.history_hidden_before = None
        profile.save(update_fields=["history_hidden_before"])
    return Response({"history_hidden_before": profile.history_hidden_before})


from django.contrib.auth import authenticate


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthThrottle])
def login(request):
    mobile = request.data.get("mobile") or request.data.get("username")
    u = authenticate(username=str(mobile or "").strip(), password=request.data.get("password"))
    if not u:
        raise ValidationError("Wrong mobile or password.")
    return Response({"token": Token.objects.get_or_create(user=u)[0].key, "role": u.role, "needs_consent": u.consent_at is None})


@api_view(["GET", "PATCH"])
def profile(request):
    user = request.user
    if request.method == "PATCH":
        name = request.data.get("name")
        if not isinstance(name, str) or len(name.strip()) > 150:
            raise ValidationError("Enter a name up to 150 characters.")
        user.first_name = name.strip()
        user.save(update_fields=["first_name"])
    return Response({
        "name": user.first_name, "mobile": user.username, "role": user.role,
        "email": user.email, "email_verified": user.email_verified,
    })


@api_view(["GET"])
def my_businesses(request):
    _mgr_only(request.user)
    out = []
    shops = request.user.businesses.all() if request.user.role == "owner" else [request.user.staff_of.business]
    for b in shops:
        d = BusinessSerializer(b).data
        d["programs"] = ProgramSerializer(b.programs.all(), many=True).data
        out.append(d)
    return Response(out)


from . import counter
from .models import StaffMember, can_manage


@api_view(["GET", "POST", "DELETE"])
def staff(request, code):
    biz = get_object_or_404(Business, shop_code=code, owner=request.user)
    if request.method == "GET":
        return Response([{"mobile": m.user.username, "name": m.user.first_name} for m in biz.staff.select_related("user")])
    d, mobile = request.data, str(request.data.get("mobile", "")).strip()
    if request.method == "DELETE":
        User.objects.filter(username=mobile, staff_of__business=biz).delete()
        return Response(status=204)
    if not mobile.isdigit() or len(mobile) < 10 or len(d.get("password", "")) < 6 or User.objects.filter(username=mobile).exists():
        raise ValidationError("Valid unused mobile and 6+ char password required.")
    u = User.objects.create_user(username=mobile, password=d["password"], first_name=d.get("name", ""), role="staff")
    StaffMember.objects.create(user=u, business=biz)
    return Response({"mobile": mobile}, status=201)


@api_view(["GET"])
def counter_code(request, code):
    biz = get_object_or_404(Business, shop_code=code)
    if not can_manage(request.user, biz):
        raise PermissionDenied()
    c, left = counter.current(biz)
    return Response({"code": c, "expires_in": left})


@api_view(["GET"])
@permission_classes([AllowAny])
def counter_qr(request, code):
    """QR for the counter screen. Only renders for a currently valid code (the code itself is the secret)."""
    biz = get_object_or_404(Business, shop_code=code)
    c = request.GET.get("c", "")
    if counter.match(biz, c) is None:
        return HttpResponse(status=404)
    buf = io.BytesIO()
    segno.make(f"{settings.BASE_URL}/b/{biz.shop_code}/?c={c}", error="m").save(buf, kind="png", scale=8, border=3)
    return HttpResponse(buf.getvalue(), content_type="image/png")


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None
