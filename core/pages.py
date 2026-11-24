import segno
from pathlib import Path
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.html import escape
from django.utils.safestring import mark_safe
from .models import Business, Vendor

WEB = Path(__file__).parent / "web"
SIZES = {"a6": ("105mm 148mm", 1), "a5": ("148mm 210mm", 1), "a4": ("210mm 297mm", 1),
         "tent": ("210mm 297mm", 2)}  # tent: A4 folded in half, top panel upside-down
CATEGORY_THEMES = {
    "cafe": {"label": "Cafe & coffee", "hindi": "कैफ़े और कॉफ़ी", "accent": "#8a4b2a", "soft": "#f8eee5"},
    "restaurant": {"label": "Restaurant & dining", "hindi": "रेस्तराँ", "accent": "#c24132", "soft": "#fff0eb"},
    "grocery": {"label": "Grocery & convenience", "hindi": "किराना और सुविधा स्टोर", "accent": "#39804b", "soft": "#edf7e9"},
    "retail": {"label": "Fashion & retail", "hindi": "फ़ैशन और रिटेल", "accent": "#7546a8", "soft": "#f3edfb"},
    "salon": {"label": "Salon & wellness", "hindi": "सैलून और वेलनेस", "accent": "#bd4f78", "soft": "#fcecf2"},
    "fitness": {"label": "Fitness & studios", "hindi": "फ़िटनेस और स्टूडियो", "accent": "#176a91", "soft": "#e9f4f9"},
    "services": {"label": "Repair, clinic & services", "hindi": "रिपेयर, क्लिनिक और सेवाएँ", "accent": "#3d5a80", "soft": "#e9eff6"},
    "other": {"label": "Shop & rewards", "hindi": "दुकान और इनाम", "accent": "#5e35b1", "soft": "#f0eafa"},
}


ASSET_VERSION = "2.4.8"  # bump on every frontend release: busts the service-worker + browser cache for /static/app/*


def shell(request, code=None):
    """Single-page app shell. For /b/<code>/ we inject Open Graph tags so the QR/WhatsApp link shows a proper card."""
    html = (WEB / "app.html").read_text(encoding="utf-8").replace("{{V}}", ASSET_VERSION)
    meta = ""
    if code:
        b = Business.objects.filter(shop_code=code).first()
        if b and b.is_live:
            title = escape(f"{b.name} Rewards")
            desc = escape(b.tagline or f"Earn rewards every time you visit {b.name}. Join in 10 seconds.")
            meta = (f'<title>{title}</title><meta property="og:title" content="{title}">'
                    f'<meta property="og:description" content="{desc}"><meta name="description" content="{desc}">'
                    f'<meta name="theme-color" content="{escape(b.brand_color or "#5e35b1")}">')
    return HttpResponse(html.replace("<!--META-->", meta), content_type="text/html")


def classic(request):
    """The previous single-file UI, kept one release as a fallback (/app/classic/)."""
    html = (WEB / "app_classic.html").read_text(encoding="utf-8")
    html = html.replace("</head>", '<style>.brand-mark{background:url("/icon.svg") center/cover no-repeat}.brand-mark svg{display:none}</style></head>', 1)
    html = html.replace("</body>", f'<script src="/static/app/install.js?v={ASSET_VERSION}"></script></body>')
    return HttpResponse(html, content_type="text/html")


def print_card(request, code):
    """Counter / reception-desk card: shop profile + QR only (no bills)."""
    b = get_object_or_404(Business, shop_code=code)
    if b.sub_state == "expired":
        return HttpResponse("Subscription expired. Renew to download the print kit.", status=402)
    size = request.GET.get("size", "a6")
    page, reps = SIZES.get(size, SIZES["a6"])
    bw = request.GET.get("bw") == "1"
    lang_hi = b.language == "hi" or request.GET.get("lang") == "hi"
    theme = CATEGORY_THEMES.get(b.category, CATEGORY_THEMES["other"])
    qr = segno.make(f"{settings.BASE_URL}/b/{b.shop_code}", error="m").svg_inline(
        scale=6, border=2, dark="#000", light="#fff")
    return render(request, "print.html", {"b": b, "qr": mark_safe(qr), "page": page, "size": size,
                  "panels": range(reps), "bw": bw, "tent": size == "tent",
                  "lang_hi": lang_hi, "theme": theme,
                  "category_label": theme["hindi"] if lang_hi else theme["label"]})


def healthz(request):
    from django.db import connection
    connection.cursor().execute("SELECT 1")
    return HttpResponse("ok")


def manifest(request):
    return JsonResponse({"name": "OFFLet", "short_name": "OFFLet", "start_url": "/app/", "scope": "/",
        "display": "standalone", "background_color": "#ffffff", "theme_color": "#5e35b1",
        "description": "Rewards, bookings and repeat customers for local businesses.",
        "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
                  {"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "maskable"}],
        "shortcuts": [{"name": "My rewards", "url": "/app/"}]})


def sw(request):
    """Service worker: stale-while-revalidate for the versioned app assets only. HTML and /api/ always hit the
    network, so a stale screen or a cached private response can never be served."""
    js = ("const V='offlet-%s';"
          "self.addEventListener('install',()=>self.skipWaiting());"
          "self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(k=>Promise.all("
          "k.filter(x=>x!==V).map(x=>caches.delete(x)))).then(()=>self.clients.claim())));"
          "self.addEventListener('fetch',e=>{const r=e.request,u=new URL(r.url);"
          "if(r.method!=='GET'||u.origin!==location.origin||!u.pathname.startsWith('/static/app/'))return;"
          "e.respondWith(caches.open(V).then(c=>c.match(r).then(h=>{"
          "const f=fetch(r).then(x=>{if(x.ok)c.put(r,x.clone());return x}).catch(()=>h);return h||f})))});") % ASSET_VERSION
    resp = HttpResponse(js, content_type="application/javascript")
    resp["Cache-Control"] = "no-cache"
    return resp


def icon(request):
    response = HttpResponse(
        (Path(__file__).parent / "static" / "app" / "offlet-icon.svg").read_text(encoding="utf-8"),
        content_type="image/svg+xml",
    )
    response["Cache-Control"] = "no-cache"
    return response


_FLYER = {
    "en": {"h": "Make customers come back.", "sub": "Stamp cards, rewards and bookings for your shop. Customers scan a QR code. No app to install.",
           "b": ["Set up in one minute with a ready-made program for your business type", "Approve purchases from your phone, see who is slipping away, send win-back offers",
                 "Free {t}-day trial, then from \u20b9{m} a month (GST included)"], "scan": "Scan to start your free trial", "by": "Your OFFLet partner"},
    "hi": {"h": "ग्राहकों को वापस लाइए।", "sub": "आपकी दुकान के लिए स्टैम्प कार्ड, रिवॉर्ड और बुकिंग। ग्राहक QR कोड स्कैन करते हैं। कोई ऐप इंस्टॉल नहीं।",
           "b": ["अपने बिज़नेस के हिसाब से तैयार प्रोग्राम के साथ एक मिनट में सेटअप", "फ़ोन से खरीदारी अप्रूव करें, देखें कौन दूर हो रहा है, वापसी ऑफ़र भेजें",
                 "{t} दिन फ़्री ट्रायल, फिर \u20b9{m} महीने से (GST सहित)"], "scan": "फ़्री ट्रायल शुरू करने के लिए स्कैन करें", "by": "आपका OFFLet पार्टनर"},
}


def partner_flyer(request, code):
    """A4 flyer with the partner's own referral QR, for partners to print and hand out. Public by design (no PII)."""
    v = get_object_or_404(Vendor.objects.select_related("user"), code=code.upper(), status="approved")
    lang = "hi" if request.GET.get("lang") == "hi" else "en"
    t = _FLYER[lang]
    monthly = settings.PLANS.get("monthly", {}).get("amount", 0) // 100
    qr = segno.make(f"{settings.BASE_URL}/app/?ref={v.code}", error="m").svg_inline(scale=6, border=2, dark="#000", light="#fff")
    bullets = "".join(f"<li>{escape(x.format(t=settings.TRIAL_DAYS, m=monthly))}</li>" for x in t["b"])
    html = f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><title>OFFLet</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Sans+Devanagari:wght@400;600;700&display=swap"><style>
@page{{size:A4;margin:0}}body{{margin:0;font-family:Hind,"Noto Sans Devanagari",system-ui,sans-serif;color:#15192b}}
.p{{width:210mm;min-height:297mm;box-sizing:border-box;padding:18mm;background:#fff}}
.top{{background:linear-gradient(135deg,#7a4bd1,#3f2380);color:#fff;border-radius:8mm;padding:12mm}}h1{{font-size:40pt;margin:0 0 4mm;line-height:1.1}}
.top p{{font-size:15pt;margin:0;color:#e4d9f7}}ul{{font-size:15pt;line-height:1.5;padding-left:7mm;margin:10mm 0}}
.qr{{display:flex;gap:10mm;align-items:center;border:2px dashed #5e35b1;border-radius:8mm;padding:8mm}}.qr svg{{width:55mm;height:55mm}}
.qr b{{font-size:18pt;color:#3f2380}}.by{{margin-top:8mm;font-size:12pt;color:#555}}@media print{{.np{{display:none}}}}
</style></head><body><div class="p"><div class="top"><h1>{escape(t["h"])}</h1><p>{escape(t["sub"])}</p></div>
<ul>{bullets}</ul><div class="qr">{qr}<div><b>{escape(t["scan"])}</b><div style="font-size:13pt;margin-top:3mm">{escape(settings.BASE_URL)}/app/</div>
<div style="font-size:13pt">Code {escape(v.code)}</div></div></div>
<div class="by">{escape(t["by"])}: {escape(v.user.first_name)}</div>
<p class="np"><button onclick="print()">Print</button> <a href="?lang={'en' if lang == 'hi' else 'hi'}">{'English' if lang == 'hi' else 'हिन्दी'}</a></p></div></body></html>"""
    return HttpResponse(html)
