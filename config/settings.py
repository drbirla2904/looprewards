import os
import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
env = os.environ.get
SECRET_KEY = env("SECRET_KEY", "dev-only-change-me")
DEBUG = env("DEBUG", "0") == "1"  # safe default: production. Local dev: DEBUG=1
_hosts = [host.strip() for host in env("ALLOWED_HOSTS", "*").split(",") if host.strip()]
ALLOWED_HOSTS = _hosts + ["localhost", "127.0.0.1"]
BASE_URL = env("BASE_URL", "http://localhost:8000")  # QR -> BASE_URL/b/<code>
CSRF_TRUSTED_ORIGINS = [o for o in env("CSRF_TRUSTED_ORIGINS", "").split(",") if o]
INSTALLED_APPS = ["django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "rest_framework", "rest_framework.authtoken", "core"]
if not DEBUG:
    if len(SECRET_KEY) < 50 or SECRET_KEY.startswith("dev-only"):
        raise RuntimeError("Set a random SECRET_KEY of at least 50 characters in .env")
    if not _hosts or "*" in _hosts:
        raise RuntimeError("Set ALLOWED_HOSTS to your domain in .env")
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware", "core.middleware.ApiNoStoreMiddleware"]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "APP_DIRS": True,
    "OPTIONS": {"context_processors": ["django.template.context_processors.request",
    "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages"]}}]
if env("POSTGRES_DB"):
    DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"), "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", "127.0.0.1"), "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": int(env("DB_CONN_MAX_AGE", "60")), "CONN_HEALTH_CHECKS": True}}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
AUTH_USER_MODEL = "core.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL, STATIC_ROOT = "static/", BASE_DIR / "staticfiles"
MEDIA_URL, MEDIA_ROOT = "media/", Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))
PRIVATE_MEDIA_ROOT = BASE_DIR / "private-media"
TIME_ZONE, USE_TZ = "Asia/Kolkata", True
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env("SECURE_SSL_REDIRECT", "1") == "1"
X_FRAME_OPTIONS = "DENY"
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.TokenAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": "60/min"},
}

# ---- Billing ----
TRIAL_DAYS, GRACE_DAYS = 14, 30
PLANS = {"monthly": {"amount": 9900, "days": 30, "label": "Monthly"},       # paise (₹99)
         "yearly": {"amount": 99900, "days": 365, "label": "Yearly"}}      # ₹999
RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_ID", ""), env("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET", "")
PLATFORM_UPI_ID, PLATFORM_UPI_NAME = env("PLATFORM_UPI_ID", ""), env("PLATFORM_UPI_NAME", "OFFLet")
GST_RATE = int(env("GST_RATE", "18"))  # plan prices are treated as GST-inclusive
SELLER = {"name": env("SELLER_NAME", "Your Company Name"), "gstin": env("SELLER_GSTIN", ""),
          "address": env("SELLER_ADDRESS", "")}
NOTIFY_WEBHOOK_URL = env("NOTIFY_WEBHOOK_URL", "")  # POST {"mobile","text"} -> your SMS/WhatsApp provider bridge
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env("EMAIL_USE_TLS", "1") == "1"
EMAIL_USE_SSL = env("EMAIL_USE_SSL", "0") == "1"
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "") or EMAIL_HOST_USER
EMAIL_TIMEOUT = int(env("EMAIL_TIMEOUT", "10"))
EMAIL_OTP_ENABLED = bool(DEFAULT_FROM_EMAIL) and (
    bool(EMAIL_HOST) or EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend"
)
# ---- Vendors ----
COMMISSION_HOLD_DAYS, MIN_PAYOUT_PAISE = 30, 50000  # ₹500
COMMISSION_FIRST_YEAR_ONLY = env("COMMISSION_FIRST_YEAR_ONLY", "0") == "1"
# Businesses (owners) can also refer other businesses and earn in a wallet. Default: an admin approves each application
# (PAN/UPI check). Set OWNER_REFERRAL_AUTO_APPROVE=1 to approve owners instantly.
OWNER_REFERRAL_AUTO_APPROVE = env("OWNER_REFERRAL_AUTO_APPROVE", "0") == "1"
# Partner tiers: (active paying shops referred, tier name, bonus percentage points added to the vendor's base rate).
# "Active" = the referred owner's subscription is currently paid up. Tune these to your margins.
VENDOR_TIERS = [(0, "Starter", 0), (5, "Silver", 2), (15, "Gold", 4), (40, "Platinum", 6)]
# TDS on commission payouts. Defaults are 0 (off) on purpose: set them with your accountant for the current law
# (rate in percent; threshold = yearly aggregate in paise per vendor above which TDS applies).
VENDOR_TDS_RATE = env("VENDOR_TDS_RATE", "0")
VENDOR_TDS_THRESHOLD_PAISE = int(env("VENDOR_TDS_THRESHOLD_PAISE", "0"))
NOTIFY_SMS = env("NOTIFY_SMS", "0") == "1"  # also send key customer alerts (reward unlocked/expiring) via NOTIFY_WEBHOOK_URL
# Razorpay Subscriptions (auto-renew): create plans in the dashboard, put their ids here
RZP_PLAN_IDS = {"monthly": env("RAZORPAY_PLAN_MONTHLY", ""), "yearly": env("RAZORPAY_PLAN_YEARLY", "")}

# ---- Production hardening / scale ----
REST_FRAMEWORK["NUM_PROXIES"] = int(env("NUM_PROXIES", "1"))  # Caddy = 1 (Cloudflare + Caddy = 2); needed for per-user-IP throttling
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = ["rest_framework.throttling.AnonRateThrottle", "rest_framework.throttling.UserRateThrottle"]
# high anon/user limits because many Indian mobile users share one carrier IP (CGNAT); login/OTP use the strict "auth" scope
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {"anon": "600/min", "user": "600/min",
                                            "auth": "10000/min" if "test" in sys.argv else "10/min",
                                            "donation": "5/min"}
if env("REDIS_URL"):  # shared across workers; without it throttling is per-process
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": env("REDIS_URL")}}
if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_CONTENT_TYPE_NOSNIFF = True
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
LOGGING = {"version": 1, "disable_existing_loggers": False,
           "handlers": {"console": {"class": "logging.StreamHandler"}},
           "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")}}
if env("SENTRY_DSN"):
    import sentry_sdk
    sentry_sdk.init(dsn=env("SENTRY_DSN"), traces_sample_rate=0.0, send_default_pii=False)

# ---- Legal pages / lifecycle ----
RETENTION_MONTHS = int(env("RETENTION_MONTHS", "12"))  # shop data kept this long after grace ends, then deleted (purge_lapsed)
_support = env("SUPPORT_EMAIL", "support@" + env("DOMAIN", "yourdomain.com"))
COMPANY = {"name": SELLER["name"], "address": SELLER["address"], "email": _support, "phone": env("SUPPORT_PHONE", ""),
           "grievance_name": env("GRIEVANCE_NAME", "Grievance Officer"), "grievance_email": env("GRIEVANCE_EMAIL", _support),
           "city": env("JURISDICTION", "Mumbai, Maharashtra"), "updated": env("LEGAL_UPDATED", "26 November 2026"),
           "hosting": env("HOSTING_REGION", "India / Europe (Contabo data centre)")}
