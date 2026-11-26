"""One-tap setup blueprints. A new owner picks a business type and gets a complete, sensible loyalty setup
(programs, rewards, a slow-day boost, tier perks, welcome + referral perks, and services for appointment
businesses) that they can edit afterwards. Amounts are INR. Everything here is only a starting point."""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from rest_framework.exceptions import ValidationError

from .models import Boost, Program, Reward, Service, Task
from .serializers import BoostSerializer

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
    """Return picker summaries and editable starter data for business registration."""
    return [{"key": k, "label": b["label"], "hi": b["hi"], "emoji": b["emoji"], "bookings": b["bookings"],
             "program": b["program"],
             "tasks": [{"title": t["title"], "reward": t["rewards"][0]["title"], "type": t["type"]} for t in b["tasks"]],
             "boosts": [x["title"] for x in b.get("boosts", [])],
             "services": [s["name"] for s in b.get("services", [])],
             "welcome": b["welcome"]["title"], "referral": b["referral"]["title"],
             "setup": {
                 "program": b["program"],
                 "tasks": [{"title": t["title"], "type": t["type"], "target": t["target"],
                            "item_name": t["item_name"], "repeatable": t["repeatable"],
                            "rewards": [dict(r) for r in t["rewards"]]} for t in b["tasks"]],
                 "boosts": [dict(x) for x in b.get("boosts", [])],
                 "welcome": dict(b["welcome"]),
                 "referral": dict(b["referral"]),
             }}
            for k, b in BLUEPRINTS.items()]


def _setup_text(value, label, max_length, required=True):
    value = str(value if value is not None else "").strip()
    if (required and not value) or len(value) > max_length:
        raise ValidationError(f"{label} is required and must be at most {max_length} characters.")
    return value


def _setup_number(value, label, minimum, maximum):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValidationError(f"{label} must be a number.")
    if not number.is_finite() or number < minimum or number > maximum:
        raise ValidationError(f"{label} must be between {minimum} and {maximum}.")
    return number


def _setup_reward(data):
    if not isinstance(data, dict):
        raise ValidationError("Reward details must be an object.")
    title = _setup_text(data.get("title"), "Reward name", 120)
    reward_type = data.get("type")
    if reward_type not in dict(Reward.TYPES):
        raise ValidationError("Choose a valid reward type.")
    value = _setup_number(data.get("value", 0), "Reward value", 0, 1_000_000)
    if reward_type == "percent_off" and value > 100:
        raise ValidationError("A percentage cannot be more than 100.")
    try:
        expiry_value = Decimal(str(data.get("expiry_days", 30)))
        expiry_days = int(expiry_value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError("Reward validity must be a whole number of days.")
    if not expiry_value.is_finite() or expiry_value != expiry_days or not 1 <= expiry_days <= 365:
        raise ValidationError("Reward validity must be between 1 and 365 days.")
    terms = _setup_text(data.get("terms", ""), "Reward terms", 500, required=False)
    return {"title": title, "type": reward_type, "value": value,
            "expiry_days": expiry_days, "terms": terms}


def _setup_config(key, setup):
    bp = BLUEPRINTS[key]
    if setup is None:
        setup = {}
    if not isinstance(setup, dict):
        raise ValidationError("Business setup must be an object.")
    allowed = {"program", "tasks", "boosts", "welcome", "referral"}
    if set(setup) - allowed:
        raise ValidationError("Business setup contains unsupported fields.")

    program = _setup_text(setup.get("program", bp["program"]), "Program name", 120)
    tasks = setup.get("tasks", bp["tasks"])
    if not isinstance(tasks, list) or len(tasks) > 20:
        raise ValidationError("Add no more than 20 starter rewards.")
    clean_tasks = []
    for data in tasks:
        if not isinstance(data, dict):
            raise ValidationError("Each starter reward must be an object.")
        task_type = data.get("type")
        if task_type not in dict(Task.TYPES):
            raise ValidationError("Choose a valid way to earn each reward.")
        rewards = data.get("rewards", [])
        if not isinstance(rewards, list) or not 1 <= len(rewards) <= 5:
            raise ValidationError("Each task can have up to 5 rewards.")
        repeatable = data.get("repeatable", True)
        if not isinstance(repeatable, bool):
            raise ValidationError("Repeatable must be true or false.")
        limit = _setup_number(data.get("max_per_customer", 0), "Customer limit", 0, 1000)
        if limit != limit.to_integral_value():
            raise ValidationError("Customer limit must be a whole number.")
        clean_tasks.append({
            "title": _setup_text(data.get("title"), "Task name", 120),
            "type": task_type,
            "target": _setup_number(data.get("target"), "Target", 1, 1_000_000),
            "item_name": _setup_text(data.get("item_name", ""), "Item name", 80, required=False),
            "repeatable": repeatable,
            "max_per_customer": int(limit),
            "rewards": [_setup_reward(reward) for reward in rewards],
        })

    boosts = setup.get("boosts", bp.get("boosts", []))
    if not isinstance(boosts, list) or len(boosts) > 20:
        raise ValidationError("Add no more than 20 starter boosts.")
    clean_boosts = []
    for data in boosts:
        if not isinstance(data, dict):
            raise ValidationError("Each boost must be an object.")
        serializer = BoostSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        clean_boosts.append(serializer.validated_data)

    clean_perks = {}
    for trigger in ("welcome", "referral"):
        data = setup.get(trigger, bp[trigger])
        clean_perks[trigger] = _setup_reward(data) if data is not None else None
    return {"program": program, "tasks": clean_tasks, "boosts": clean_boosts, **clean_perks}


@transaction.atomic
def apply(biz, key, setup=None):
    """Create the blueprint for a business. Programs are always added; boosts, services, perks and tier perks
    are only filled in when the owner has not set them yet, so applying twice never duplicates them."""
    bp = BLUEPRINTS[key]
    config = _setup_config(key, setup)
    program = Program.objects.create(business=biz, title=config["program"])
    for t in config["tasks"]:
        task = Task.objects.create(program=program, title=t["title"], type=t["type"], target=t["target"],
                                   item_name=t["item_name"], repeatable=t["repeatable"],
                                   max_per_customer=t["max_per_customer"])
        for r in t["rewards"]:
            Reward.objects.create(task=task, **r)
    made = {"program": program.id, "boosts": 0, "services": 0, "perks": 0}
    if config["boosts"] and not biz.boosts.exists():
        for b in config["boosts"]:
            Boost.objects.create(business=biz, **b)
            made["boosts"] += 1
    if bp.get("services") and not biz.services.exists():
        for s in bp["services"]:
            Service.objects.create(business=biz, **s)
            made["services"] += 1
    for trig in ("welcome", "referral"):
        if config[trig] and not biz.perk_rewards.filter(trigger=trig).exists():
            Reward.objects.create(business=biz, trigger=trig, **config[trig])
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
