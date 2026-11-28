from django.utils import timezone
import re
from urllib.parse import urlparse
from rest_framework import serializers
from .models import (AuditLog, Booking, Boost, Business, Feedback, Program, PurchaseEntry, Reward, Service,
                     ShopOffer, ShopOfferItem, Task)


SOCIAL_URL_DOMAINS = {
    "instagram_url": ("instagram.com",),
    "facebook_url": ("facebook.com", "fb.com"),
    "youtube_url": ("youtube.com", "youtu.be"),
    "tiktok_url": ("tiktok.com",),
    "x_url": ("x.com", "twitter.com"),
}


class BusinessSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()

    def get_logo_url(self, o):
        return o.logo.url if o.logo else ""

    def validate_brand_color(self, v):
        if v and not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
            raise serializers.ValidationError("Use a hex colour like #5e35b1.")
        return v or "#5e35b1"

    def validate_logo(self, f):
        if f and f.size > 2 * 1024 * 1024:
            raise serializers.ValidationError("Logo must be 2 MB or smaller.")
        return f

    def validate(self, d):
        inst = self.instance
        lat = d.get("lat", inst.lat if inst else None)
        lng = d.get("lng", inst.lng if inst else None)
        if (lat is None) != (lng is None):
            raise serializers.ValidationError({"lat": "Provide both latitude and longitude for a shop location."})
        if lat is not None and not -90 <= lat <= 90:
            raise serializers.ValidationError({"lat": "Latitude must be between -90 and 90."})
        if lng is not None and not -180 <= lng <= 180:
            raise serializers.ValidationError({"lng": "Longitude must be between -180 and 180."})
        silver = d.get("tier_silver_visits", inst.tier_silver_visits if inst else 5)
        gold = d.get("tier_gold_visits", inst.tier_gold_visits if inst else 15)
        if silver and gold and gold <= silver:
            raise serializers.ValidationError("Gold must need more visits than Silver.")
        for k in ("phone", "whatsapp"):
            if d.get(k) and not re.fullmatch(r"\+?[0-9 ]{8,15}", d[k]):
                raise serializers.ValidationError({k: "Enter a valid phone number."})
        for field, domains in SOCIAL_URL_DOMAINS.items():
            url = d.get(field, getattr(inst, field, "") if inst else "")
            if not url:
                continue
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            if parsed.scheme != "https" or not any(host == domain or host.endswith("." + domain) for domain in domains):
                raise serializers.ValidationError({field: f"Use a valid HTTPS {field.removesuffix('_url')} profile URL."})
        return d

    class Meta:
        model = Business
        fields = ["name", "category", "tagline", "address", "lat", "lng", "hours", "language",
                  "pay_upi_id", "shop_code", "approval_mode", "cooldown_minutes", "daily_cap",
                  "require_bill_photo", "max_distance_m",
                  "brand_color", "logo", "logo_url", "about", "phone", "whatsapp", "maps_url",
                  "instagram_url", "facebook_url", "youtube_url", "tiktok_url", "x_url",
                  "tier_silver_visits", "tier_gold_visits", "silver_perk", "gold_perk", "bookings_enabled"]
        read_only_fields = ["shop_code"]
        extra_kwargs = {"logo": {"write_only": True, "required": False}}


class RewardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reward
        fields = ["id", "title", "type", "value", "expiry_days", "terms", "min_order_amount",
                  "product_restrictions", "item_name", "original_price", "offer_price"]


class ShopOfferItemSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    def get_image(self, obj):
        return obj.image.url if obj.image else ""

    class Meta:
        model = ShopOfferItem
        fields = ["id", "name", "price", "offer_price", "image"]


class ShopOfferSerializer(serializers.ModelSerializer):
    items = ShopOfferItemSerializer(many=True, read_only=True)
    expired = serializers.SerializerMethodField()

    def get_expired(self, obj):
        return bool(obj.ends_on and obj.ends_on < timezone.localdate())

    class Meta:
        model = ShopOffer
        fields = ["id", "offer_type", "value", "title", "ends_on", "expired", "active", "items"]


class TaskSerializer(serializers.ModelSerializer):
    rewards = RewardSerializer(many=True, read_only=True)

    class Meta:
        model = Task
        fields = ["id", "title", "type", "target", "item_name", "repeatable", "max_per_customer", "rewards"]


class ProgramSerializer(serializers.ModelSerializer):
    tasks = TaskSerializer(many=True, read_only=True)
    archived = serializers.SerializerMethodField()

    def get_archived(self, obj):
        return AuditLog.objects.filter(
            business_id=obj.business_id, action="program_archived", ref=str(obj.pk)
        ).exists()

    class Meta:
        model = Program
        fields = ["id", "title", "active", "start", "end", "archived", "tasks"]


class EntrySerializer(serializers.ModelSerializer):
    customer = serializers.CharField(source="profile.user.first_name", read_only=True)
    customer_image_url = serializers.SerializerMethodField()
    task_title = serializers.SerializerMethodField()
    task_type = serializers.SerializerMethodField()

    shop_code = serializers.CharField(source="profile.business.shop_code", read_only=True)
    bill_url = serializers.SerializerMethodField()

    def get_task_title(self, o):
        return o.task.title if o.task_id else "Coin purchase"

    def get_task_type(self, o):
        return o.task.type if o.task_id else "coin_only"

    def get_bill_url(self, o):
        return o.bill_photo.url if o.bill_photo else ""

    def get_customer_image_url(self, o):
        return o.profile.user.profile_image.url if o.profile.user.profile_image else ""

    class Meta:
        model = PurchaseEntry
        fields = ["id", "profile", "shop_code", "customer", "customer_image_url", "task", "task_title",
                  "task_type", "value", "status", "created_at", "reviewed_at", "far", "distance_m", "bill_url"]


class ProfileImageSerializer(serializers.Serializer):
    profile_image = serializers.ImageField()

    def validate_profile_image(self, image):
        if image.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("Profile photos must be 5 MB or smaller.")
        return image


class CoinPurchaseSubmitSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.01,
                                      max_value=99999999.99)
    bill_photo = serializers.ImageField()

    def validate_bill_photo(self, image):
        if image.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("Bill photos must be 5 MB or smaller.")
        return image


class BoostSerializer(serializers.ModelSerializer):
    def validate_multiplier(self, v):
        if v not in (2, 3, 4, 5):
            raise serializers.ValidationError("Choose 2x to 5x.")
        return v

    def validate_weekdays(self, v):
        parts = [x.strip() for x in v.split(",") if x.strip()]
        if any(not x.isdigit() or int(x) > 6 for x in parts):
            raise serializers.ValidationError("Weekdays are 0 (Mon) to 6 (Sun), comma separated.")
        return ",".join(sorted(set(parts)))

    def validate(self, d):
        st, en = d.get("start_time"), d.get("end_time")
        if bool(st) != bool(en):
            raise serializers.ValidationError("Set both a start and an end time, or neither.")
        if d.get("start") and d.get("end") and d["end"] < d["start"]:
            raise serializers.ValidationError("End date is before the start date.")
        return d

    class Meta:
        model = Boost
        fields = ["id", "title", "multiplier", "weekdays", "start_time", "end_time", "start", "end", "active"]


class ServiceSerializer(serializers.ModelSerializer):
    def validate_duration_min(self, v):
        if not 5 <= v <= 600:
            raise serializers.ValidationError("Duration must be 5 to 600 minutes.")
        return v

    def validate_price(self, v):
        if v < 0:
            raise serializers.ValidationError("Price cannot be negative.")
        return v

    class Meta:
        model = Service
        fields = ["id", "name", "price", "duration_min", "description", "active"]


class BookingSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source="service.name", read_only=True)
    price = serializers.DecimalField(source="service.price", max_digits=10, decimal_places=2, read_only=True)
    duration_min = serializers.IntegerField(source="service.duration_min", read_only=True)
    customer = serializers.SerializerMethodField()
    mobile = serializers.CharField(source="profile.user.username", read_only=True)
    shop = serializers.CharField(source="profile.business.name", read_only=True)
    shop_code = serializers.CharField(source="profile.business.shop_code", read_only=True)
    rated = serializers.SerializerMethodField()

    def get_customer(self, o):
        u = o.profile.user
        return u.first_name or "…" + u.username[-4:]

    def get_rated(self, o):
        return hasattr(o, "feedback")

    class Meta:
        model = Booking
        fields = ["id", "service", "service_name", "price", "duration_min", "starts_at", "status", "note",
                  "customer", "mobile", "shop", "shop_code", "rated", "created_at"]


class FeedbackSerializer(serializers.ModelSerializer):
    customer = serializers.SerializerMethodField()

    def get_customer(self, o):
        u = o.profile.user
        return u.first_name or "…" + u.username[-4:]

    class Meta:
        model = Feedback
        fields = ["id", "rating", "comment", "customer", "created_at"]
