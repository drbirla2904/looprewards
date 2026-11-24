"""v2 API: wallet, customer CRM, campaigns, insights, boosts, perks, services, bookings, feedback, blueprints."""
from datetime import timedelta
import json
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from . import blueprints, engage, services
from .models import (AuditLog, Booking, Boost, Business, CustomerProfile, Feedback, PurchaseEntry, Reward,
                     RewardGrant, Service, ShopOffer, ShopOfferItem, SocialFollowClaim, can_manage)
from .notify import announce_shop_customers, push
from .serializers import (BoostSerializer, BookingSerializer, FeedbackSerializer, ServiceSerializer,
                          ShopOfferSerializer)


# --------------------------------------------------------------------------- helpers
def _owner_biz(request, code):
    return get_object_or_404(Business, shop_code=code, owner=request.user)


def _mgr_biz(request, code):
    biz = get_object_or_404(Business, shop_code=code)
    if not can_manage(request.user, biz):
        raise PermissionDenied()
    return biz


def _customer(request):
    if request.user.role != "customer":
        raise PermissionDenied("Customer account required.")
    return request.user


def _managers(biz):
    return [biz.owner] + [s.user for s in biz.staff.select_related("user")]


def _dec(v, field="value"):
    try:
        d = Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(f"Enter a valid {field}.")
    if not d.is_finite() or d < 0 or d > Decimal("99999999.99"):
        raise ValidationError(f"Enter a valid {field}.")
    return d.quantize(Decimal("0.01"))


def _offer_item_image(image):
    if not image:
        return
    if image.size > 5 * 1024 * 1024:
        raise ValidationError("Product images must be 5 MB or smaller.")
    if image.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise ValidationError("Upload a JPEG, PNG or WebP product image.")


# --------------------------------------------------------------------------- session
@api_view(["POST"])
def logout(request):
    Token.objects.filter(user=request.user).delete()  # also signs out other devices
    return Response(status=204)


# --------------------------------------------------------------------------- customer
@api_view(["GET"])
def wallet(request):
    return Response(engage.wallet(_customer(request)))


@api_view(["GET"])
def customer_shop(request, code):
    """One call for the customer's view of one shop (after joining)."""
    user = _customer(request)
    p = get_object_or_404(CustomerProfile, user=user, business__shop_code=code)
    biz = p.business
    st = engage.shop_state(p)
    entries = p.entries.select_related("task").order_by("-created_at", "-id")
    if p.history_hidden_before:
        entries = entries.filter(created_at__gte=p.history_hidden_before)
    recent_bookings = Booking.objects.filter(profile=p).select_related(
        "service", "profile__user", "profile__business").order_by("-starts_at")[:10]
    code_ = engage.ensure_ref_code(p)
    now = timezone.now()
    counted = PurchaseEntry.objects.filter(profile=p).exclude(status="rejected")
    last = counted.order_by("-created_at").first()
    wait = max(0, int(biz.cooldown_minutes * 60 - (now - last.created_at).total_seconds())) if last else 0
    used_today = counted.filter(created_at__date=timezone.localdate()).count()
    st.update({
        "cooldown_seconds": wait, "daily_cap": biz.daily_cap, "entries_left_today": max(0, biz.daily_cap - used_today),
        "pending_count": p.entries.filter(status="pending").count(),
        "approval_mode": biz.approval_mode, "joined_at": p.joined_at,
    })
    st.update({
        "shop": biz.name, "shop_code": biz.shop_code, "live": biz.is_live, "consent": p.marketing_consent,
        "status": p.status, "bookings_enabled": biz.bookings_enabled,
        "entries": [{"id": e.id, "task_title": e.task.title, "task_type": e.task.type, "value": str(e.value),
                     "credited": str(e.credited_value if e.credited_value is not None else e.value),
                     "multiplier": e.multiplier, "status": e.status, "created_at": e.created_at,
                     "rated": hasattr(e, "feedback")} for e in entries[:15]],
        "bookings": BookingSerializer(recent_bookings, many=True).data,
        "referral_code": code_, "referral_url": f"{settings.BASE_URL}/b/{biz.shop_code}/?ref={code_}",
        "referral_reward": next((r.title for r in biz.perk_rewards.filter(trigger="referral")[:1]), ""),
        "friends_referred": p.referred.count(),
    })
    social_reward = biz.perk_rewards.filter(trigger="social").first()
    follow_claim = SocialFollowClaim.objects.filter(profile=p).select_related("reward_grant__reward").first()
    st["social_follow_reward"] = _perk(social_reward) if social_reward else None
    st["social_follow_claim"] = ({
        "status": follow_claim.status,
        "requested_at": follow_claim.requested_at,
        "reward_title": (follow_claim.reward_grant.reward.title if follow_claim.reward_grant_id
                         else social_reward.title if social_reward else ""),
    } if follow_claim else None)
    return Response(st)


@api_view(["POST"])
def feedback_submit(request):
    user = _customer(request)
    d = request.data
    try:
        rating = int(d.get("rating"))
    except (TypeError, ValueError):
        raise ValidationError("Choose a rating from 1 to 5.")
    if not 1 <= rating <= 5:
        raise ValidationError("Choose a rating from 1 to 5.")
    comment = str(d.get("comment", "")).strip()[:300]
    if d.get("entry"):
        target = get_object_or_404(PurchaseEntry, pk=d["entry"], profile__user=user, status="approved")
        profile, kw = target.profile, {"entry": target}
    elif d.get("booking"):
        target = get_object_or_404(Booking, pk=d["booking"], profile__user=user, status="completed")
        profile, kw = target.profile, {"booking": target}
    else:
        raise ValidationError("Nothing to rate.")
    if hasattr(target, "feedback"):
        raise ValidationError("You already rated this visit.")
    fb = Feedback.objects.create(profile=profile, rating=rating, comment=comment, **kw)
    if rating <= 2:  # a private heads-up lets the owner fix it before it becomes a lost customer
        who = user.first_name or "A customer"
        for m in _managers(profile.business):
            push(m, f"Low rating ({rating}★) from {who}: {comment or 'no comment'}", link="/app/#/insights")
    return Response(FeedbackSerializer(fb).data, status=201)


# --------------------------------------------------------------------------- owner: CRM, campaigns, insights
@api_view(["GET"])
def customers(request, code):
    biz = _owner_biz(request, code)
    rows, counts = engage.customer_rows(biz, request.GET.get("segment"), request.GET.get("q", "").strip(),
                                        request.GET.get("sort", "recent"))
    try:
        limit = max(1, min(int(request.GET.get("limit", 50)), 200))
        offset = max(0, int(request.GET.get("offset", 0)))
    except ValueError:
        limit, offset = 50, 0
    return Response({"count": len(rows), "segments": counts, "results": rows[offset:offset + limit]})


@api_view(["GET", "PATCH"])
def customer_detail(request, code, pid):
    biz = _owner_biz(request, code)
    p = get_object_or_404(CustomerProfile.objects.select_related("user"), pk=pid, business=biz)
    if request.method == "PATCH":
        if "note" in request.data:
            p.note = str(request.data["note"]).strip()[:300]
            p.save(update_fields=["note"])
    st = engage.shop_state(p)
    return Response({
        "id": p.id, "name": p.user.first_name or "…" + p.user.username[-4:], "mobile": p.user.username,
        "status": p.status, "note": p.note, "joined_at": p.joined_at, "marketing_consent": p.marketing_consent,
        "visits": st["visits"], "last_visit": st["last_visit"], "tier": st["tier"], "streak": st["streak"],
        "rewards": st["rewards"][:10], "tasks": st["tasks"],
        "entries": [{"id": e.id, "task_title": e.task.title, "value": str(e.value), "status": e.status,
                     "created_at": e.created_at, "multiplier": e.multiplier}
                    for e in p.entries.select_related("task").order_by("-created_at")[:15]],
        "ratings": FeedbackSerializer(p.feedback.order_by("-created_at")[:5], many=True).data,
        "referred": p.referred.count(),
    })


@api_view(["GET", "POST"])
def campaign(request, code):
    """Segment-targeted offer to customers who opted in. GET previews the audience size."""
    biz = _owner_biz(request, code)
    seg = (request.data.get("segment") if request.method == "POST" else request.GET.get("segment")) or "all"
    if seg != "all" and seg not in engage.SEGMENTS:
        raise ValidationError("Unknown audience.")
    rows, _ = engage.customer_rows(biz, None if seg == "all" else seg)
    ids = [r["id"] for r in rows if r["marketing_consent"] and r["status"] == "active"]
    if request.method == "GET":
        return Response({"audience": len(ids), "segment": seg})
    text = str(request.data.get("text", "")).strip()[:200]
    if not text:
        raise ValidationError("Write the offer text.")
    since = timezone.now() - timedelta(hours=24)
    sent_today = AuditLog.objects.filter(business=biz, action__startswith="campaign:", at__gte=since)
    if sent_today.filter(action=f"campaign:{seg}").exists():
        raise ValidationError("You already sent an offer to this audience today.")
    if sent_today.count() >= 3:
        raise ValidationError("Daily campaign limit reached (3). Customers should not be spammed.")
    for p in CustomerProfile.objects.filter(pk__in=ids).select_related("user"):
        push(p.user, f"{biz.name}: {text}", link=f"/b/{biz.shop_code}/?tab=earn")
    AuditLog.objects.create(business=biz, actor=request.user, action=f"campaign:{seg}", ref=str(len(ids)))
    return Response({"sent": len(ids)})


@api_view(["POST"])
def nudge_customer(request, code, pid):
    """One friendly reminder to one customer who agreed to offers. Max one per customer per 3 days, 20 a day per shop."""
    biz = _owner_biz(request, code)
    p = get_object_or_404(CustomerProfile.objects.select_related("user"), pk=pid, business=biz)
    if p.status != "active" or not p.marketing_consent:
        raise ValidationError("This customer has not agreed to receive offers.")
    now = timezone.now()
    if AuditLog.objects.filter(business=biz, action=f"nudge:{p.pk}", at__gte=now - timedelta(days=3)).exists():
        raise ValidationError("You already sent this customer a reminder in the last 3 days.")
    if AuditLog.objects.filter(business=biz, action__startswith="nudge:", at__gte=now - timedelta(hours=24)).count() >= 20:
        raise ValidationError("Daily reminder limit reached (20).")
    text = str(request.data.get("text", "")).strip()[:160] or "We miss you! Your next reward is waiting."
    push(p.user, f"{biz.name}: {text}", link=f"/b/{biz.shop_code}/?tab=earn")
    AuditLog.objects.create(business=biz, actor=request.user, action=f"nudge:{p.pk}", ref=str(p.pk))
    return Response({"sent": 1})


@api_view(["GET", "POST"])
@transaction.atomic
def winback(request, code):
    """Win-back gift: gives every consenting customer in a segment a real reward code (valid for a short time) and tells them.
    Shares the daily campaign limits so customers are never spammed."""
    from .models import RewardGrant
    biz = _owner_biz(request, code)
    seg = (request.data.get("segment") if request.method == "POST" else request.GET.get("segment")) or "lapsed"
    if seg not in engage.SEGMENTS or seg == "never":
        raise ValidationError("Choose who should get the gift.")
    rows, _ = engage.customer_rows(biz, seg)
    ids = [r["id"] for r in rows if r["marketing_consent"] and r["status"] == "active"]
    if request.method == "GET":
        return Response({"audience": len(ids), "segment": seg})
    title = str(request.data.get("title", "")).strip()[:120]
    if not title:
        raise ValidationError("Name the gift, for example: Free cookie.")
    offer_type = str(request.data.get("offer_type", "gift")).strip()
    type_map = {
        "percent_off": "percent_off",
        "flat_off": "flat_off",
        "free_item": "free_item",
        "fixed_price": "special_offer",
        "gift": "gift",
    }
    reward_type = type_map.get(offer_type)
    if not reward_type:
        raise ValidationError("Choose a valid offer type.")
    try:
        value = Decimal(str(request.data.get("value", 0) or 0))
        original_price = Decimal(str(request.data.get("original_price", 0) or 0))
        offer_price = Decimal(str(request.data.get("offer_price", 0) or 0))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError("Offer prices and values must be numbers.")
    if reward_type == "percent_off" and not 1 <= value <= 100:
        raise ValidationError("Percentage discount must be from 1 to 100.")
    if reward_type == "flat_off" and value <= 0:
        raise ValidationError("Fixed discount must be greater than zero.")
    if reward_type == "special_offer" and offer_price <= 0:
        raise ValidationError("Set a fixed offer price.")
    item_name = str(request.data.get("item_name", "")).strip()[:120]
    if offer_type in ("free_item", "fixed_price") and not item_name:
        raise ValidationError("Add an item name.")
    offer_image = request.FILES.get("image")
    if offer_image:
        if offer_image.size > 5 * 1024 * 1024:
            raise ValidationError("The product image must be 5 MB or smaller.")
        if offer_image.content_type not in ("image/jpeg", "image/png", "image/webp"):
            raise ValidationError("Upload a JPEG, PNG or WebP product image.")
    try:
        days = int(request.data.get("expiry_days", 7))
    except (TypeError, ValueError):
        raise ValidationError("Valid days must be a number.")
    if not 1 <= days <= 60:
        raise ValidationError("The gift can be valid for 1 to 60 days.")
    if not ids:
        raise ValidationError("Nobody in this group has agreed to receive offers yet.")
    since = timezone.now() - timedelta(hours=24)
    sent_today = AuditLog.objects.filter(business=biz, action__startswith="campaign:", at__gte=since)
    if sent_today.filter(action=f"campaign:winback:{seg}").exists():
        raise ValidationError("You already sent a gift to this group today.")
    if sent_today.count() >= 3:
        raise ValidationError("Daily campaign limit reached (3). Customers should not be spammed.")
    text = str(request.data.get("text", "")).strip()[:100] or "We miss you! A gift is waiting for you."
    reward = Reward.objects.create(
        business=biz, trigger="winback", type=reward_type, title=title, value=value,
        expiry_days=days, terms=str(request.data.get("terms", "")).strip()[:300],
        item_name=item_name, original_price=original_price, offer_price=offer_price,
        image=offer_image,
    )
    for p in CustomerProfile.objects.filter(pk__in=ids).select_related("user"):
        g = RewardGrant.objects.create(profile=p, reward=reward, expires_at=timezone.now() + timedelta(days=days))
        push(p.user, f"{biz.name}: {text} {title}, code {g.code}.", link=f"/b/{biz.shop_code}/?tab=rewards")
    AuditLog.objects.create(business=biz, actor=request.user, action=f"campaign:winback:{seg}", ref=str(len(ids)))
    return Response({"sent": len(ids), "reward_id": reward.pk})


@api_view(["GET"])
def insights(request, code):
    try:
        days = int(request.GET.get("days", 30))
    except ValueError:
        days = 30
    return Response(engage.insights(_owner_biz(request, code), days))


@api_view(["GET"])
def feedback_list(request, code):
    biz = _owner_biz(request, code)
    qs = Feedback.objects.filter(profile__business=biz).select_related("profile__user").order_by("-created_at")
    return Response(FeedbackSerializer(qs[:30], many=True).data)


@api_view(["GET", "POST", "DELETE"])
@transaction.atomic
def shop_offers(request, code):
    biz = _owner_biz(request, code)
    if request.method == "GET":
        offers = biz.offers.prefetch_related("items")
        return Response(ShopOfferSerializer(offers, many=True).data)
    if request.method == "DELETE":
        biz.offers.filter(active=True).update(active=False)
        return Response({"removed": True})

    offer_type = str(request.data.get("offer_type", "")).strip()
    if offer_type not in dict(ShopOffer.TYPES):
        raise ValidationError("Choose percentage off, fixed price, or buy one get one.")
    value = _dec(request.data.get("value", 0) or 0, "discount")
    if offer_type == "percent_off" and not 1 <= value <= 100:
        raise ValidationError("Percentage off must be from 1 to 100.")
    if offer_type != "percent_off":
        value = Decimal("0")
    try:
        items = json.loads(request.data.get("items", "[]"))
    except (TypeError, ValueError):
        raise ValidationError("Add valid offer items.")
    if not isinstance(items, list) or not 1 <= len(items) <= 20:
        raise ValidationError("Add between 1 and 20 items.")

    cleaned = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValidationError("Each item needs a name and price.")
        name = str(item.get("name", "")).strip()[:120]
        if not name:
            raise ValidationError("Add a name for every item.")
        price = _dec(item.get("price", 0), "item price")
        if price <= 0:
            raise ValidationError("Item price must be greater than zero.")
        offer_price = _dec(item.get("offer_price", 0) or 0, "offer price")
        if offer_type == "fixed_price" and (offer_price <= 0 or offer_price > price):
            raise ValidationError("Set a fixed offer price no higher than the item price.")
        if offer_type != "fixed_price":
            offer_price = Decimal("0")
        image = request.FILES.get(f"image_{index}")
        _offer_item_image(image)
        cleaned.append((name, price, offer_price, image))

    with transaction.atomic():
        offer = ShopOffer.objects.create(business=biz, offer_type=offer_type, value=value)
        for name, price, offer_price, image in cleaned:
            ShopOfferItem.objects.create(offer=offer, name=name, price=price, offer_price=offer_price, image=image)
    item_names = ", ".join(item[0] for item in cleaned[:3]) + (" and more" if len(cleaned) > 3 else "")
    offer_label = f"{value}% off" if offer_type == "percent_off" else (
        "fixed-price" if offer_type == "fixed_price" else "buy-one-get-one"
    )
    announce_shop_customers(
        biz, f"New {offer_label} offer at {biz.name}: {item_names}.",
        link=f"/b/{biz.shop_code}/",
    )
    offer = ShopOffer.objects.prefetch_related("items").get(pk=offer.pk)
    return Response(ShopOfferSerializer(offer).data, status=201)


@api_view(["PATCH", "DELETE"])
def shop_offer_detail(request, code, pk):
    biz = _owner_biz(request, code)
    offer = get_object_or_404(ShopOffer, pk=pk, business=biz)
    if request.method == "DELETE":
        images = list(offer.items.exclude(image="").values_list("image", flat=True))
        offer.delete()
        for image in images:
            default_storage.delete(image)
        return Response(status=204)
    if "active" not in request.data or not isinstance(request.data["active"], bool):
        raise ValidationError({"active": "Choose whether this offer is active."})
    offer.active = request.data["active"]
    offer.save(update_fields=["active"])
    return Response(ShopOfferSerializer(offer).data)


# --------------------------------------------------------------------------- owner: boosts, perks, blueprints
@api_view(["GET", "POST"])
def boosts(request, code):
    biz = _owner_biz(request, code)
    if request.method == "POST":
        s = BoostSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        s.save(business=biz)
        return Response(s.data, status=201)
    return Response(BoostSerializer(biz.boosts.order_by("-id"), many=True).data)


@api_view(["PATCH", "DELETE"])
def boost_detail(request, pk):
    b = get_object_or_404(Boost, pk=pk, business__owner=request.user)
    if request.method == "DELETE":
        b.delete()
        return Response(status=204)
    s = BoostSerializer(b, data=request.data, partial=True)
    s.is_valid(raise_exception=True)
    s.save()
    return Response(s.data)


def _perk(r):
    return {"title": r.title, "type": r.type, "value": str(r.value), "expiry_days": r.expiry_days, "terms": r.terms}


@api_view(["GET", "PUT"])
def perks(request, code):
    """Configure welcome, referral, and social-follow rewards for a shop."""
    biz = _owner_biz(request, code)
    if request.method == "PUT":
        new_perks = []
        with transaction.atomic():
            for trig in ("welcome", "referral", "social"):
                if trig not in request.data:
                    continue
                d = request.data[trig]
                cur = biz.perk_rewards.filter(trigger=trig).first()
                if not d:  # switch off but keep the row so rewards already in customers' wallets stay valid
                    if cur:
                        cur.trigger = "retired"
                        cur.save(update_fields=["trigger"])
                    continue
                title = str(d.get("title", "")).strip()[:120]
                rtype = d.get("type", "custom")
                if not title or rtype not in dict(Reward.TYPES):
                    raise ValidationError("Give the reward a title and a valid type.")
                try:
                    days = int(d.get("expiry_days", 30))
                except (TypeError, ValueError):
                    days = 30
                fields = {"title": title, "type": rtype, "value": _dec(d.get("value", 0)),
                          "expiry_days": max(1, min(days, 365)), "terms": str(d.get("terms", ""))[:300]}
                if cur:
                    for k, v in fields.items():
                        setattr(cur, k, v)
                    cur.save()
                else:
                    Reward.objects.create(business=biz, trigger=trig, **fields)
                    new_perks.append(title)
        if new_perks:
            names = ", ".join(new_perks)
            announce_shop_customers(
                biz, f"New reward at {biz.name}: {names}.",
                link=f"/b/{biz.shop_code}/?tab=earn",
            )
    out = {}
    for trig in ("welcome", "referral", "social"):
        r = biz.perk_rewards.filter(trigger=trig).first()
        out[trig] = _perk(r) if r else None
    return Response(out)


@api_view(["POST"])
@transaction.atomic
def social_follow_claim(request, code):
    user = _customer(request)
    biz = get_object_or_404(Business, shop_code=code)
    if not biz.is_live:
        raise ValidationError("This shop is not taking rewards right now.")
    profile = get_object_or_404(
        CustomerProfile.objects.select_for_update(), user=user, business=biz, status="active",
    )
    if not any(getattr(biz, field) for field in (
        "instagram_url", "facebook_url", "youtube_url", "tiktok_url", "x_url",
    )):
        raise ValidationError("This shop has not added a social profile yet.")
    if not biz.perk_rewards.filter(trigger="social").exists():
        raise ValidationError("This shop has not set up a social follow reward.")
    claim, created = SocialFollowClaim.objects.select_for_update().get_or_create(profile=profile)
    if not created and claim.status in ("pending", "approved"):
        raise ValidationError("You already have a social follow reward request for this shop.")
    claim.status = "pending"
    claim.requested_at = timezone.now()
    claim.reviewed_at = None
    claim.reviewed_by = None
    claim.reward_grant = None
    claim.save(update_fields=["status", "requested_at", "reviewed_at", "reviewed_by", "reward_grant"])
    for manager in _managers(biz):
        push(manager, f"{user.first_name or 'A customer'} requested the social follow reward at {biz.name}.",
             link="/app/")
    return Response({"status": claim.status}, status=201)


@api_view(["GET"])
def social_follow_claims(request, code):
    biz = _mgr_biz(request, code)
    claims = list(SocialFollowClaim.objects.filter(
        profile__business=biz, status="pending"
    ).select_related("profile__user").order_by("requested_at"))
    reward = biz.perk_rewards.filter(trigger="social").first()
    return Response({
        "enabled": bool(claims),
        "reward_configured": bool(reward),
        "claims": [{
            "id": claim.pk,
            "name": claim.profile.user.first_name or "Customer",
            "mobile_last4": claim.profile.user.username[-4:],
            "requested_at": claim.requested_at,
        } for claim in claims],
    })


@api_view(["POST"])
@transaction.atomic
def social_follow_claim_review(request, code, pk):
    biz = _mgr_biz(request, code)
    action = request.data.get("action")
    if action not in ("approve", "reject"):
        raise ValidationError("Choose approve or reject.")
    claim = get_object_or_404(
        SocialFollowClaim.objects.select_for_update().select_related("profile__user"),
        pk=pk, profile__business=biz,
    )
    if claim.status != "pending":
        raise ValidationError("This social follow request has already been reviewed.")
    now = timezone.now()
    title = ""
    if action == "approve":
        reward = biz.perk_rewards.filter(trigger="social").first()
        if not reward:
            raise ValidationError("Set up a social follow reward before approving this request.")
        grant = RewardGrant.objects.create(
            profile=claim.profile, reward=reward, expires_at=now + timedelta(days=reward.expiry_days),
        )
        claim.reward_grant = grant
        claim.status = "approved"
        title = reward.title
        push(claim.profile.user, f"{biz.name}: Your social follow reward is ready: {title}. Code {grant.code}.",
             link=f"/b/{biz.shop_code}/?tab=rewards")
    else:
        claim.status = "rejected"
        push(claim.profile.user, f"{biz.name} could not verify your follow. Follow a listed profile and request again.",
             link=f"/b/{biz.shop_code}/")
    claim.reviewed_by = request.user
    claim.reviewed_at = now
    claim.save(update_fields=["status", "reward_grant", "reviewed_by", "reviewed_at"])
    return Response({"status": claim.status, "reward_title": title})


@api_view(["GET"])
def blueprint_list(request):
    return Response(blueprints.catalog())


@api_view(["POST"])
@transaction.atomic
def blueprint_apply(request, code):
    biz = _owner_biz(request, code)
    key = request.data.get("key")
    if key not in blueprints.BLUEPRINTS:
        raise ValidationError("Unknown business type.")
    result = blueprints.apply(biz, key)
    announce_shop_customers(
        biz, f"New rewards are ready at {biz.name}. Visit the shop page to see them.",
        link=f"/b/{biz.shop_code}/?tab=earn",
    )
    return Response(result, status=201)


# --------------------------------------------------------------------------- services & bookings
@api_view(["GET", "POST"])
def services_(request, code):
    biz = _mgr_biz(request, code) if request.method == "GET" else _owner_biz(request, code)
    if request.method == "POST":
        s = ServiceSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        s.save(business=biz)
        return Response(s.data, status=201)
    return Response(ServiceSerializer(biz.services.order_by("id"), many=True).data)


@api_view(["PATCH", "DELETE"])
def service_detail(request, pk):
    sv = get_object_or_404(Service, pk=pk, business__owner=request.user)
    if request.method == "DELETE":
        if sv.bookings.exists():  # keep history: just hide it from the booking page
            sv.active = False
            sv.save(update_fields=["active"])
            return Response({"archived": True})
        sv.delete()
        return Response(status=204)
    s = ServiceSerializer(sv, data=request.data, partial=True)
    s.is_valid(raise_exception=True)
    s.save()
    return Response(s.data)


def _parse_when(raw):
    when = parse_datetime(str(raw or ""))
    if not when:
        raise ValidationError("Choose a date and time.")
    if timezone.is_naive(when):
        when = timezone.make_aware(when)
    now = timezone.now()
    if when < now + timedelta(minutes=15):
        raise ValidationError("Pick a time at least 15 minutes from now.")
    if when > now + timedelta(days=60):
        raise ValidationError("Bookings open up to 60 days ahead.")
    return when


@api_view(["GET", "POST"])
def bookings(request, code):
    if request.method == "GET":  # shop side: owner/staff queue
        biz = _mgr_biz(request, code)
        qs = Booking.objects.filter(profile__business=biz).select_related("service", "profile__user", "profile__business")
        st = request.GET.get("status")
        if st == "open":
            qs = qs.filter(status__in=("requested", "confirmed"), starts_at__gte=timezone.now() - timedelta(hours=6))
        elif st:
            qs = qs.filter(status=st)
        if request.GET.get("when") == "today":
            qs = qs.filter(starts_at__date=timezone.localdate())
        return Response(BookingSerializer(qs.order_by("starts_at")[:100], many=True).data)
    user = _customer(request)
    biz = get_object_or_404(Business, shop_code=code)
    if not biz.is_live or not biz.bookings_enabled:
        raise ValidationError("This shop is not taking bookings right now.")
    svc = get_object_or_404(Service, pk=request.data.get("service"), business=biz, active=True)
    when = _parse_when(request.data.get("starts_at"))
    p, _ = CustomerProfile.objects.get_or_create(user=user, business=biz)
    if p.status == "blocked":
        raise PermissionDenied("You cannot book at this shop.")
    mine = Booking.objects.filter(profile=p, status__in=("requested", "confirmed"), starts_at__gte=timezone.now())
    if mine.count() >= 3:
        raise ValidationError("You already have 3 upcoming bookings here.")
    if mine.filter(starts_at__lt=when + timedelta(minutes=svc.duration_min),
                   starts_at__gt=when - timedelta(minutes=svc.duration_min)).exists():
        raise ValidationError("You already have a booking around that time.")
    b = Booking.objects.create(profile=p, service=svc, starts_at=when, note=str(request.data.get("note", ""))[:200])
    local = timezone.localtime(when)
    for m in _managers(biz):
        push(m, f"New booking request: {user.first_name or user.username} - {svc.name}, {local:%d %b %I:%M %p}", link="/app/#/bookings")
    return Response(BookingSerializer(b).data, status=201)


@api_view(["GET"])
def my_bookings(request):
    user = _customer(request)
    qs = Booking.objects.filter(profile__user=user, profile__hidden_from_customer=False).select_related(
        "service", "profile__user", "profile__business").order_by("-starts_at")[:30]
    return Response(BookingSerializer(qs, many=True).data)


@api_view(["POST"])
def booking_action(request, pk):
    b = get_object_or_404(Booking.objects.select_related("profile__business", "profile__user", "service"), pk=pk)
    biz, action = b.profile.business, request.data.get("action")
    mine = b.profile.user_id == request.user.id
    if action == "cancel" and mine:
        pass
    elif not can_manage(request.user, biz):
        raise PermissionDenied()
    when = f"{timezone.localtime(b.starts_at):%d %b %I:%M %p}"
    if action == "complete":
        b = services.complete_booking(b, request.user)
        return Response(BookingSerializer(b).data)
    rules = {"confirm": ("requested", "confirmed"), "decline": ("requested", "declined"),
             "no_show": ("confirmed", "no_show"), "cancel": (("requested", "confirmed"), "cancelled")}
    if action not in rules:
        raise ValidationError("Unknown action.")
    allowed, new = rules[action]
    allowed = (allowed,) if isinstance(allowed, str) else allowed
    if b.status not in allowed:
        raise ValidationError(f"A {b.status} booking cannot be changed this way.")
    b.status = new
    b.save(update_fields=["status"])
    if mine:
        for m in _managers(biz):
            push(m, f"Booking cancelled by {request.user.first_name or request.user.username}: {b.service.name}, {when}", link="/app/#/bookings")
    else:
        msg = {"confirmed": "is confirmed", "declined": "could not be accepted", "cancelled": "was cancelled",
               "no_show": "was marked as missed"}[new]
        push(b.profile.user, f"{biz.name}: your {b.service.name} booking on {when} {msg}.", link=f"/b/{biz.shop_code}/?tab=book")
    return Response(BookingSerializer(b).data)
