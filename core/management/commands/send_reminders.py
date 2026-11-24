from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import ReminderLog, RewardGrant, Subscription
from core.notify import notify, push


class Command(BaseCommand):
    help = "Trial-ending (2d), renewal (7d) and paused notices. Run daily."

    def handle(self, *a, **o):
        now, sent = timezone.now(), 0
        for s in Subscription.objects.select_related("owner"):
            end = s.paid_until or s.trial_ends
            st, left = s.state, end - now
            msg = None
            if st == "trial" and left <= timedelta(days=2):
                kind, msg = "trial_2d", "Your OFFLet free trial ends in 2 days. Subscribe to keep your QR and rewards live."
            elif st == "active" and left <= timedelta(days=7):
                if s.rzp_sub_id and s.rzp_autorenew_active:  # AutoPay owners should not be told to renew by hand
                    kind, msg = "autorenew_7d", f"Your OFFLet plan renews automatically on {end:%d %b %Y}. Nothing to do."
                else:
                    kind, msg = "renew_7d", f"Your OFFLet plan expires on {end:%d %b %Y}. Renew from Billing to avoid a pause."
            elif st == "grace":
                d = (now - end).days
                kind = "grace_25" if d >= 25 else "grace_7" if d >= 7 else "paused"
                msg = "Your OFFLet plan expired and your shop page is paused. Renew to restore it instantly; your customers' progress is safe."
            elif st == "expired":
                gone = end + timedelta(days=settings.GRACE_DAYS + 30 * settings.RETENTION_MONTHS)
                out = (now - end).days - settings.GRACE_DAYS
                back = f"We miss you! Your shop data is safe until {gone:%d %b %Y}. Renew any time to restore your QR, customers and rewards."
                if gone - now <= timedelta(days=30):
                    kind, msg = "purge_30d", f"Final notice: your OFFLet shop data will be deleted on {gone:%d %b %Y}. Renew before then to keep it."
                elif out >= 150:
                    kind, msg = "winback_150", back
                elif out >= 60:
                    kind, msg = "winback_60", back
            if msg and ReminderLog.objects.get_or_create(owner=s.owner, kind=kind, key=end.strftime("%Y%m%d"))[1]:
                notify(s.owner, msg)
                sent += 1
        soon = RewardGrant.objects.filter(status="active", expires_at__gt=now, expires_at__lte=now + timedelta(days=3))
        for g in soon.select_related("reward", "profile__user", "profile__business"):
            u = g.profile.user
            if ReminderLog.objects.get_or_create(owner=u, kind="reward_exp", key=g.code)[1]:
                push(u, f"Your reward '{g.reward.title}' at {g.profile.business.name} expires on {g.expires_at:%d %b}. Code {g.code}", sms=True)
                sent += 1
        sent += self.streak_nudges(now, force=o.get("force_streaks"))
        self.stdout.write(f"{sent} reminders sent")

    def add_arguments(self, parser):
        parser.add_argument("--force-streaks", action="store_true", help="send streak nudges even if today is not Saturday")

    def streak_nudges(self, now, force=False):
        """Saturday: customers with a 2+ week streak who have not visited this week get a friendly nudge, once per week."""
        today = timezone.localdate()
        if today.weekday() != 5 and not force:
            return 0
        from core import engage
        from core.models import CustomerProfile
        recent = CustomerProfile.objects.filter(status="active", hidden_from_customer=False,
            entries__status="approved", entries__created_at__gte=now - timedelta(days=21)).select_related("user", "business").distinct()
        n = 0
        for p in recent:
            if not p.business.is_live:
                continue
            streak, this_week = engage.streak_weeks(engage.visit_days(p), today)
            if streak >= 2 and not this_week:
                key = f"{today.isocalendar()[0]}W{today.isocalendar()[1]}"
                if ReminderLog.objects.get_or_create(owner=p.user, kind=f"streak{p.business_id}", key=key)[1]:
                    push(p.user, f"Streak alert: {streak} weeks in a row at {p.business.name}. Visit by Sunday to keep it going.")
                    n += 1
        return n
