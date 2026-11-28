"""Business rules: submit / review purchases, progress, reward grants, redemption."""
from datetime import timedelta
from decimal import Decimal, InvalidOperation
import secrets
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, Sum
from . import counter, engage
from .notify import push
from .models import (AuditLog, Booking, CodeUse, CoinAccount, CoinProgram, CoinTransaction, CustomerProfile,
                     PurchaseEntry, Reward, RewardGrant, RewardRedemptionRequest, ScratchCampaign,
                     ScratchTicket, Task, TaskProgress, can_manage)


def _log(business, actor, action, ref=""):
    AuditLog.objects.create(business=business, actor=actor, action=action, ref=str(ref))


@transaction.atomic
def submit_entry(profile, task, value, bill_photo=None, counter_code="", lat=None, lng=None):
    biz = profile.business
    if profile.status == "blocked":
        raise PermissionDenied("You cannot earn rewards at this shop.")
    if not biz.is_live or not task.program.active or task.program.business_id != biz.id:
        raise ValidationError("This offer is not active.")
    now = timezone.now()
    mine = PurchaseEntry.objects.filter(profile=profile).exclude(status="rejected")
    last = mine.order_by("-created_at").first()
    if last and now - last.created_at < timedelta(minutes=biz.cooldown_minutes):
        raise ValidationError(f"Please wait {biz.cooldown_minutes} minutes between entries.")
    if mine.filter(created_at__date=timezone.localdate()).count() >= biz.daily_cap:
        raise ValidationError("Daily entry limit reached.")
    if task.type == "visit":
        value = Decimal("1")
    else:
        try:
            value = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError("Enter a valid quantity or amount.")
        if not value.is_finite() or value <= 0 or value > Decimal("99999999.99"):
            raise ValidationError("Quantity or amount is outside the allowed range.")
        if value.quantize(Decimal("0.01")) != value:
            raise ValidationError("Amounts can have at most two decimal places.")
        if task.type == "count" and value != value.to_integral_value():
            raise ValidationError("Quantity must be a whole number.")
    far, dist = False, None
    if None not in (lat, lng, biz.lat, biz.lng):
        dist = int(_dist_m(lat, lng, biz.lat, biz.lng))
        far = dist > biz.max_distance_m  # soft check: flagged for the owner, never auto-approved
    if biz.require_bill_photo and not bill_photo:
        raise ValidationError("Please attach the bill photo.")
    step = None
    if counter_code:
        step = counter.match(biz, counter_code)
        if step is None:
            raise ValidationError("Counter code expired or wrong. Ask the staff for the current code.")
        if CodeUse.objects.filter(business=biz, step=step, profile=profile).exists():
            raise ValidationError("You already used this code.")
        if CodeUse.objects.filter(business=biz, step=step).count() >= 20:
            raise ValidationError("This code was used too many times. Ask for the new code.")
    entry = PurchaseEntry.objects.create(profile=profile, task=task, value=value, bill_photo=bill_photo or "", far=far, distance_m=dist)
    _log(biz, profile.user, "entry_submitted", entry.id)
    if step is not None:
        CodeUse.objects.create(business=biz, step=step, profile=profile)
        _log(biz, None, "counter_code_used", entry.id)
    if not far and (step is not None or biz.approval_mode == "auto"):
        review_entry(entry, None, approve=True)
        entry.refresh_from_db()
    else:
        for u in [biz.owner] + [s.user for s in biz.staff.all()]:
            push(u, f"New purchase pending: {profile.user.first_name or profile.user.username} - {task.title}" + (" (far from shop)" if far else ""), link="/app/#/")
    return entry


@transaction.atomic
def review_entry(entry, actor, approve):
    entry = PurchaseEntry.objects.select_for_update().select_related("profile__business", "task").get(pk=entry.pk)
    if entry.status != "pending":
        raise ValidationError("Entry already reviewed.")
    biz = entry.profile.business
    if actor and not can_manage(actor, biz):
        raise PermissionDenied()
    entry.status = "approved" if approve else "rejected"
    entry.reviewed_by, entry.reviewed_at = actor, timezone.now()
    entry.save()
    _log(biz, actor, entry.status, entry.id)
    push(entry.profile.user, f"{biz.name}: your purchase was {entry.status}.", link=f"/b/{biz.shop_code}/?tab=earn")
    if approve:
        issue_purchase_rewards(entry)
        _apply_progress(entry)
        engage.after_approval(entry.profile)
    return entry


def issue_purchase_rewards(entry):
    profile = CustomerProfile.objects.select_for_update().get(pk=entry.profile_id)
    biz = profile.business
    config = CoinProgram.objects.select_for_update().filter(business=biz, enabled=True).first()
    if config:
        # amount tasks earn per rupee spent; visit/count tasks earn a flat number of coins per approved entry
        if entry.task.type == "amount":
            coins = int(entry.value // config.spend_per_coin) if config.spend_per_coin else 0
        else:
            coins = config.visit_coins
        if coins:
            account, _ = CoinAccount.objects.get_or_create(profile=profile)
            account = CoinAccount.objects.select_for_update().get(pk=account.pk)
            earned_today = CoinTransaction.objects.filter(
                account=account, kind="purchase", created_at__date=timezone.localdate(),
            ).aggregate(total=Sum("delta"))["total"] or 0
            coins = min(coins, max(0, config.daily_cap - earned_today))
            if coins:
                account.balance += coins
                account.save(update_fields=["balance", "updated_at"])
                CoinTransaction.objects.create(account=account, delta=coins, kind="purchase", purchase_entry=entry)
                push(profile.user, f"You earned {coins} coin{'s' if coins != 1 else ''} at {biz.name}.",
                     link=f"/b/{biz.shop_code}/?tab=rewards")

    campaign = ScratchCampaign.objects.select_for_update().filter(
        business=biz, active=True,
    ).first()
    if not campaign or not campaign.prize_title or not campaign.cards_per_deck:
        return
    if campaign.cards_issued >= campaign.cards_per_deck:
        campaign.deck_number += 1
        campaign.cards_issued = 0
        campaign.wins_issued = 0
    cards_left = campaign.cards_per_deck - campaign.cards_issued
    wins_left = max(0, campaign.winning_cards - campaign.wins_issued)
    is_winner = wins_left > 0 and secrets.randbelow(cards_left) < wins_left
    ticket = ScratchTicket.objects.create(
        profile=profile, campaign=campaign, purchase_entry=entry, deck_number=campaign.deck_number,
        is_winner=is_winner, prize_title=campaign.prize_title if is_winner else "",
        prize_type=campaign.prize_type if is_winner else "", prize_value=campaign.prize_value if is_winner else 0,
        prize_terms=campaign.prize_terms if is_winner else "", expiry_days=campaign.expiry_days,
    )
    campaign.cards_issued += 1
    campaign.wins_issued += int(is_winner)
    campaign.save(update_fields=["deck_number", "cards_issued", "wins_issued", "updated_at"])
    push(profile.user, f"Scratch card ready at {biz.name}.", link=f"/b/{biz.shop_code}/?tab=rewards")
    return ticket


@transaction.atomic
def reveal_scratch_ticket(ticket_id, user):
    ticket = ScratchTicket.objects.select_for_update().select_related(
        "profile__business", "profile__user",
    ).get(pk=ticket_id, profile__user=user)
    if ticket.revealed_at:
        return ticket, False
    if not ticket.valid or ticket.purchase_entry.status != "approved":
        raise ValidationError("This scratch card is no longer valid.")
    ticket.revealed_at = timezone.now()
    if ticket.is_winner:
        reward = Reward.objects.create(
            business=ticket.profile.business, title=ticket.prize_title, type=ticket.prize_type,
            value=ticket.prize_value, expiry_days=ticket.expiry_days, terms=ticket.prize_terms,
            trigger="spin",
        )
        ticket.reward_grant = RewardGrant.objects.create(
            profile=ticket.profile, reward=reward,
            expires_at=ticket.revealed_at + timedelta(days=ticket.expiry_days),
        )
    ticket.save(update_fields=["revealed_at", "reward_grant"])
    return ticket, True


def _apply_progress(entry):
    task, profile = entry.task, entry.profile
    prog, _ = TaskProgress.objects.select_for_update().get_or_create(profile=profile, task=task)
    if prog.target is None:
        prog.target = task.target  # snapshot: later edits do not change this customer's goal
    mult = engage.multiplier_for(profile.business, entry.created_at, task)
    credit = entry.value * mult
    entry.multiplier, entry.credited_value = mult, credit  # remembered so Undo reverses exactly what was credited
    entry.save(update_fields=["multiplier", "credited_value"])
    prog.current_value += credit
    if task.repeatable:
        cap = task.max_per_customer or None  # 0 = unlimited
    else:
        cap = 1
    while prog.current_value >= prog.target and (cap is None or prog.completed_count < cap):
        prog.current_value -= prog.target
        prog.completed_count += 1
        prog.target = task.target  # next cycle uses the latest target
        for r in task.rewards.all():
            g = RewardGrant.objects.create(profile=profile, reward=r,
                                           expires_at=timezone.now() + timedelta(days=r.expiry_days))
            push(profile.user, f"Reward unlocked at {profile.business.name}: {r.title}. Code {g.code}", sms=True,
                 link=f"/b/{profile.business.shop_code}/?tab=rewards")
    if cap is not None and prog.completed_count >= cap:
        prog.current_value = Decimal("0")
    prog.save()
    # nudge: one step from a reward is the moment a customer is most likely to come back
    first = task.rewards.first()
    if (first and task.type != "amount" and (cap is None or prog.completed_count < cap)
            and prog.target > 1 and 0 < prog.target - prog.current_value <= 1 and prog.current_value > 0):
        push(profile.user, f"Almost there! One more {'visit' if task.type == 'visit' else 'stamp'} at "
                           f"{profile.business.name} unlocks: {first.title}.", link=f"/b/{profile.business.shop_code}/?tab=earn")


def _grant_for_shop(code, shop_code, actor, *, lock=False):
    grants = RewardGrant.objects.select_related("profile__business", "profile__user", "reward")
    if lock:
        grants = grants.select_for_update()
    try:
        g = grants.get(code=str(code).strip().upper())
    except RewardGrant.DoesNotExist:
        raise ValidationError("Invalid code.")
    biz = g.profile.business
    if not can_manage(actor, biz):
        raise ValidationError("Invalid code.")
    if not shop_code or str(shop_code).strip() != biz.shop_code:
        raise ValidationError("Invalid code.")
    return g


@transaction.atomic
def redeem(code, shop_code, actor):
    g = _grant_for_shop(code, shop_code, actor, lock=True)
    biz = g.profile.business
    if g.status != "active":
        raise ValidationError(f"Reward already {g.status}.")
    if g.expires_at < timezone.now():
        g.status = "expired"; g.save()
        raise ValidationError("Reward expired.")
    g.status, g.redeemed_at = "used", timezone.now()
    g.save()
    RewardRedemptionRequest.objects.filter(grant=g, status="pending").update(
        status="cancelled", reviewed_at=g.redeemed_at, reviewed_by=actor,
    )
    _log(biz, actor, "redeemed", g.code)
    return g


def _dist_m(lat1, lng1, lat2, lng2):
    from math import asin, cos, radians, sin, sqrt
    a = sin(radians(lat2 - lat1) / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(radians(lng2 - lng1) / 2) ** 2
    return 6371000 * 2 * asin(sqrt(a))


@transaction.atomic
def reverse_entry(entry, actor):
    entry = PurchaseEntry.objects.select_for_update().select_related("profile__business", "task").get(pk=entry.pk)
    biz = entry.profile.business
    if not can_manage(actor, biz):
        raise PermissionDenied()
    if entry.status != "approved":
        raise ValidationError("Only approved entries can be undone.")
    if not entry.reviewed_at or timezone.now() > entry.reviewed_at + timedelta(seconds=5):
        raise ValidationError("The 5-second undo window has expired.")
    if PurchaseEntry.objects.filter(
        profile=entry.profile, task=entry.task, status="approved", reviewed_at__gt=entry.reviewed_at,
    ).exists():
        raise ValidationError("A newer purchase has already been approved for this task.")
    if RewardGrant.objects.select_for_update().filter(
        profile=entry.profile, reward__task=entry.task, status="used", issued_at__gte=entry.reviewed_at,
    ).exists():
        raise ValidationError("This purchase cannot be undone because its reward was already redeemed.")
    ticket = ScratchTicket.objects.select_for_update().filter(purchase_entry=entry).first()
    if ticket and ticket.revealed_at:
        raise ValidationError("This purchase cannot be undone after its scratch card was revealed.")
    coin_tx = CoinTransaction.objects.select_for_update().filter(purchase_entry=entry).first()
    account = None
    if coin_tx:
        account = CoinAccount.objects.select_for_update().get(pk=coin_tx.account_id)
        if account.balance < coin_tx.delta:
            raise ValidationError("This purchase cannot be undone because some earned coins have already been spent.")
    task = entry.task
    prog = TaskProgress.objects.select_for_update().get(profile=entry.profile, task=task)
    tgt = prog.target or task.target
    prog.current_value -= entry.credited_value if entry.credited_value is not None else entry.value
    while prog.current_value < 0 and prog.completed_count > 0:
        prog.completed_count -= 1
        prog.current_value += tgt
        g = RewardGrant.objects.filter(profile=entry.profile, reward__task=task, status="active").order_by("-id").first()
        if g:
            g.status = "revoked"; g.save()
    prog.current_value = max(prog.current_value, 0)
    prog.save()
    if coin_tx:
        account.balance -= coin_tx.delta
        account.save(update_fields=["balance", "updated_at"])
        CoinTransaction.objects.create(account=account, delta=-coin_tx.delta, kind="reversal", reversal_of=coin_tx)
    if ticket:
        ticket.valid = False
        ticket.save(update_fields=["valid"])
    entry.status = "reversed"; entry.save()
    _log(biz, actor, "reversed", entry.id)
    push(entry.profile.user, f"{biz.name}: your purchase approval was undone.", link=f"/b/{biz.shop_code}/?tab=history")
    return entry


@transaction.atomic
def complete_booking(booking, actor):
    """Staff marks an appointment as done. The visit is credited to every live program (visit tasks +1, amount
    tasks += service price, count tasks +1 when they are not tied to a different item), exactly once."""
    booking = Booking.objects.select_for_update().select_related("profile__business", "profile__user", "service").get(pk=booking.pk)
    biz = booking.profile.business
    if not can_manage(actor, biz):
        raise PermissionDenied()
    if booking.status not in ("requested", "confirmed"):
        raise ValidationError("This booking is already closed.")
    booking.status = "completed"
    credited = []
    if not booking.credited and booking.profile.status == "active" and biz.is_live:
        today = timezone.localdate()
        tasks = Task.objects.filter(program__business=biz, program__active=True).filter(
            Q(program__start__isnull=True) | Q(program__start__lte=today)).filter(
            Q(program__end__isnull=True) | Q(program__end__gte=today))
        for t in tasks:
            if t.type == "amount":
                v = booking.service.price
            elif t.type == "visit" or not t.item_name or t.item_name.strip().lower() == booking.service.name.strip().lower():
                v = Decimal("1")
            else:
                continue
            if v <= 0:
                continue
            e = PurchaseEntry.objects.create(profile=booking.profile, task=t, value=v, status="approved",
                                             reviewed_by=actor, reviewed_at=timezone.now())
            _apply_progress(e)
            credited.append(e.id)
        if credited:
            engage.after_approval(booking.profile)
        booking.credited = True
    booking.save()
    _log(biz, actor, "booking_completed", booking.id)
    push(booking.profile.user, f"{biz.name}: thanks for visiting! Your {booking.service.name} visit is recorded."
         + (" Check your progress." if credited else ""))
    return booking


def lookup_grant(code, shop_code, actor):
    """Read-only preview for the redeem screen, so staff confirm the right customer and reward before tapping Redeem."""
    g = _grant_for_shop(code, shop_code, actor)
    biz = g.profile.business
    expired = g.status == "active" and g.expires_at < timezone.now()
    status = "expired" if expired else g.status
    return {"code": g.code, "reward": g.reward.title, "terms": g.reward.terms, "status": status,
            "redeemable": status == "active", "expires_at": g.expires_at, "shop": biz.name,
            "customer": g.profile.user.first_name or "Customer", "customer_mobile_tail": g.profile.user.username[-4:],
            "issued_at": g.issued_at, "redeemed_at": g.redeemed_at}
