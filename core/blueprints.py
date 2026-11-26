"""One-tap setup blueprints. A new owner picks a business type and gets a complete, sensible loyalty setup
(programs, rewards, a slow-day boost, tier perks, welcome + referral perks, and services for appointment
businesses) that they can edit afterwards. Amounts are INR. Everything here is only a starting point."""
from django.db import transaction

from .models import Boost, Program, Reward, Service, Task

# weekday numbers follow Python: Monday=0 ... Sunday=6
_WEEKDAYS = "0,1,2,3"


def _task(title, type_, target, reward, item="", repeatable=True):
    return {"title": title, "type": type_, "target": target, "item_name": item, "repeatable": repeatable,
            "rewards": [reward]}


def _r(title, type_="custom", value=0, days=30, terms=""):
    return {"title": title, "type": type_, "value": value, "expiry_days": days, "terms": terms}


BLUEPRINTS = {
    "cafe": {
        "label": "Cafe & coffee", "hi": "कैफ़े और कॉफ़ी", "emoji": "☕", "bookings": False,
        "program": "Coffee Club",
        "tasks": [_task("Buy 8 coffees", "count", 8, _r("Free coffee", "free_item", 0, 30), item="coffee"),
                  _task("Spend ₹2,000", "amount", 2000, _r("10% off your next bill", "percent_off", 10, 45))],
        "boosts": [{"title": "Slow-afternoon double stamps", "multiplier": 2, "weekdays": "1,2,3",
                    "start_time": "14:00", "end_time": "17:00"}],
        "welcome": _r("Free cookie with your first coffee", "gift", 0, 14),
        "referral": _r("Free coffee for bringing a friend", "free_item", 0, 30),
        "tiers": {"silver": 5, "gold": 15, "silver_perk": "Free size upgrade", "gold_perk": "Free coffee on your birthday week"},
    },
    "restaurant": {
        "label": "Restaurant & dining", "hi": "रेस्तराँ", "emoji": "🍽️", "bookings": False,
        "program": "Dine & Earn",
        "tasks": [_task("Visit 5 times", "visit", 5, _r("Free dessert", "free_item", 0, 30)),
                  _task("Spend ₹3,000", "amount", 3000, _r("15% off your next meal", "percent_off", 15, 45))],
        "boosts": [{"title": "Weekday double visits", "multiplier": 2, "weekdays": _WEEKDAYS}],
        "welcome": _r("Free mocktail with your first meal", "gift", 0, 14),
        "referral": _r("Free starter when a friend dines", "free_item", 0, 30),
        "tiers": {"silver": 5, "gold": 12, "silver_perk": "Priority seating", "gold_perk": "Free dessert every visit"},
    },
    "grocery": {
        "label": "Grocery & convenience", "hi": "किराना और सुविधा स्टोर", "emoji": "🛒", "bookings": False,
        "program": "Neighbour Rewards",
        "tasks": [_task("Spend ₹3,000", "amount", 3000, _r("₹150 off your next bill", "flat_off", 150, 30)),
                  _task("Visit 10 times", "visit", 10, _r("Free 1 kg staple (sugar or rice)", "gift", 0, 30))],
        "boosts": [{"title": "Midweek double visits", "multiplier": 2, "weekdays": "0,1,2"}],
        "welcome": _r("₹30 off your first bill", "flat_off", 30, 14),
        "referral": _r("₹50 off when a neighbour joins", "flat_off", 50, 30),
        "tiers": {"silver": 8, "gold": 25, "silver_perk": "Free home delivery on big orders", "gold_perk": "Monthly surprise gift"},
    },
    "retail": {
        "label": "Fashion & retail", "hi": "फ़ैशन और रिटेल", "emoji": "🛍️", "bookings": False,
        "program": "Style Circle",
        "tasks": [_task("Spend ₹10,000", "amount", 10000, _r("₹500 off your next purchase", "flat_off", 500, 60)),
                  _task("Visit 4 times", "visit", 4, _r("Free gift wrap + accessory", "gift", 0, 45))],
        "boosts": [{"title": "Midweek double visits", "multiplier": 2, "weekdays": "1,2"}],
        "welcome": _r("10% off your first purchase", "percent_off", 10, 14),
        "referral": _r("₹200 off when a friend shops", "flat_off", 200, 45),
        "tiers": {"silver": 4, "gold": 10, "silver_perk": "Early access to new arrivals", "gold_perk": "Free alterations"},
    },
    "salon": {
        "label": "Salon & wellness", "hi": "सैलून और वेलनेस", "emoji": "💇", "bookings": True,
        "program": "Glow Club",
        "tasks": [_task("Visit 5 times", "visit", 5, _r("20% off your next service", "percent_off", 20, 45)),
                  _task("Spend ₹5,000", "amount", 5000, _r("Free hair spa", "free_item", 0, 60))],
        "boosts": [{"title": "Midweek double visits", "multiplier": 2, "weekdays": "1,2"}],
        "services": [{"name": "Haircut", "price": 300, "duration_min": 30},
                     {"name": "Hair spa", "price": 800, "duration_min": 60},
                     {"name": "Facial", "price": 1200, "duration_min": 60},
                     {"name": "Beard trim", "price": 150, "duration_min": 15}],
        "welcome": _r("Free head massage with your first service", "gift", 0, 14),
        "referral": _r("₹150 off when a friend books", "flat_off", 150, 45),
        "tiers": {"silver": 4, "gold": 10, "silver_perk": "Priority booking slots", "gold_perk": "Free add-on every visit"},
    },
    "fitness": {
        "label": "Fitness & studios", "hi": "फ़िटनेस और स्टूडियो", "emoji": "🏋️", "bookings": True,
        "program": "Stay Consistent",
        "tasks": [_task("Attend 12 sessions", "visit", 12, _r("Free personal-training session", "free_item", 0, 60)),
                  _task("Spend ₹6,000", "amount", 6000, _r("₹500 off your next renewal", "flat_off", 500, 60))],
        "boosts": [{"title": "Off-peak double visits", "multiplier": 2, "weekdays": "0,1,2,3",
                    "start_time": "11:00", "end_time": "16:00"}],
        "services": [{"name": "Trial session", "price": 0, "duration_min": 45},
                     {"name": "Personal training", "price": 600, "duration_min": 60},
                     {"name": "Group class", "price": 250, "duration_min": 45}],
        "welcome": _r("Free guest pass for a friend", "gift", 0, 21),
        "referral": _r("Free week when a friend joins", "gift", 0, 45),
        "tiers": {"silver": 10, "gold": 30, "silver_perk": "Free towel service", "gold_perk": "Free guest pass every month"},
    },
    "services": {
        "label": "Repair, clinic & other services", "hi": "रिपेयर, क्लिनिक और सेवाएँ", "emoji": "🛠️", "bookings": True,
        "program": "Trusted Customer Rewards",
        "tasks": [_task("Every 4th service", "visit", 4, _r("Free check-up / inspection", "free_item", 0, 90)),
                  _task("Spend ₹10,000", "amount", 10000, _r("₹500 off your next service", "flat_off", 500, 90))],
        "boosts": [],
        "services": [{"name": "Standard service", "price": 1500, "duration_min": 60},
                     {"name": "Check-up / inspection", "price": 300, "duration_min": 30}],
        "welcome": _r("Free check-up with your first service", "free_item", 0, 30),
        "referral": _r("₹200 off when you refer a friend", "flat_off", 200, 60),
        "tiers": {"silver": 3, "gold": 8, "silver_perk": "Priority scheduling", "gold_perk": "Free pickup & drop"},
    },
    "other": {
        "label": "Other shop", "hi": "अन्य दुकान", "emoji": "🏪", "bookings": False,
        "program": "Loyalty Rewards",
        "tasks": [_task("Visit 5 times", "visit", 5, _r("Free gift", "gift", 0, 30)),
                  _task("Spend ₹2,000", "amount", 2000, _r("10% off", "percent_off", 10, 45))],
        "boosts": [],
        "welcome": _r("Welcome gift on your first purchase", "gift", 0, 14),
        "referral": _r("Reward for bringing a friend", "gift", 0, 30),
        "tiers": {"silver": 5, "gold": 15, "silver_perk": "", "gold_perk": ""},
    },
}

ADDITIONAL_CATEGORIES = {
    "agri_inputs": ("Seeds, fertilizer & pesticides", "बीज, उर्वरक और कीटनाशक", "🌱"),
    "medical_store": ("Medical store & pharmacy", "मेडिकल स्टोर और फ़ार्मेसी", "💊"),
    "books_stationery": ("Books & stationery", "किताबें और स्टेशनरी", "📚"),
    "electronics": ("Electronics & appliances", "इलेक्ट्रॉनिक्स और उपकरण", "🔌"),
    "hardware": ("Hardware & building supplies", "हार्डवेयर और निर्माण सामग्री", "🧰"),
    "automotive": ("Automotive & spare parts", "ऑटोमोबाइल और स्पेयर पार्ट्स", "🛞"),
    "pet_supplies": ("Pet supplies", "पालतू जानवरों की सामग्री", "🐾"),
    "bakery_sweets": ("Bakery & sweets", "बेकरी और मिठाइयाँ", "🍰"),
}

for key, (label, hi, emoji) in ADDITIONAL_CATEGORIES.items():
    blueprint = BLUEPRINTS["other"].copy()
    blueprint.update({
        "label": label,
        "hi": hi,
        "emoji": emoji,
        "program": f"{label} Rewards",
        "tasks": [
            _task("Spend ₹2,000", "amount", 2000, _r("₹100 off an eligible purchase", "flat_off", 100, 30)),
            _task("Visit 5 times", "visit", 5, _r("Shop-defined reward", "custom", 0, 30)),
        ],
        "welcome": _r("Welcome reward (shop-defined)", "custom", 0, 14),
        "referral": _r("Referral reward (shop-defined)", "custom", 0, 30),
    })
    BLUEPRINTS[key] = blueprint


def catalog():
    """Compact list for the picker UI."""
    return [{"key": k, "label": b["label"], "hi": b["hi"], "emoji": b["emoji"], "bookings": b["bookings"],
             "program": b["program"],
             "tasks": [{"title": t["title"], "reward": t["rewards"][0]["title"], "type": t["type"]} for t in b["tasks"]],
             "boosts": [x["title"] for x in b.get("boosts", [])],
             "services": [s["name"] for s in b.get("services", [])],
             "welcome": b["welcome"]["title"], "referral": b["referral"]["title"]}
            for k, b in BLUEPRINTS.items()]


@transaction.atomic
def apply(biz, key):
    """Create the blueprint for a business. Programs are always added; boosts, services, perks and tier perks
    are only filled in when the owner has not set them yet, so applying twice never duplicates them."""
    bp = BLUEPRINTS[key]
    program = Program.objects.create(business=biz, title=bp["program"])
    for t in bp["tasks"]:
        task = Task.objects.create(program=program, title=t["title"], type=t["type"], target=t["target"],
                                   item_name=t["item_name"], repeatable=t["repeatable"])
        for r in t["rewards"]:
            Reward.objects.create(task=task, **r)
    made = {"program": program.id, "boosts": 0, "services": 0, "perks": 0}
    if bp.get("boosts") and not biz.boosts.exists():
        for b in bp["boosts"]:
            Boost.objects.create(business=biz, **b)
            made["boosts"] += 1
    if bp.get("services") and not biz.services.exists():
        for s in bp["services"]:
            Service.objects.create(business=biz, **s)
            made["services"] += 1
    for trig in ("welcome", "referral"):
        if not biz.perk_rewards.filter(trigger=trig).exists():
            Reward.objects.create(business=biz, trigger=trig, **bp[trig])
            made["perks"] += 1
    tiers = bp["tiers"]
    if not biz.silver_perk and not biz.gold_perk:
        biz.tier_silver_visits, biz.tier_gold_visits = tiers["silver"], tiers["gold"]
        biz.silver_perk, biz.gold_perk = tiers["silver_perk"], tiers["gold_perk"]
    if bp["bookings"] and not biz.bookings_enabled:
        biz.bookings_enabled = True
    if biz.category in ("", "other") and key != "other":
        biz.category = key
    biz.save()
    return made
