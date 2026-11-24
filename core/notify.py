import json, logging, threading, urllib.request
from django.conf import settings
log = logging.getLogger("notify")


def _post(url, payload):
    req = urllib.request.Request(url, method="POST", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        log.exception("notify failed")


def notify(user, text, sensitive=False):
    """SMS/WhatsApp via your provider bridge (NOTIFY_WEBHOOK_URL). Fire-and-forget thread so requests never wait.
    At very large scale replace with a queue (Celery/RQ) so messages survive restarts."""
    if sensitive:
        log.info("Sensitive notification queued")
    else:
        log.info("NOTIFY %s: %s", user.username, text)
    if settings.NOTIFY_WEBHOOK_URL:
        threading.Thread(target=_post, args=(settings.NOTIFY_WEBHOOK_URL, {"mobile": user.username, "text": text}),
                         daemon=True).start()


def safe_link(link):
    """Only in-app paths are allowed (no scheme, no //host), so a notification can never send someone off-site."""
    link = (link or "").strip()
    return link[:200] if link.startswith("/") and not link.startswith("//") and "\\" not in link and ":" not in link.split("#")[0] else ""


def push(user, text, sms=False, link=""):
    """In-app notification (always); SMS/WhatsApp only for key alerts when NOTIFY_SMS=1.
    link: where tapping it goes, e.g. /b/CODE/?tab=rewards (customers) or /app/#/billing (owners)."""
    from .models import Notification
    Notification.objects.create(user=user, text=text[:240], link=safe_link(link))
    if sms and settings.NOTIFY_SMS:
        notify(user, text)


def announce_shop_customers(business, text, link="", audience="all"):
    """Create an in-app promotion notice for active shop members who opted in to marketing."""
    from django.db.models import Exists, OuterRef
    from .models import CustomerProfile, PurchaseEntry

    if audience not in ("all", "new", "returning"):
        raise ValueError("Unsupported shop announcement audience.")
    profiles = CustomerProfile.objects.filter(
        business=business,
        status="active",
        hidden_from_customer=False,
        marketing_consent=True,
    )
    if audience != "all":
        purchases = PurchaseEntry.objects.filter(profile_id=OuterRef("pk"), status="approved")
        profiles = profiles.annotate(has_purchased=Exists(purchases)).filter(
            has_purchased=(audience == "returning")
        )
    recipients = list(profiles.select_related("user"))
    for profile in recipients:
        push(profile.user, text, link=link)
    return len(recipients)
