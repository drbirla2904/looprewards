import secrets, string
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from .private_storage import PrivateMediaStorage


def new_shop_code():
    return "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))


def new_reward_code():
    return secrets.token_hex(4).upper()


def _bill_path(instance, filename):  # unguessable file names
    import os, uuid
    return f"bills/{uuid.uuid4().hex}{os.path.splitext(filename)[1][:6]}"


def _profile_image_path(instance, filename):
    import os, uuid
    return f"profiles/{uuid.uuid4().hex}{os.path.splitext(filename)[1][:6]}"


def _payment_proof_path(instance, filename):
    import os, uuid
    return f"payment-proofs/{uuid.uuid4().hex}{os.path.splitext(filename)[1].lower()}"


def _offer_image_path(instance, filename):
    import os, uuid
    return f"offers/{uuid.uuid4().hex}{os.path.splitext(filename)[1].lower()}"


class User(AbstractUser):  # username == mobile number
    ROLES = [("owner", "owner"), ("staff", "staff"), ("customer", "customer"), ("vendor", "vendor")]
    role = models.CharField(max_length=10, choices=ROLES, default="customer")
    profile_image = models.ImageField(upload_to=_profile_image_path, blank=True)
    email_verified = models.BooleanField(default=False)


class Business(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="businesses")
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=30, default="other")
    tagline = models.CharField(max_length=160, blank=True)
    address = models.TextField(blank=True)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    hours = models.CharField(max_length=120, blank=True)
    language = models.CharField(max_length=5, default="en")
    pay_upi_id = models.CharField(max_length=80, blank=True)
    pay_qr_image = models.ImageField(upload_to="payqr/", blank=True)
    shop_code = models.CharField(max_length=12, unique=True, default=new_shop_code)  # regenerate = revoke QR
    status = models.CharField(max_length=12, default="active")  # active / paused (subscription gate)
    approval_mode = models.CharField(max_length=10, default="manual", choices=[("manual", "manual"), ("auto", "auto")])
    cooldown_minutes = models.PositiveIntegerField(default=10)
    daily_cap = models.PositiveIntegerField(default=3)
    # --- v2: branding (public shop page) ---
    brand_color = models.CharField(max_length=7, default="#5e35b1", blank=True)
    logo = models.ImageField(upload_to="logos/", blank=True)
    about = models.TextField(blank=True, max_length=600)
    phone = models.CharField(max_length=20, blank=True)
    whatsapp = models.CharField(max_length=20, blank=True)
    maps_url = models.URLField(blank=True)
    instagram_url = models.URLField(max_length=300, blank=True)
    facebook_url = models.URLField(max_length=300, blank=True)
    youtube_url = models.URLField(max_length=300, blank=True)
    tiktok_url = models.URLField(max_length=300, blank=True)
    x_url = models.URLField(max_length=300, blank=True)
    # --- v2: membership tiers (lifetime approved visits) ---
    tier_silver_visits = models.PositiveIntegerField(default=5)
    tier_gold_visits = models.PositiveIntegerField(default=15)
    silver_perk = models.CharField(max_length=120, blank=True)
    gold_perk = models.CharField(max_length=120, blank=True)
    # --- v2: appointments for service businesses ---
    bookings_enabled = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class ShopOffer(models.Model):
    TYPES = [("percent_off", "Percentage off"), ("fixed_price", "Fixed price"), ("bogo", "Buy one get one")]
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="offers")
    offer_type = models.CharField(max_length=15, choices=TYPES)
    value = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    title = models.CharField(max_length=80, blank=True)  # v2.5: optional headline, e.g. "Weekend special"
    ends_on = models.DateField(null=True, blank=True)    # v2.5: last day the offer is shown (inclusive)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")


class ShopOfferItem(models.Model):
    offer = models.ForeignKey(ShopOffer, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=120)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    offer_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    image = models.ImageField(upload_to=_offer_image_path, blank=True)

    class Meta:
        ordering = ("id",)


class Program(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="programs")
    title = models.CharField(max_length=120)
    active = models.BooleanField(default=True)
    start = models.DateField(null=True, blank=True)
    end = models.DateField(null=True, blank=True)


class Task(models.Model):
    TYPES = [("count", "count"), ("amount", "amount"), ("visit", "visit")]
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=120)
    type = models.CharField(max_length=10, choices=TYPES)
    target = models.DecimalField(max_digits=10, decimal_places=2)
    item_name = models.CharField(max_length=80, blank=True)
    repeatable = models.BooleanField(default=True)
    max_per_customer = models.PositiveIntegerField(default=0)  # 0 = unlimited when repeatable
    version = models.PositiveIntegerField(default=1)


class Reward(models.Model):
    TYPES = [("free_item", "free_item"), ("percent_off", "percent_off"), ("flat_off", "flat_off"),
             ("gift", "gift"), ("cashback", "cashback"), ("special_offer", "special_offer"), ("custom", "custom")]
    TRIGGERS = [("task", "task"), ("welcome", "welcome"), ("referral", "referral"), ("retired", "retired"),
                ("winback", "winback"), ("spin", "spin"), ("social", "social")]
    task = models.ForeignKey(Task, null=True, blank=True, on_delete=models.CASCADE, related_name="rewards")
    title = models.CharField(max_length=120)
    type = models.CharField(max_length=15, choices=TYPES)
    value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    expiry_days = models.PositiveIntegerField(default=30)
    terms = models.TextField(blank=True)
    # v2: "welcome" (first approved purchase) and "referral" (friend's first purchase) rewards have no task
    trigger = models.CharField(max_length=10, choices=TRIGGERS, default="task")
    business = models.ForeignKey(Business, null=True, blank=True, on_delete=models.CASCADE, related_name="perk_rewards")
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    product_restrictions = models.CharField(max_length=200, blank=True)
    item_name = models.CharField(max_length=120, blank=True)
    original_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    offer_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    image = models.ImageField(upload_to=_offer_image_path, blank=True)


class CustomerProfile(models.Model):  # one global login, separate profile per business
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="profiles")
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="customers")
    status = models.CharField(max_length=10, default="active")  # active / blocked
    joined_at = models.DateTimeField(auto_now_add=True)
    hidden_from_customer = models.BooleanField(default=False)
    history_hidden_before = models.DateTimeField(null=True, blank=True)
    referral_code = models.CharField(max_length=8, blank=True, db_index=True)  # generated lazily (see engage.ensure_ref_code)
    referred_by = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="referred")
    note = models.CharField(max_length=300, blank=True)  # private owner note, never shown to the customer

    class Meta:
        unique_together = ("user", "business")


class PurchaseEntry(models.Model):
    profile = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="entries")
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    value = models.DecimalField(max_digits=10, decimal_places=2, default=1)  # qty or amount
    status = models.CharField(max_length=10, default="pending")  # pending/approved/rejected/reversed
    bill_photo = models.ImageField(upload_to=_bill_path, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    credited_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)  # value x boost, set on approval
    multiplier = models.PositiveSmallIntegerField(default=1)


class TaskProgress(models.Model):
    profile = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="progress")
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    current_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    completed_count = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("profile", "task")


class RewardGrant(models.Model):
    profile = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="grants")
    reward = models.ForeignKey(Reward, on_delete=models.CASCADE)
    code = models.CharField(max_length=12, unique=True, default=new_reward_code)
    status = models.CharField(max_length=10, default="active")  # active/used/expired
    issued_at = models.DateTimeField(auto_now_add=True)
    redeemed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()


class RewardRedemptionRequest(models.Model):
    STATUSES = [("pending", "Pending"), ("approved", "Approved"), ("declined", "Declined"), ("cancelled", "Cancelled")]
    grant = models.ForeignKey(RewardGrant, on_delete=models.CASCADE, related_name="redemption_requests")
    status = models.CharField(max_length=10, choices=STATUSES, default="pending")
    requested_at = models.DateTimeField(default=timezone.now)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="reviewed_reward_redemption_requests")

    class Meta:
        ordering = ("-requested_at", "-id")
        constraints = [
            models.UniqueConstraint(fields=("grant",), condition=models.Q(status="pending"),
                                    name="one_pending_redemption_per_grant"),
        ]


class CoinProgram(models.Model):
    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name="coin_program")
    enabled = models.BooleanField(default=False)
    spend_per_coin = models.PositiveIntegerField(default=10)
    daily_cap = models.PositiveIntegerField(default=1000)
    # v2.5 growth bonuses (0 = off): coins for joining, per approved visit/count entry, and for refer-and-earn
    welcome_bonus = models.PositiveIntegerField(default=0)
    visit_coins = models.PositiveIntegerField(default=0)
    referrer_bonus = models.PositiveIntegerField(default=0)
    friend_bonus = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class CoinReward(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="coin_rewards")
    title = models.CharField(max_length=120)
    description = models.CharField(max_length=240, blank=True)
    cost = models.PositiveIntegerField()
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("cost", "id")


class CoinAccount(models.Model):
    profile = models.OneToOneField(CustomerProfile, on_delete=models.CASCADE, related_name="coin_account")
    balance = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class CoinRedemption(models.Model):
    STATUSES = [("pending", "Pending"), ("approved", "Approved"), ("declined", "Declined")]
    profile = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="coin_redemptions")
    reward = models.ForeignKey(CoinReward, on_delete=models.PROTECT, related_name="redemptions")
    coins_cost = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=STATUSES, default="pending")
    requested_at = models.DateTimeField(default=timezone.now)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="reviewed_coin_redemptions")

    class Meta:
        ordering = ("requested_at", "id")


class CoinTransaction(models.Model):
    KINDS = [("purchase", "Purchase"), ("redemption", "Redemption"), ("refund", "Refund"), ("reversal", "Purchase reversal"),
             ("bonus", "Bonus")]
    account = models.ForeignKey(CoinAccount, on_delete=models.CASCADE, related_name="transactions")
    delta = models.BigIntegerField()
    kind = models.CharField(max_length=12, choices=KINDS)
    reason = models.CharField(max_length=20, blank=True)  # for bonus rows: welcome / referrer / friend
    purchase_entry = models.OneToOneField(PurchaseEntry, null=True, blank=True, on_delete=models.CASCADE,
                                          related_name="coin_transaction")
    redemption = models.ForeignKey(CoinRedemption, null=True, blank=True, on_delete=models.CASCADE,
                                   related_name="transactions")
    reversal_of = models.OneToOneField("self", null=True, blank=True, on_delete=models.CASCADE,
                                       related_name="reversal")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(fields=("redemption", "kind"), condition=models.Q(redemption__isnull=False),
                                    name="one_coin_txn_kind_per_redemption"),
        ]


class ScratchCampaign(models.Model):
    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name="scratch_campaign")
    active = models.BooleanField(default=False)
    prize_title = models.CharField(max_length=120, blank=True)
    prize_type = models.CharField(max_length=15, choices=Reward.TYPES, default="free_item")
    prize_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    prize_terms = models.CharField(max_length=500, blank=True)
    expiry_days = models.PositiveSmallIntegerField(default=30)
    cards_per_deck = models.PositiveSmallIntegerField(default=10)
    winning_cards = models.PositiveSmallIntegerField(default=1)
    deck_number = models.PositiveIntegerField(default=1)
    cards_issued = models.PositiveSmallIntegerField(default=0)
    wins_issued = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class ScratchTicket(models.Model):
    profile = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="scratch_tickets")
    campaign = models.ForeignKey(ScratchCampaign, on_delete=models.CASCADE, related_name="tickets")
    purchase_entry = models.OneToOneField(PurchaseEntry, on_delete=models.CASCADE, related_name="scratch_ticket")
    deck_number = models.PositiveIntegerField()
    valid = models.BooleanField(default=True)
    is_winner = models.BooleanField(default=False)
    prize_title = models.CharField(max_length=120, blank=True)
    prize_type = models.CharField(max_length=15, choices=Reward.TYPES, blank=True)
    prize_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    prize_terms = models.CharField(max_length=500, blank=True)
    expiry_days = models.PositiveSmallIntegerField(default=30)
    issued_at = models.DateTimeField(auto_now_add=True)
    revealed_at = models.DateTimeField(null=True, blank=True)
    reward_grant = models.OneToOneField(RewardGrant, null=True, blank=True, on_delete=models.SET_NULL,
                                        related_name="scratch_ticket")

    class Meta:
        ordering = ("-issued_at", "-id")


class SocialFollowClaim(models.Model):
    profile = models.OneToOneField(CustomerProfile, on_delete=models.CASCADE, related_name="social_follow_claim")
    status = models.CharField(max_length=10, default="pending", choices=[
        ("pending", "pending"), ("approved", "approved"), ("rejected", "rejected"),
    ])
    requested_at = models.DateTimeField(default=timezone.now)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="reviewed_social_follow_claims")
    reward_grant = models.OneToOneField(RewardGrant, null=True, blank=True, on_delete=models.SET_NULL,
                                        related_name="social_follow_claim")


class AuditLog(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    actor = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=40)
    ref = models.CharField(max_length=60, blank=True)
    at = models.DateTimeField(auto_now_add=True)


from datetime import timedelta
from django.conf import settings
class Subscription(models.Model):
    owner = models.OneToOneField(User, on_delete=models.CASCADE, related_name="subscription")
    trial_ends = models.DateTimeField()
    paid_until = models.DateTimeField(null=True, blank=True)

    @property
    def state(self):
        now = timezone.now()
        end = self.paid_until or self.trial_ends
        if now <= end:
            return "active" if self.paid_until else "trial"
        return "grace" if now <= end + timedelta(days=settings.GRACE_DAYS) else "expired"


class BusinessReferralSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    enabled = models.BooleanField(
        default=True,
        help_text="Allow business owners to earn referral commissions. Owners also need an active yearly plan.",
    )
    updated_at = models.DateTimeField(auto_now=True)


class GatewayPlan(models.Model):
    """A Razorpay plan OFFLet created itself, so AutoPay works with only the API keys (no copying plan IDs by hand).
    A new row replaces the old one if the price in settings changes."""
    plan = models.CharField(max_length=10, unique=True)
    rzp_plan_id = models.CharField(max_length=60)
    amount = models.PositiveIntegerField()  # paise, the price this plan was created with
    created_at = models.DateTimeField(auto_now_add=True)


class Payment(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="payments")
    plan = models.CharField(max_length=10)
    amount = models.PositiveIntegerField()  # paise
    method = models.CharField(max_length=10)  # gateway / upi
    status = models.CharField(max_length=10, default="created")  # created/pending/paid/rejected
    order_id = models.CharField(max_length=60, blank=True, db_index=True)
    payment_id = models.CharField(max_length=60, blank=True)
    utr = models.CharField(max_length=20, blank=True, db_index=True)
    proof = models.ImageField(upload_to=_payment_proof_path, blank=True, storage=PrivateMediaStorage())
    created_at = models.DateTimeField(auto_now_add=True)


class Donation(models.Model):
    donor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="donations")
    amount = models.PositiveIntegerField()  # paise
    status = models.CharField(max_length=10, default="created", choices=[("created", "created"), ("paid", "paid")])
    order_id = models.CharField(max_length=60, unique=True)
    payment_id = models.CharField(max_length=60, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)


def get_sub(owner):
    return Subscription.objects.get_or_create(
        owner=owner, defaults={"trial_ends": timezone.now() + timedelta(days=settings.TRIAL_DAYS)})[0]


def _sub_state(self):
    return get_sub(self.owner).state


def _is_live(self):  # public profile + earning allowed only in trial/active
    return self.status == "active" and self.sub_state in ("trial", "active")


Business.sub_state = property(_sub_state)
Business.is_live = property(_is_live)


class ReminderLog(models.Model):  # dedupe: one reminder per owner/kind/period
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    kind = models.CharField(max_length=20)
    key = models.CharField(max_length=20)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("owner", "kind", "key")


Payment.add_to_class("invoice_no", models.CharField(max_length=24, blank=True))


class Vendor(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="vendor")
    code = models.CharField(max_length=10, unique=True)
    applied_at = models.DateTimeField(default=timezone.now)
    rate = models.DecimalField(max_digits=5, decimal_places=2, default=20)  # % of ex-GST subscription, set by admin
    pan = models.CharField(max_length=10)
    upi_id = models.CharField(max_length=80)
    status = models.CharField(max_length=10, default="pending")  # pending/approved/suspended

    def __str__(self):
        return f"{self.code} ({self.user.username})"


class Payout(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="payouts")
    amount = models.PositiveIntegerField()  # paise, before TDS
    status = models.CharField(max_length=10, default="pending")  # pending/paid
    reference = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    tds = models.PositiveIntegerField(default=0)  # paise withheld when marked paid; vendor receives amount - tds


class Commission(models.Model):
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="commissions")
    rate = models.DecimalField(max_digits=5, decimal_places=2)
    amount = models.PositiveIntegerField()  # paise
    status = models.CharField(max_length=10, default="hold")  # hold/payable/paid/reversed
    payable_on = models.DateTimeField()
    payout = models.ForeignKey(Payout, null=True, blank=True, on_delete=models.SET_NULL)


# permanent attribution, set once at registration
User.add_to_class("referred_by", models.ForeignKey(Vendor, null=True, blank=True, on_delete=models.SET_NULL,
                                                   related_name="referrals"))


class StaffMember(models.Model):  # staff: approve + redeem only
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="staff_of")
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="staff")


class CodeUse(models.Model):  # a counter code works once per customer, and only N times per step
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    step = models.BigIntegerField()
    profile = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("business", "step", "profile")


def can_manage(user, biz):
    return user.id == biz.owner_id or StaffMember.objects.filter(user=user, business=biz).exists()


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    text = models.CharField(max_length=240)
    link = models.CharField(max_length=200, blank=True)  # in-app path opened when the notification is tapped
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


Business.add_to_class("require_bill_photo", models.BooleanField(default=False))
Business.add_to_class("max_distance_m", models.PositiveIntegerField(default=300))
CustomerProfile.add_to_class("marketing_consent", models.BooleanField(default=False))
PurchaseEntry.add_to_class("far", models.BooleanField(default=False))
PurchaseEntry.add_to_class("distance_m", models.IntegerField(null=True, blank=True))
TaskProgress.add_to_class("target", models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True))  # snapshot
Subscription.add_to_class("rzp_sub_id", models.CharField(max_length=40, blank=True))
Subscription.add_to_class("rzp_autorenew_active", models.BooleanField(default=False))


class OtpCode(models.Model):
    PURPOSES = [("password_reset", "Password reset"), ("email_verify", "Recovery email verification")]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    code_hash = models.CharField(max_length=64)
    purpose = models.CharField(max_length=20, choices=PURPOSES, default="password_reset")
    target_email = models.EmailField(blank=True)
    expires = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


User.add_to_class("consent_at", models.DateTimeField(null=True, blank=True))  # when Terms/Privacy were accepted


# ===================== v2: engagement layer =====================
class Boost(models.Model):
    """Multiplier events ("double stamps on Tuesdays", "happy hour 3-6pm"). Applies to count/visit tasks."""
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="boosts")
    title = models.CharField(max_length=80)
    multiplier = models.PositiveSmallIntegerField(default=2)
    weekdays = models.CharField(max_length=13, blank=True)  # "0,1" = Mon,Tue; blank = every day
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    start = models.DateField(null=True, blank=True)
    end = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)


class Service(models.Model):  # bookable service (haircut, oil change, 1:1 class ...)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="services")
    name = models.CharField(max_length=80)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    duration_min = models.PositiveIntegerField(default=30)
    description = models.CharField(max_length=200, blank=True)
    active = models.BooleanField(default=True)


class Booking(models.Model):
    STATUSES = [("requested", "requested"), ("confirmed", "confirmed"), ("completed", "completed"),
                ("cancelled", "cancelled"), ("declined", "declined"), ("no_show", "no_show")]
    profile = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="bookings")
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="bookings")
    starts_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=STATUSES, default="requested")
    note = models.CharField(max_length=200, blank=True)
    credited = models.BooleanField(default=False)  # visit credited to the reward programs on completion
    created_at = models.DateTimeField(auto_now_add=True)


class Feedback(models.Model):
    profile = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="feedback")
    entry = models.OneToOneField(PurchaseEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name="feedback")
    booking = models.OneToOneField(Booking, null=True, blank=True, on_delete=models.SET_NULL, related_name="feedback")
    rating = models.PositiveSmallIntegerField()  # 1..5
    comment = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class SpinWheel(models.Model):
    AUDIENCES = [("all", "All customers"), ("new", "New customers"), ("returning", "Returning customers")]
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="spin_wheels")
    name = models.CharField(max_length=100)
    audience = models.CharField(max_length=10, choices=AUDIENCES, default="all")
    weekdays = models.CharField(max_length=13, blank=True)  # comma-separated Monday=0 ... Sunday=6; blank = every day
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    spins_per_day = models.PositiveSmallIntegerField(default=1)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-id")


class SpinSegment(models.Model):
    REWARD_TYPES = [("percent_off", "Percentage discount"), ("flat_off", "Fixed discount"),
                    ("free_item", "Free item"), ("gift", "Gift"), ("cashback", "Cashback"),
                    ("special_offer", "Special offer"), ("empty", "Try again")]
    wheel = models.ForeignKey(SpinWheel, on_delete=models.CASCADE, related_name="segments")
    position = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=80)
    reward_type = models.CharField(max_length=15, choices=REWARD_TYPES)
    probability = models.PositiveSmallIntegerField()  # percent; all active segments must total 100
    color = models.CharField(max_length=7, default="#5e35b1")
    icon = models.CharField(max_length=16, default="🎁")
    image_url = models.URLField(max_length=500, blank=True)
    value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    expiry_days = models.PositiveSmallIntegerField(default=30)
    minimum_order = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    product_restrictions = models.CharField(max_length=200, blank=True)
    terms = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(fields=("wheel", "position"), name="unique_spin_segment_position"),
        ]


class SpinRecord(models.Model):
    profile = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="spins")
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="spin_records")
    wheel = models.ForeignKey(SpinWheel, on_delete=models.SET_NULL, null=True, related_name="spins")
    segment = models.ForeignKey(SpinSegment, on_delete=models.SET_NULL, null=True, related_name="spins")
    grant = models.OneToOneField(RewardGrant, on_delete=models.SET_NULL, null=True, blank=True, related_name="spin_record")
    spin_date = models.DateField()
    sequence = models.PositiveSmallIntegerField(default=1)
    outcome = models.CharField(max_length=10, choices=[("won", "Won"), ("try_again", "Try again")])
    prize_title = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(fields=("profile", "business", "spin_date", "sequence"),
                                    name="unique_customer_daily_spin_sequence"),
        ]
