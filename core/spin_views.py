import io
import secrets
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation
import segno
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import (Business, CustomerProfile, PurchaseEntry, Reward, RewardGrant, SpinRecord,
                     SpinSegment, SpinWheel)
from .notify import announce_shop_customers, push


_REWARD_TYPES = {"percent_off", "free_item"}
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_URL = URLValidator(schemes=("http", "https"))


def _owner_business(request, code):
    return get_object_or_404(Business, shop_code=code, owner=request.user)


def _decimal(value, label, maximum=Decimal("99999999.99")):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(f"Enter a valid {label}.")
    if not result.is_finite() or result < 0 or result > maximum:
        raise ValidationError(f"Enter a valid {label}.")
    return result.quantize(Decimal("0.01"))


def _parse_wheel(data, current=None):
    name = str(data.get("name", current.name if current else "")).strip()[:100]
    audience = data.get("audience", current.audience if current else "all")
    if not name or audience not in {x[0] for x in SpinWheel.AUDIENCES}:
        raise ValidationError("Give the wheel a name and choose a valid customer group.")

    raw_days = data.get("weekdays", current.weekdays if current else "")
    if isinstance(raw_days, (list, tuple)):
        raw_days = ",".join(str(x) for x in raw_days)
    if not isinstance(raw_days, str):
        raise ValidationError("Choose valid days for this campaign.")
    days = [x.strip() for x in raw_days.split(",") if x.strip()]
    if any(not x.isdigit() or not 0 <= int(x) <= 6 for x in days):
        raise ValidationError("Weekdays must be numbered 0 (Monday) through 6 (Sunday).")
    weekdays = ",".join(dict.fromkeys(days))

    def date_field(key, old):
        raw = data.get(key, old.isoformat() if old else "")
        if raw in (None, ""):
            return None
        parsed = parse_date(str(raw))
        if not parsed:
            raise ValidationError(f"Enter a valid {key.replace('_', ' ')}.")
        return parsed

    start = date_field("start_date", current.start_date if current else None)
    end = date_field("end_date", current.end_date if current else None)
    if start and end and end < start:
        raise ValidationError("The campaign end date must be on or after its start date.")
    try:
        spins = int(data.get("spins_per_day", current.spins_per_day if current else 1))
    except (TypeError, ValueError):
        raise ValidationError("Spins per day must be between 1 and 10.")
    if not 1 <= spins <= 10:
        raise ValidationError("Spins per day must be between 1 and 10.")
    active = data.get("active", current.active if current else True)
    if isinstance(active, str):
        if active.lower() in ("true", "1", "yes", "on"):
            active = True
        elif active.lower() in ("false", "0", "no", "off"):
            active = False
        else:
            raise ValidationError("Choose whether the campaign is active.")
    elif not isinstance(active, bool) and active not in (0, 1):
        raise ValidationError("Choose whether the campaign is active.")
    return {"name": name, "audience": audience, "weekdays": weekdays, "start_date": start,
            "end_date": end, "spins_per_day": spins, "active": bool(active)}


def _parse_segments(raw):
    if not isinstance(raw, list) or not 2 <= len(raw) <= 12:
        raise ValidationError({"segments": "Add between 2 and 12 wheel segments."})
    result, total = [], 0
    for position, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValidationError({"segments": "Each segment must be an object."})
        label = str(item.get("label", "")).strip()[:80]
        reward_type = item.get("reward_type")
        if not label or reward_type not in _REWARD_TYPES:
            raise ValidationError({"segments": "Give each segment a label and valid reward type."})
        try:
            probability = int(item.get("probability"))
        except (TypeError, ValueError):
            raise ValidationError({"segments": "Each probability must be between 0 and 100."})
        if not 0 <= probability <= 100:
            raise ValidationError({"segments": "Each probability must be between 0 and 100."})
        total += probability
        color = str(item.get("color", "#5e35b1")).strip()
        if not _HEX_COLOR.fullmatch(color):
            raise ValidationError({"segments": "Use a six-digit hex color for each segment."})
        icon = str(item.get("icon", "🎁")).strip()[:16]
        image_url = str(item.get("image_url", "")).strip()
        if image_url.lower() in ("none", "null", "undefined"):
            image_url = ""
        if image_url:
            try:
                _URL(image_url)
            except DjangoValidationError:
                image_url = ""
            if len(image_url) > 500:
                image_url = ""
        raw_value = item.get("value", 0)
        value = _decimal(0 if raw_value in (None, "") else raw_value, "reward value",
                         Decimal("100") if reward_type == "percent_off" else Decimal("99999999.99"))
        if reward_type == "percent_off" and value > 100:
            raise ValidationError({"segments": "Percentage discounts cannot exceed 100%."})
        raw_expiry = item.get("expiry_days", 30)
        try:
            expiry = int(30 if raw_expiry in (None, "") else raw_expiry)
        except (TypeError, ValueError):
            raise ValidationError({"segments": "Reward expiry must be between 1 and 365 days."})
        if not 1 <= expiry <= 365:
            raise ValidationError({"segments": "Reward expiry must be between 1 and 365 days."})
        terms = str(item.get("terms", "")).strip()[:300]
        products = str(item.get("product_restrictions", "")).strip()[:200]
        raw_minimum = item.get("minimum_order", 0)
        result.append({
            "position": position, "label": label, "reward_type": reward_type, "probability": probability,
            "color": color, "icon": icon or "🎁", "image_url": image_url, "value": value,
            "expiry_days": expiry,
            "minimum_order": _decimal(0 if raw_minimum in (None, "") else raw_minimum, "minimum order"),
            "product_restrictions": products, "terms": terms,
        })
    if total != 100:
        raise ValidationError({"segments": "Segment probabilities must add up to exactly 100%."})
    return result


def _segment_json(segment):
    return {"id": segment.id, "position": segment.position, "label": segment.label,
            "reward_type": segment.reward_type, "probability": segment.probability, "color": segment.color,
            "icon": segment.icon, "image_url": segment.image_url, "value": str(segment.value),
            "expiry_days": segment.expiry_days, "minimum_order": str(segment.minimum_order),
            "product_restrictions": segment.product_restrictions, "terms": segment.terms}


def _wheel_json(wheel, include_stats=False):
    data = {"id": wheel.id, "name": wheel.name, "audience": wheel.audience,
            "weekdays": [int(x) for x in wheel.weekdays.split(",") if x],
            "start_date": wheel.start_date, "end_date": wheel.end_date,
            "spins_per_day": wheel.spins_per_day, "active": wheel.active,
            "segments": [_segment_json(s) for s in wheel.segments.all()]}
    if include_stats:
        records = SpinRecord.objects.filter(wheel=wheel)
        data["analytics"] = {
            "spins": records.count(),
            "wins": records.filter(outcome="won").count(),
            "redeemed": records.filter(grant__status="used").count(),
            "active_coupons": records.filter(grant__status="active").count(),
            "recent": [{
                "customer": row.profile.user.first_name or "Customer",
                "outcome": row.outcome, "prize": row.prize_title,
                "coupon_status": row.grant.status if row.grant else "",
                "created_at": row.created_at,
            } for row in records.select_related("profile__user", "grant")[:10]],
        }
    return data


@transaction.atomic
def _save_wheel(business, data, wheel=None):
    fields = _parse_wheel(data, wheel)
    segments = _parse_segments(data["segments"]) if "segments" in data else None
    if wheel is None:
        if segments is None:
            raise ValidationError({"segments": "Add wheel segments."})
        wheel = SpinWheel.objects.create(business=business, **fields)
    else:
        for key, value in fields.items():
            setattr(wheel, key, value)
        wheel.save()
    if segments is not None:
        for item in segments:
            pos = item.pop("position")
            segment, _ = SpinSegment.objects.get_or_create(wheel=wheel, position=pos, defaults=item)
            if segment.pk and segment.position == pos:
                for key, value in item.items():
                    setattr(segment, key, value)
                segment.save()
        wheel.segments.exclude(position__lt=len(segments)).delete()
    return wheel


@api_view(["GET", "POST"])
@transaction.atomic
def spin_wheels(request, code):
    business = _owner_business(request, code)
    if request.method == "POST":
        wheel = _save_wheel(business, request.data)
        if wheel.active:
            announce_shop_customers(
                business, f"New Spin & Win wheel at {business.name}: {wheel.name}.",
                link=f"/b/{business.shop_code}/",
                audience=wheel.audience,
            )
        return Response(_wheel_json(wheel, True), status=201)
    return Response([_wheel_json(wheel, True) for wheel in business.spin_wheels.all()])


@api_view(["PATCH", "DELETE"])
def spin_wheel_detail(request, pk):
    wheel = get_object_or_404(SpinWheel, pk=pk, business__owner=request.user)
    if request.method == "DELETE":
        wheel.delete()
        return Response(status=204)
    return Response(_wheel_json(_save_wheel(wheel.business, request.data, wheel), True))


def _active_wheel(business, audience, day):
    wheels = business.spin_wheels.filter(active=True).filter(
        Q(start_date__isnull=True) | Q(start_date__lte=day)
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=day)).prefetch_related("segments")
    matching = []
    for wheel in wheels:
        if wheel.weekdays and day.weekday() not in {int(x) for x in wheel.weekdays.split(",") if x}:
            continue
        if wheel.audience not in (audience, "all"):
            continue
        matching.append(wheel)
    matching.sort(key=lambda wheel: (wheel.audience == audience, wheel.updated_at, wheel.pk), reverse=True)
    return matching[0] if matching else None


def _spin_status(profile, wheel, day):
    spun = SpinRecord.objects.filter(profile=profile, business=profile.business, spin_date=day).count()
    has_purchase = PurchaseEntry.objects.filter(profile=profile, status="approved").exists()
    return {"available": bool(wheel), "audience": "returning" if has_purchase else "new",
            "wheel": _wheel_json(wheel) if wheel else None,
            "spins_per_day": wheel.spins_per_day if wheel else 0,
            "spins_remaining": max(0, wheel.spins_per_day - spun) if wheel else 0,
            "history": _history(profile)}


def _history(profile):
    return [{"id": row.id, "wheel": row.wheel.name if row.wheel else "",
             "prize": row.prize_title, "outcome": row.outcome, "code": row.grant.code if row.grant else "",
             "status": row.grant.status if row.grant else "", "created_at": row.created_at,
             "expires_at": row.grant.expires_at if row.grant else None}
            for row in profile.spins.select_related("wheel", "grant")[:20]]


def _customer_profile(request, code):
    if request.user.role != "customer":
        raise PermissionDenied("Customer account required.")
    return get_object_or_404(CustomerProfile.objects.select_related("business", "user"),
                             user=request.user, business__shop_code=code)


@api_view(["GET", "POST"])
def customer_spin(request, code):
    profile = _customer_profile(request, code)
    business = profile.business
    if not business.is_live:
        raise ValidationError("This shop is not taking rewards right now.")
    if profile.status != "active":
        raise PermissionDenied("This shop has paused your account.")
    today = timezone.localdate()
    has_purchase = PurchaseEntry.objects.filter(profile=profile, status="approved").exists()
    audience = "returning" if has_purchase else "new"
    wheel = _active_wheel(business, audience, today)
    if request.method == "GET":
        return Response(_spin_status(profile, wheel, today))
    if not wheel:
        raise ValidationError("There is no Spin & Win campaign available today.")
    if not wheel.segments.exists():
        raise ValidationError("This Spin & Win campaign has no rewards configured.")

    try:
        with transaction.atomic():
            CustomerProfile.objects.select_for_update().get(pk=profile.pk)
            existing = SpinRecord.objects.filter(profile=profile, business=business, spin_date=today)
            sequence = existing.count() + 1
            if sequence > wheel.spins_per_day:
                raise ValidationError("You have used all your spins for today. Come back tomorrow!")
            roll = secrets.randbelow(100)
            cursor = 0
            chosen = None
            for segment in wheel.segments.all():
                cursor += segment.probability
                if roll < cursor:
                    chosen = segment
                    break
            if chosen is None:
                raise RuntimeError("The configured wheel probabilities did not select a segment.")

            grant = None
            outcome = "try_again" if chosen.reward_type == "empty" else "won"
            if outcome == "won":
                conditions = []
                if chosen.minimum_order:
                    conditions.append(f"Minimum order: INR {chosen.minimum_order}.")
                if chosen.product_restrictions:
                    conditions.append(f"Valid for: {chosen.product_restrictions}.")
                terms = " ".join(x for x in (chosen.terms, *conditions) if x)
                reward = Reward.objects.create(
                    business=business, trigger="spin", title=chosen.label, type=chosen.reward_type,
                    value=chosen.value, expiry_days=chosen.expiry_days, min_order_amount=chosen.minimum_order,
                    product_restrictions=chosen.product_restrictions, terms=terms,
                )
                grant = RewardGrant.objects.create(profile=profile, reward=reward,
                                                   expires_at=timezone.now() + timedelta(days=chosen.expiry_days))
                push(profile.user, f"You won {chosen.label} at {business.name}! Your coupon code is {grant.code}.",
                     link=f"/b/{business.shop_code}/?tab=rewards")
            SpinRecord.objects.create(profile=profile, business=business, wheel=wheel, segment=chosen, grant=grant,
                                      spin_date=today, sequence=sequence, outcome=outcome, prize_title=chosen.label)
    except IntegrityError:
        raise ValidationError("Your spin was already recorded. Refresh and check your rewards.")

    return Response({
        "outcome": outcome, "segment": _segment_json(chosen),
        "grant": ({"title": grant.reward.title, "code": grant.code, "expires_at": grant.expires_at,
                   "terms": grant.reward.terms, "status": grant.status} if grant else None),
        **_spin_status(profile, wheel, today),
    }, status=201)


@api_view(["GET"])
@permission_classes([AllowAny])
def spin_qr(request, code):
    business = get_object_or_404(Business, shop_code=code)
    buf = io.BytesIO()
    target = f"{settings.BASE_URL}/b/{business.shop_code}/?tab=spin"
    segno.make(target, error="m").save(buf, kind="png", scale=10, border=4)
    response = HttpResponse(buf.getvalue(), content_type="image/png")
    response["Cache-Control"] = "public, max-age=3600"
    if request.GET.get("download") == "1":
        response["Content-Disposition"] = f'attachment; filename="{business.shop_code}-spin-qr.png"'
    return response
