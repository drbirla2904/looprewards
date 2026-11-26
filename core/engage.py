"""v2 engagement layer: tiers, streaks, boosts, welcome/referral perks, segments, insights, customer wallet.

Rules of thumb used everywhere below:
* a *visit* is one calendar day (shop-local) with at least one approved entry, so a booking that credits two
  tasks, or a customer who buys twice in an afternoon, still counts as one visit;
* a customer's *segment* is derived from visits + recency, never stored, so it can never go stale.
"""
import secrets
import string
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import (AuditLog, Booking, CustomerProfile, Feedback, Program, PurchaseEntry, RewardGrant,
                     TaskProgress)
from .notify import push

SEGMENTS = ("never", "new", "regular", "at_risk", "lapsed")
_MON0 = date(2000, 1, 3)  # a Monday, anchor for week arithmetic
_REF_ALPHABET = "".join(c for c in string.ascii_uppercase if c not in "IO") + "23456789"


# --------------------------------------------------------------------------- referral codes
def ensure_ref_code(profile):
    """Referral codes are created lazily so existing customers get one the first time it is needed."""
    if profile.referral_code:
        return profile.referral_code
    for _ in range(20):
        code = "".join(secrets.choice(_REF_ALPHABET) for _ in range(6))
        if not CustomerProfile.objects.filter(referral_code=code).exists():
            profile.referral_code = code
            profile.save(update_fields=["referral_code"])
            return code
    raise RuntimeError("could not allocate a referral code")


# --------------------------------------------------------------------------- tiers & streaks
def tier_ladder(biz):
    ladder = [("member", 0, "")]
    if biz.tier_silver_visits:
        ladder.append(("silver", biz.tier_silver_visits, biz.silver_perk))
    if biz.tier_gold_visits and biz.tier_gold_visits > biz.tier_silver_visits:
        ladder.append(("gold", biz.tier_gold_visits, biz.gold_perk))
    return ladder


def tier_info(biz, visits):
    ladder = tier_ladder(biz)
    cur = max((t for t in ladder if visits >= t[1]), key=lambda t: t[1])
    nxt = next((t for t in ladder if t[1] > visits), None)
    return {"tier": cur[0], "perk": cur[2], "visits": visits,
            "next": nxt[0] if nxt else None, "next_at": nxt[1] if nxt else None,
            "to_next": (nxt[1] - visits) if nxt else 0, "next_perk": nxt[2] if nxt else ""}


def visit_days(profile):
    qs = PurchaseEntry.objects.filter(profile=profile, status="approved").values_list("created_at", flat=True)
    return sorted({timezone.localtime(c).date() for c in qs})


def streak_weeks(days, today=None):
    """Consecutive calendar weeks (Mon-Sun) with a visit. The current week may still be empty without breaking it."""
    today = today or timezone.localdate()
    weeks = {(d - _MON0).days // 7 for d in days}
    cur = (today - _MON0).days // 7
    w = cur if cur in weeks else cur - 1
    n = 0
    while w in weeks:
        n += 1
        w -= 1
    return n, cur in weeks


# --------------------------------------------------------------------------- boosts
def active_boosts(biz, when=None):
    when = timezone.localtime(when or timezone.now())
    out = []
    for b in biz.boosts.filter(active=True):
        if (b.start and when.date() < b.start) or (b.end and when.date() > b.end):
            continue
        if b.weekdays:
            days = {int(x) for x in b.weekdays.split(",") if x.strip().isdigit()}
            if when.weekday() not in days:
                continue
        if b.start_time and b.end_time:
            t = when.time()
            inside = (b.start_time <= t < b.end_time) if b.start_time <= b.end_time else (t >= b.start_time or t < b.end_time)
            if not inside:
                continue
        out.append(b)
    return out


def multiplier_for(biz, when, task):
    """Boosts never stack (the best one wins) and never apply to amount tasks (money is money)."""
    if task.type == "amount":
        return 1
    return max([b.multiplier for b in active_boosts(biz, when)], default=1)


def boost_dict(b):
    return {"id": b.id, "title": b.title, "multiplier": b.multiplier}


# --------------------------------------------------------------------------- welcome / referral perks
def _grant(profile, reward):
    g = RewardGrant.objects.create(profile=profile, reward=reward,
                                   expires_at=timezone.now() + timedelta(days=reward.expiry_days))
    push(profile.user, f"Reward unlocked at {profile.business.name}: {reward.title}. Code {g.code}", sms=True,
         link=f"/b/{profile.business.shop_code}/?tab=rewards")
    return g


def after_approval(profile):
    """Run inside the approval transaction. First approved purchase => welcome perk for the customer and a
    referral perk for whoever invited them. AuditLog rows make both exactly-once, even after an undo."""
    biz = profile.business
    if len(visit_days(profile)) != 1:  # only the very first visit day triggers perks
        return
    if not AuditLog.objects.filter(business=biz, action="perk_welcome", ref=str(profile.id)).exists():
        reward = biz.perk_rewards.filter(trigger="welcome").first()
        AuditLog.objects.create(business=biz, actor=None, action="perk_welcome", ref=str(profile.id))
        if reward:
            _grant(profile, reward)
    ref = profile.referred_by
    if ref and ref.status == "active" and not AuditLog.objects.filter(
            business=biz, action="perk_referral", ref=str(profile.id)).exists():
        reward = biz.perk_rewards.filter(trigger="referral").first()
        AuditLog.objects.create(business=biz, actor=None, action="perk_referral", ref=str(profile.id))
        if reward:
            _grant(ref, reward)
            friend = profile.user.first_name or "Your friend"
            push(ref.user, f"{friend} made a first purchase at {biz.name}, so you earned: {reward.title}", link=f"/b/{biz.shop_code}/?tab=rewards")


# --------------------------------------------------------------------------- CRM & segments
def segment_of(visits, last, now=None):
    now = now or timezone.now()
    if not visits or not last:
        return "never"
    age = (now - last).days
    if age <= 30:
        return "regular" if visits >= 3 else "new"
    return "at_risk" if age <= 60 else "lapsed"


def customers_qs(biz):
    ok = Q(entries__status="approved")
    return CustomerProfile.objects.filter(business=biz).select_related("user").annotate(
        visits=Count(TruncDate("entries__created_at"), distinct=True, filter=ok),
        last=Max("entries__created_at", filter=ok),
        first=Min("entries__created_at", filter=ok),
        spend=Sum("entries__value", filter=ok & Q(entries__task__type="amount")),
    )


def customer_rows(biz, segment=None, q="", sort="recent"):
    now = timezone.now()
    active_rewards = dict(RewardGrant.objects.filter(
        profile__business=biz, status="active", expires_at__gt=now).values_list("profile_id").annotate(n=Count("id")))
    rows = []
    for c in customers_qs(biz):
        seg = segment_of(c.visits, c.last, now)
        name = c.user.first_name or ""
        if q and q.lower() not in name.lower() and q not in c.user.username:
            continue
        rows.append({
            "id": c.id, "name": name or ("…" + c.user.username[-4:]), "mobile": c.user.username,
            "visits": c.visits, "spend": str(c.spend or 0), "last_visit": c.last, "joined_at": c.joined_at,
            "segment": seg, "tier": tier_info(biz, c.visits)["tier"], "status": c.status, "note": c.note,
            "marketing_consent": c.marketing_consent, "active_rewards": active_rewards.get(c.id, 0),
            "image": c.user.profile_image.url if c.user.profile_image else "",
        })
    counts = Counter(r["segment"] for r in rows)
    if segment and segment != "all":
        rows = [r for r in rows if r["segment"] == segment]
    keys = {"recent": lambda r: r["last_visit"] or r["joined_at"], "visits": lambda r: r["visits"],
            "spend": lambda r: Decimal(r["spend"])}
    rows.sort(key=keys.get(sort, keys["recent"]), reverse=True)
    return rows, {s: counts.get(s, 0) for s in SEGMENTS}


# --------------------------------------------------------------------------- insights
def insights(biz, days=30):
    days = max(7, min(int(days), 180))
    now = timezone.now()
    today = timezone.localdate()
    since = today - timedelta(days=days - 1)
    custs = list(customers_qs(biz))
    first_by = {c.id: timezone.localtime(c.first).date() for c in custs if c.first}
    seg_counts = Counter(segment_of(c.visits, c.last, now) for c in custs)
    buyers = [c for c in custs if c.visits >= 1]

    rows = PurchaseEntry.objects.filter(profile__business=biz, status="approved",
                                        created_at__date__gte=since).values_list(
        "profile_id", "created_at", "value", "task__type")
    per_day, weekday, hours = defaultdict(set), Counter(), Counter()
    seen_pairs, returning_pairs = set(), set()
    sales = returning_sales = Decimal(0)
    for pid, created, value, ttype in rows:
        d = timezone.localtime(created)
        day = d.date()
        per_day[day].add(pid)
        if (pid, day) not in seen_pairs:
            seen_pairs.add((pid, day))
            weekday[day.weekday()] += 1
            hours[d.hour] += 1
            if first_by.get(pid) and day > first_by[pid]:
                returning_pairs.add((pid, day))
        if ttype == "amount":
            sales += value
            if first_by.get(pid) and day > first_by[pid]:
                returning_sales += value
    joined = Counter(timezone.localtime(c.joined_at).date() for c in custs if c.joined_at.date() >= since - timedelta(days=1))
    series = []
    for i in range(days):
        d = since + timedelta(days=i)
        series.append({"date": d.isoformat(), "visits": len(per_day.get(d, ())), "new": joined.get(d, 0)})

    grants = RewardGrant.objects.filter(profile__business=biz)
    issued = grants.count()
    used = grants.filter(status="used").count()
    fb = Feedback.objects.filter(profile__business=biz)
    fb_stats = fb.aggregate(total=Sum("rating"), n=Count("id"))
    dist = {k: fb.filter(rating=k).count() for k in range(1, 6)}
    active_30 = sum(1 for c in custs if c.last and (now - c.last).days <= 30)
    total_pairs = len(seen_pairs)
    out = {
        "days": days,
        "kpis": {
            "customers": len(custs), "active_30d": active_30,
            "new_in_period": sum(1 for c in custs if c.joined_at.date() >= since),
            "repeat_rate": round(100 * sum(c.visits >= 2 for c in buyers) / len(buyers)) if buyers else 0,
            "visits_in_period": total_pairs,
            "returning_share": round(100 * len(returning_pairs) / total_pairs) if total_pairs else 0,
            "tracked_sales": str(sales), "returning_sales": str(returning_sales),
            "rewards_issued": issued, "rewards_redeemed": used,
            "redeem_rate": round(100 * used / issued) if issued else 0,
            "rating_avg": round(fb_stats["total"] / fb_stats["n"], 1) if fb_stats["n"] else None,
            "rating_count": fb_stats["n"], "pending": PurchaseEntry.objects.filter(
                profile__business=biz, status="pending").count(),
            "bookings_upcoming": Booking.objects.filter(
                profile__business=biz, status__in=("requested", "confirmed"), starts_at__gte=now).count(),
        },
        "segments": {s: seg_counts.get(s, 0) for s in SEGMENTS},
        "series": series,
        "weekday": [weekday.get(i, 0) for i in range(7)],
        "hours": [{"hour": h, "count": n} for h, n in sorted(hours.items())],
        "ratings": dist,
        "tips": [],
    }
    out["tips"] = _tips(biz, out)
    return out


def _tips(biz, d):
    tips, k, seg = [], d["kpis"], d["segments"]
    if seg["at_risk"] + seg["lapsed"] >= 3:
        tips.append({"key": "winback", "n": seg["at_risk"] + seg["lapsed"]})
    if sum(d["weekday"]) >= 20 and not biz.boosts.filter(active=True).exists():
        quiet = min(range(7), key=lambda i: d["weekday"][i])
        tips.append({"key": "boost", "weekday": quiet})
    if k["rating_count"] and k["rating_avg"] is not None and k["rating_avg"] < 4:
        tips.append({"key": "reviews", "avg": k["rating_avg"]})
    if k["customers"] and not biz.perk_rewards.filter(trigger="referral").exists():
        tips.append({"key": "referral"})
    if k["redeem_rate"] < 30 and k["rewards_issued"] >= 10:
        tips.append({"key": "redeem", "rate": k["redeem_rate"]})
    return tips


# --------------------------------------------------------------------------- customer wallet
def _live_programs(biz):
    today = timezone.localdate()
    return Program.objects.filter(business=biz, active=True).filter(
        Q(start__isnull=True) | Q(start__lte=today)).filter(Q(end__isnull=True) | Q(end__gte=today))


def shop_state(profile):
    """Everything the customer UI needs for one shop: tier, streak, per-task progress, best next reward."""
    biz, now = profile.business, timezone.now()
    days = visit_days(profile)
    streak, this_week = streak_weeks(days)
    prog = {p.task_id: p for p in TaskProgress.objects.filter(profile=profile)}
    tasks = []
    for pr in _live_programs(biz).prefetch_related("tasks__rewards"):
        for t in pr.tasks.all():
            p = prog.get(t.id)
            cur = p.current_value if p else Decimal(0)
            tgt = (p.target if p and p.target else t.target)
            tasks.append({"task_id": t.id, "title": t.title, "type": t.type, "item_name": t.item_name,
                          "current": str(cur), "target": str(tgt), "completed": p.completed_count if p else 0,
                          "pct": float(min(100, (cur / tgt * 100) if tgt else 0)),
                          "repeatable": t.repeatable, "program": pr.title,
                          "rewards": [{"title": r.title, "type": r.type, "value": str(r.value)} for r in t.rewards.all()]})
    best = max((t for t in tasks if t["rewards"]), key=lambda t: t["pct"], default=None)
    grants = list(profile.grants.select_related("reward").order_by("expires_at"))
    active = [g for g in grants if g.status == "active" and g.expires_at > now]
    return {
        "visits": len(days), "last_visit": days[-1].isoformat() if days else None,
        "tier": tier_info(biz, len(days)), "streak": streak, "streak_this_week": this_week,
        "tasks": tasks, "best": best,
        "rewards": [{"title": g.reward.title, "type": g.reward.type, "value": str(g.reward.value),
                     "terms": g.reward.terms, "code": g.code, "status": g.status, "expires_at": g.expires_at,
                     "trigger": g.reward.trigger, "item_name": g.reward.item_name,
                     "original_price": str(g.reward.original_price), "offer_price": str(g.reward.offer_price),
                     "image": g.reward.image.url if g.reward.image else ""} for g in grants],
        "active_rewards": len(active), "next_expiry": active[0].expires_at if active else None,
        "boosts_now": [boost_dict(b) for b in active_boosts(biz)],
    }


def wallet(user):
    from .blueprints import BLUEPRINTS

    shops, total_rewards, total_visits = [], 0, 0
    profiles = list(user.profiles.filter(hidden_from_customer=False).select_related("business"))
    ratings = Feedback.objects.filter(
        profile__business_id__in=[p.business_id for p in profiles]
    ).filter(
        Q(entry__status="approved") | Q(booking__status="completed")
    ).values("profile__business_id").annotate(average=Avg("rating"), count=Count("id"))
    rating_by_business = {r["profile__business_id"]: r for r in ratings}
    for p in profiles:
        biz = p.business
        if biz.status == "closed":
            continue
        st = shop_state(p)
        rating = rating_by_business.get(biz.id)
        category = BLUEPRINTS.get(biz.category, BLUEPRINTS["other"])
        upcoming = Booking.objects.filter(profile=p, status__in=("requested", "confirmed"),
                                          starts_at__gte=timezone.now()).select_related("service").order_by("starts_at").first()
        shops.append({
            "shop": biz.name, "shop_code": biz.shop_code, "category": biz.category,
            "category_label": category["label"], "category_label_hi": category["hi"], "brand_color": biz.brand_color,
            "rating_average": round(float(rating["average"]), 1) if rating else None,
            "rating_count": rating["count"] if rating else 0,
            "logo_url": biz.logo.url if biz.logo else "", "live": biz.is_live,
            "bookings_enabled": biz.bookings_enabled, "referral_code": ensure_ref_code(p),
            "visits": st["visits"], "tier": st["tier"], "streak": st["streak"],
            "streak_this_week": st["streak_this_week"], "best": st["best"],
            "active_rewards": st["active_rewards"], "next_expiry": st["next_expiry"],
            "boosts_now": st["boosts_now"],
            "next_booking": {"id": upcoming.id, "service": upcoming.service.name, "starts_at": upcoming.starts_at,
                             "status": upcoming.status} if upcoming else None,
        })
        total_rewards += st["active_rewards"]
        total_visits += st["visits"]
    shops.sort(key=lambda s: (-s["active_rewards"], -(s["best"]["pct"] if s["best"] else 0)))
    return {"shops": shops, "total_rewards": total_rewards, "total_visits": total_visits}
