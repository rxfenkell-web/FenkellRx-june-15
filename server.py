import os
import json
import uuid
import zipfile
import io
from datetime import date, datetime
from zoneinfo import ZoneInfo
from http.server import SimpleHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import resend


def log(msg):
    """Unbuffered log so messages appear instantly in Render."""
    print(msg, flush=True)


# Always serve files from the directory containing this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM = os.environ.get("RESEND_FROM", "Fenkell Rx Pharmacy <onboarding@resend.dev>")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "FenkellRx2025")


def get_recipient():
    content = load_content()
    notif = content.get("notifications", {})
    return notif.get("recipientEmail", "").strip() or os.environ.get("NOTIFICATION_EMAIL", "fenkellrxpharmacy@gmail.com")

BANNER_FILE = os.path.join(BASE_DIR, "banner.json")
SUBMISSIONS_FILE = os.path.join(BASE_DIR, "submissions.json")
MEDICATIONS_FILE = os.path.join(BASE_DIR, "medications.json")
CONTENT_FILE = os.path.join(BASE_DIR, "content.json")


def load_content():
    try:
        with open(CONTENT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_content(data):
    try:
        with open(CONTENT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        github_sync_async(os.path.basename(CONTENT_FILE))
        return True
    except Exception as e:
        log(f"Error saving content: {e}")
        return False


def ensure_content_file():
    if not os.path.exists(CONTENT_FILE):
        log("WARNING: content.json not found — content API will return empty object.")


def load_submissions():
    try:
        with open(SUBMISSIONS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def save_submissions(data):
    try:
        with open(SUBMISSIONS_FILE, "w") as f:
            json.dump(data, f, indent=2)
        github_sync_async(os.path.basename(SUBMISSIONS_FILE))
        return True
    except Exception as e:
        log(f"Error saving submissions: {e}")
        return False


def ensure_submissions_file():
    if not os.path.exists(SUBMISSIONS_FILE):
        save_submissions([])


def log_submission(form_type, data):
    submissions = load_submissions()
    form_type = form_type or "Unknown"
    eastern = ZoneInfo("America/New_York")
    now_est = datetime.now(eastern)
    timestamp = now_est.strftime("%b %d, %Y %I:%M %p EST")

    if form_type == "Refill Request":
        first = data.get("firstName", "")
        last = data.get("lastName", "")
        contact = f"{first} {last}".strip() or "—"
        fields = [
            ("Patient Name",     contact),
            ("Date of Birth",    data.get("dob", "—")),
            ("Phone",            data.get("phone", "—")),
            ("Rx Number(s)",     data.get("rx", "—")),
            ("Preferred Method", data.get("method", "—")),
            ("Notes",            data.get("notes", "None")),
            ("Email",            data.get("customerEmail", "Not provided")),
        ]
    elif form_type == "Transfer Request":
        contact = data.get("name", "—")
        ref = data.get("ref", "").strip()
        fields = [
            ("Patient Name",         contact),
            ("Date of Birth",        data.get("dob", "—")),
            ("Patient Phone",        data.get("phone", "—")),
            ("Previous Pharmacy",    data.get("rxName", "—")),
            ("Prev. Pharmacy Phone", data.get("rxPhone", "—")),
            ("Email",                data.get("customerEmail", "Not provided")),
            ("Source",               ref if ref else "Direct / Unknown"),
        ]
    elif form_type == "Contact Inquiry":
        first = data.get("first", "")
        last = data.get("last", "")
        contact = f"{first} {last}".strip() or "—"
        fields = [
            ("Name",    contact),
            ("Phone",   data.get("phone", "—")),
            ("Email",   data.get("email") or data.get("customerEmail", "Not provided")),
            ("Topic",   data.get("topic", "—")),
            ("Message", data.get("message", "—")),
        ]
    elif form_type == "Newsletter Signup":
        contact = data.get("customerEmail", "—")
        fields = [("Email", contact)]
    else:
        contact = "—"
        fields = []

    entry = {
        "id":        str(uuid.uuid4()),
        "type":      form_type,
        "contact":   contact,
        "fields":    fields,
        "timestamp": timestamp,
    }
    submissions.insert(0, entry)
    submissions = submissions[:500]
    save_submissions(submissions)


def load_medications():
    try:
        with open(MEDICATIONS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"medications": []}


def save_medications(data):
    try:
        with open(MEDICATIONS_FILE, "w") as f:
            json.dump(data, f, indent=2)
        github_sync_async(os.path.basename(MEDICATIONS_FILE))
        return True
    except Exception as e:
        log(f"Error saving medications: {e}")
        return False


def ensure_medications_file():
    if not os.path.exists(MEDICATIONS_FILE):
        save_medications({"medications": []})



NEWS_FILE = os.path.join(BASE_DIR, "news.json")

def load_news():
    try:
        with open(NEWS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"updatedAt": "", "items": []}


def save_news(data):
    try:
        data["updatedAt"] = datetime.now(ZoneInfo("America/Detroit")).isoformat()
        with open(NEWS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        github_sync_async(os.path.basename(NEWS_FILE))
        return True
    except Exception as e:
        log(f"Error saving news: {e}")
        return False


def ensure_news_file():
    if not os.path.exists(NEWS_FILE):
        save_news({"items": []})


def load_banner_data():
    try:
        with open(BANNER_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"messages": []}


def save_banner_data(data):
    try:
        with open(BANNER_FILE, "w") as f:
            json.dump(data, f, indent=2)
        github_sync_async(os.path.basename(BANNER_FILE))
        return True
    except Exception as e:
        log(f"Error saving banner data: {e}")
        return False


def ensure_banner_file():
    if not os.path.exists(BANNER_FILE):
        save_banner_data({"messages": []})


def get_active_message():
    data = load_banner_data()
    today = datetime.now(ZoneInfo("America/Detroit")).date().isoformat()
    for msg in data.get("messages", []):
        if not msg.get("active", True):
            continue
        start = msg.get("startDate", "")
        end = msg.get("endDate", "")
        if start <= today <= end:
            return msg
    return None


def send_email(subject, body, to=None):
    if not RESEND_API_KEY:
        log("WARNING: RESEND_API_KEY not set — email not sent.")
        return False
    recipient = to if to else get_recipient()
    try:
        resend.api_key = RESEND_API_KEY
        params = {
            "from": RESEND_FROM,
            "to": [recipient],
            "subject": subject,
            "text": body,
        }
        email = resend.Emails.send(params)
        log(f"Email sent via Resend to {recipient} | id={email.get('id')}")
        return True
    except Exception as e:
        log(f"Resend send failed: {e}")
        return False


def build_confirmation_email(form_type, data):
    """Return (subject, body) for a customer confirmation email."""
    c = load_content()
    ct = c.get("contact", {})
    hr = c.get("hours", {})
    pharmacy_name    = ct.get("pharmacyName", "Fenkell Rx Pharmacy")
    pharmacy_phone   = ct.get("phone", "(313) 519-5700")
    pharmacy_fax     = ct.get("fax", "(313) 899-7389")
    pharmacy_email   = ct.get("email", "care@fenkellrxpharmacy.com")
    pharmacy_address = ct.get("address", "18360 Fenkell Ave, Detroit, MI 48223")
    pharmacy_hours   = (
        f"Mon: {hr.get('monday', '9:30 AM – 6:00 PM')}\n"
        f"Tue: {hr.get('tuesday', '9:30 AM – 6:00 PM')}\n"
        f"Wed: {hr.get('wednesday', '9:30 AM – 6:00 PM')}\n"
        f"Thu: {hr.get('thursday', '9:30 AM – 6:00 PM')}\n"
        f"Fri: {hr.get('friday', '9:30 AM – 6:00 PM')}\n"
        f"Sat: {hr.get('saturday', '9:30 AM – 3:00 PM')}\n"
        f"{hr.get('sundayLabel', 'Sundays & Holidays')}: {hr.get('sundayValue', 'Closed')}"
    )
    footer = (
        f"\n\n----------------------------------\n"
        f"{pharmacy_name}\n"
        f"{pharmacy_address}\n"
        f"Phone: {pharmacy_phone}\n"
        f"Fax (Prescriber Line): {pharmacy_fax}\n"
        f"Email: {pharmacy_email}\n"
        f"\nHours:\n{pharmacy_hours}\n"
        f"----------------------------------\n"
        f"This is an automated confirmation. Please do not reply to this email.\n"
        f"For urgent matters, call us directly at {pharmacy_phone}."
    )

    if form_type == "Refill Request":
        name = f"{data.get('firstName', '')} {data.get('lastName', '')}".strip()
        subject = f"Refill Request Received — Fenkell Rx Pharmacy"
        body = (
            f"Dear {name or 'Valued Patient'},\n\n"
            f"We have received your refill request and will have it ready as soon as possible.\n\n"
            f"Request Details:\n"
            f"  Rx Number(s): {data.get('rx', '—')}\n"
            f"  Preferred Pickup Method: {data.get('method', '—')}\n"
            f"  Notes: {data.get('notes', 'None')}\n\n"
            f"We will contact you when your prescription is ready.\n"
            f"{footer}"
        )
        return subject, body

    elif form_type == "Transfer Request":
        name = data.get("name", "Valued Patient")
        ref = data.get("ref", "").strip()
        source_line = f"\nSource / Referral:         {ref}" if ref else "\nSource / Referral:         Direct / Unknown"
        subject = f"Transfer Request Received — Fenkell Rx Pharmacy"
        body = (
            f"Dear {name},\n\n"
            f"We have received your prescription transfer request from {data.get('rxName', 'your previous pharmacy')}.\n\n"
            f"Our team will contact your previous pharmacy to process the transfer. "
            f"We will notify you once your prescription is ready.\n"
            f"{footer}"
        )
        return subject, body

    elif form_type == "Contact Inquiry":
        first = data.get("first", "")
        last = data.get("last", "")
        name = f"{first} {last}".strip() or "Valued Patient"
        subject = f"We Received Your Message — Fenkell Rx Pharmacy"
        body = (
            f"Dear {name},\n\n"
            f"Thank you for reaching out to Fenkell Rx Pharmacy. "
            f"We have received your message and will respond within 1 business day.\n\n"
            f"Your inquiry topic: {data.get('topic', '—')}\n"
            f"{footer}"
        )
        return subject, body

    elif form_type == "Newsletter Signup":
        subject = f"Welcome to the Fenkell Rx Health Newsletter"
        body = (
            f"Thank you for subscribing to the Fenkell Rx Pharmacy health newsletter!\n\n"
            f"We're glad to have you. As a subscriber, you can look forward to:\n\n"
            f"  - Health tips and wellness advice from our pharmacy team\n"
            f"  - Updates on available vaccinations and on-site health screenings\n"
            f"  - Information on new services and community health programs\n"
            f"  - Reminders about seasonal health (flu season, blood pressure awareness, and more)\n\n"
            f"We'll only send you content that's helpful.\n"
            f"{footer}"
        )
        return subject, body

    return None, None





# ===================== GITHUB PERSISTENCE SYNC =====================
# Render's filesystem is ephemeral: runtime writes are wiped on redeploy.
# Fix: every save also commits the file back to the GitHub repo, so the
# repo always holds the latest data and redeploys restore it intact.
# Setup (Render dashboard -> Environment):
#   GITHUB_TOKEN  = fine-grained PAT, this repo only, Contents: read/write
#   GITHUB_REPO   = e.g. "rxfenkell-web/FenkellRx-june-15"
#   GITHUB_BRANCH = "main" (optional, defaults to main)
# Commits use "[skip render]" so syncs never trigger a redeploy loop.
import base64
import threading
import urllib.request
import urllib.error

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.environ.get("GITHUB_REPO", "").strip()
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main").strip() or "main"
_sync_lock = threading.Lock()

def _github_request(url, data=None, method="GET"):
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "fenkellrx-data-sync",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))

def github_sync_file(filename):
    """Commit a local data file back to the repo. Never raises: local save
    already succeeded; sync failure only logs so the site keeps working."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return False
    try:
        fpath = os.path.join(BASE_DIR, filename)
        with open(fpath, "r", encoding="utf-8") as f:
            text = f.read()
        api = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
        with _sync_lock:
            sha = None
            try:
                info = _github_request(f"{api}?ref={GITHUB_BRANCH}")
                sha = info.get("sha")
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise
            payload = {
                "message": f"[skip render] Sync {filename} from live site",
                "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
                "branch": GITHUB_BRANCH,
            }
            if sha:
                payload["sha"] = sha
            _github_request(api, data=json.dumps(payload).encode("utf-8"), method="PUT")
        log(f"GitHub sync OK: {filename}")
        return True
    except Exception as e:
        log(f"GitHub sync FAILED for {filename}: {e}")
        return False

def github_sync_async(filename):
    """Fire-and-forget so admin saves and form posts never wait on GitHub."""
    threading.Thread(target=github_sync_file, args=(filename,), daemon=True).start()
# ===================== END GITHUB PERSISTENCE SYNC =====================


# ===================== MEDICATION SEO PAGES =====================
import re as _re
from html import escape as _esc

SITE_URL = "https://fenkellrxpharmacy.com"
PHARMACY_NAME = "Fenkell Rx Pharmacy"
PHARMACY_PHONE = "(313) 519-5700"
PHARMACY_TEL = "+13135195700"
PHARMACY_ADDR = "18360 Fenkell Ave, Detroit, MI 48223"

def med_slug(name):
    s = name.lower()
    s = _re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s

STATUS_LABELS = {
    "in_stock": ("In Stock Now", "#1a7f37", "https://schema.org/InStock"),
    "limited": ("Limited Availability", "#b7791f", "https://schema.org/LimitedAvailability"),
    "call_us": ("Call For Availability", "#b7791f", "https://schema.org/LimitedAvailability"),
    "out_of_stock": ("Currently Unavailable - Call Us", "#b42318", "https://schema.org/OutOfStock"),
}

def _site_nav_html():
    return """<nav class="site-nav">
  <div class="wrap nav-inner">
    <a href="/" class="nav-logo-link"><img src="/logo.png" alt="Fenkell Rx Pharmacy"></a>
    <div class="nav-actions">
      <a href="/" class="nav-back">&larr; <span class="label">Back to Home</span></a>
      <a href="tel:3135195700" class="nav-call">(313) 519-5700</a>
    </div>
  </div>
</nav>"""

def _med_page_css():
    return """
    *{margin:0;padding:0;box-sizing:border-box}
    body{font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;color:#1e2f3c;background:#FBF8F2;line-height:1.6}
    .wrap{max-width:860px;margin:0 auto;padding:0 20px}
    .site-nav{background:rgba(255,255,255,0.97);backdrop-filter:blur(12px);border-bottom:1px solid #e1edf4;position:sticky;top:0;z-index:100}
    .nav-inner{display:flex;align-items:center;justify-content:space-between;height:76px;gap:1rem}
    .nav-logo-link{display:flex;align-items:center;text-decoration:none;flex-shrink:0}
    .nav-logo-link img{height:56px;width:auto;display:block}
    .nav-actions{display:flex;gap:10px;align-items:center}
    .nav-back{display:inline-flex;align-items:center;gap:6px;font-size:14px;font-weight:500;color:#4A5568;padding:8px 16px;border:1.5px solid #e1edf4;border-radius:50px;text-decoration:none;transition:all .2s;white-space:nowrap}
    .nav-back:hover{border-color:#0089c0;color:#0089c0}
    .nav-call{display:inline-flex;align-items:center;gap:6px;font-size:14px;font-weight:700;color:#fff !important;background:#CC001C;padding:9px 18px;border-radius:50px;text-decoration:none;white-space:nowrap}
    .nav-call:hover{background:#a50016}
    @media (max-width:560px){.nav-back span.label{display:none}.nav-inner{height:68px}.nav-logo-link img{height:46px}}
    header.top{background:linear-gradient(135deg,#0077a8 0%,#00b4d8 45%,#48cae4 100%);color:#fff;padding:44px 0 40px}
    .crumb{font-size:13px;margin-bottom:14px}
    .crumb a{color:#bfe9fb;text-decoration:none}
    .crumb a:hover{text-decoration:underline}
    h1{font-size:clamp(24px,4.5vw,36px);line-height:1.15;letter-spacing:-.01em}
    .status{display:inline-flex;align-items:center;gap:8px;background:#fff;border-radius:999px;padding:8px 18px;font-weight:800;font-size:14px;margin-top:16px}
    .status .dot{width:10px;height:10px;border-radius:50%}
    .meta{margin-top:10px;font-size:14.5px;color:#d8f0fb}
    main{padding:34px 0 50px}
    .card{background:#fff;border:1px solid #e1edf4;border-radius:14px;padding:24px;margin-bottom:18px}
    .card h2{font-size:19px;margin-bottom:10px;color:#0b2231}
    .card p{font-size:15px;color:#42586a;margin-bottom:8px}
    .facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-top:6px}
    .fact{background:#f2f9fd;border-radius:10px;padding:12px 14px}
    .fact .k{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#5b7487}
    .fact .v{font-weight:700;font-size:15px;margin-top:2px}
    .cta{display:flex;gap:12px;flex-wrap:wrap;margin:22px 0}
    .btn{display:inline-flex;align-items:center;gap:8px;text-decoration:none;font-weight:800;font-size:15px;padding:14px 24px;border-radius:10px;transition:transform .15s,box-shadow .15s}
    .btn:hover{transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,0,0,.15)}
    .btn-red{background:#CC001C;color:#fff}
    .btn-blue{background:#0077a8;color:#fff}
    .btn-line{border:2px solid #0077a8;color:#0077a8;background:transparent}
    .faq h3{font-size:15.5px;margin:16px 0 4px;color:#0b2231}
    .faq p{font-size:14.5px;color:#42586a}
    .links{font-size:14px;margin-top:8px}
    .links a{color:#0077a8;font-weight:600;text-decoration:none;margin-right:16px}
    .links a:hover{text-decoration:underline}
    footer{background:#0b2231;color:#9db8c6;padding:26px 0;font-size:13px}
    footer a{color:#bfe9fb}
    .note{font-size:12.5px;color:#7b93a3;margin-top:14px}
    """

def render_med_page(med):
    name = _esc(med.get("name", ""))
    generic = _esc(med.get("genericName", "") or "")
    category = _esc(med.get("category", "") or "")
    notes = _esc(med.get("notes", "") or "")
    updated = _esc(med.get("updatedAt", "") or "")
    status = med.get("status", "in_stock")
    label, color, schema_avail = STATUS_LABELS.get(status, STATUS_LABELS["in_stock"])
    slug = med_slug(med.get("name", ""))
    url = SITE_URL + "/medications/" + slug

    title = f"{name} in Detroit, MI - {label} | {PHARMACY_NAME}"
    desc = (f"{name}" + (f" ({generic})" if generic else "") +
            f" - {label.lower()} at {PHARMACY_NAME}, an independent pharmacy in Detroit, MI 48223. "
            f"Free same-day delivery, easy prescription transfer. Call {PHARMACY_PHONE}.")

    faq = [
        (f"Is {name} in stock near me in Detroit?",
         f"{PHARMACY_NAME} at {PHARMACY_ADDR} currently lists {name} as: {label}. "
         f"Inventory changes daily - call {PHARMACY_PHONE} to confirm and we can set it aside for you."),
        (f"Can I transfer my {name} prescription to Fenkell Rx?",
         f"Yes. Transfers are free and take about 2 minutes - we contact your current pharmacy and handle everything. "
         f"Start online at {SITE_URL}/#transfer or call {PHARMACY_PHONE}."),
        (f"Do you deliver {name} in Detroit?",
         "Yes. We offer free same-day prescription delivery across Northwest Detroit, Redford Township, and Southfield "
         "with a valid prescription."),
    ]

    faq_ld = {
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [{"@type": "Question", "name": q,
                        "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]
    }
    biz_ld = {
        "@context": "https://schema.org", "@type": "Pharmacy",
        "name": PHARMACY_NAME, "url": SITE_URL, "telephone": PHARMACY_TEL,
        "address": {"@type": "PostalAddress", "streetAddress": "18360 Fenkell Ave",
                    "addressLocality": "Detroit", "addressRegion": "MI",
                    "postalCode": "48223", "addressCountry": "US"},
        "makesOffer": {"@type": "Offer",
                       "itemOffered": {"@type": "Product", "name": med.get("name", "")},
                       "availability": schema_avail,
                       "areaServed": "Detroit, MI"}
    }

    faq_html = "".join(f"<h3>{_esc(q)}</h3><p>{_esc(a)}</p>" for q, a in faq)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="icon" type="image/x-icon" href="/favicon.ico">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<link rel="canonical" href="{url}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta property="og:type" content="website">
<script type="application/ld+json">{json.dumps(biz_ld)}</script>
<script type="application/ld+json">{json.dumps(faq_ld)}</script>
<style>{_med_page_css()}</style>
</head>
<body>
{_site_nav_html()}
<header class="top">
  <div class="wrap">
    <div class="crumb"><a href="/">Home</a> &rsaquo; <a href="/medications">Medication Availability</a> &rsaquo; {name}</div>
    <h1>{name} in Detroit, MI</h1>
    <div class="status"><span class="dot" style="background:{color}"></span><span style="color:{color}">{label}</span></div>
    <div class="meta">{("Generic: " + generic + " &middot; ") if generic else ""}{("Category: " + category + " &middot; ") if category else ""}Updated {updated}</div>
  </div>
</header>
<main>
  <div class="wrap">
    <div class="card">
      <h2>Availability at Fenkell Rx Pharmacy</h2>
      <p>{name} is currently listed as <strong>{label}</strong> at our independent pharmacy at {PHARMACY_ADDR}.
      {("Note: " + notes) if notes else ""}</p>
      <div class="facts">
        <div class="fact"><div class="k">Status</div><div class="v" style="color:{color}">{label}</div></div>
        <div class="fact"><div class="k">Pharmacy</div><div class="v">{PHARMACY_NAME}</div></div>
        <div class="fact"><div class="k">Delivery</div><div class="v">Free, same-day</div></div>
        <div class="fact"><div class="k">Transfer</div><div class="v">Free, 2 minutes</div></div>
      </div>
      <div class="cta">
        <a class="btn btn-red" href="tel:3135195700">Call {PHARMACY_PHONE}</a>
        <a class="btn btn-blue" href="/#transfer">Transfer My Prescription</a>
        <a class="btn btn-line" href="/availability">Check All Availability</a>
      </div>
      <p class="note">A valid prescription from your provider is required. Inventory changes daily; please call to confirm current stock. This page provides availability information only and is not medical advice.</p>
    </div>
    <div class="card faq">
      <h2>Frequently Asked Questions</h2>
      {faq_html}
    </div>
    <div class="card">
      <h2>Why Detroit Patients Switch to Fenkell Rx</h2>
      <p>Same insurance and copays as the big chains - with no lines, a pharmacist who answers the phone, and free same-day home delivery across North Rosedale, Brightmoor, Old Redford, Grandmont, Redford Township, and Southfield.</p>
      <div class="links">
        <a href="/medications">All medications</a>
        <a href="/free-prescription-delivery-detroit">Free delivery</a>
        <a href="/blister-packaging-detroit">Blister packaging</a>
        <a href="/compounding-pharmacy-detroit">Compounding</a>
      </div>
    </div>
  </div>
</main>
<footer><div class="wrap">{PHARMACY_NAME} &middot; {PHARMACY_ADDR} &middot; <a href="tel:3135195700">{PHARMACY_PHONE}</a> &middot; <a href="/">fenkellrxpharmacy.com</a></div></footer>
</body>
</html>"""

def render_med_hub(meds):
    items = []
    cats = {}
    for m in meds:
        cats.setdefault(m.get("category", "Other") or "Other", []).append(m)
    body_rows = ""
    pos = 1
    ld_items = []
    for cat in sorted(cats):
        body_rows += f'<h2 style="margin:26px 0 10px;font-size:18px;color:#0b2231">{_esc(cat)}</h2>'
        for m in sorted(cats[cat], key=lambda x: x.get("name", "")):
            slug = med_slug(m.get("name", ""))
            label, color, _sa = STATUS_LABELS.get(m.get("status", "in_stock"), STATUS_LABELS["in_stock"])
            gen = m.get("genericName", "")
            body_rows += (f'<a class="row" href="/medications/{slug}">'
                          f'<span><strong>{_esc(m.get("name",""))}</strong>'
                          f'{("<em> - " + _esc(gen) + "</em>") if gen else ""}</span>'
                          f'<span class="st" style="color:{color}">{label}</span></a>')
            ld_items.append({"@type": "ListItem", "position": pos,
                             "name": m.get("name", ""),
                             "url": SITE_URL + "/medications/" + slug})
            pos += 1
    ld = {"@context": "https://schema.org", "@type": "ItemList",
          "name": "Medication availability at Fenkell Rx Pharmacy, Detroit MI",
          "itemListElement": ld_items}
    title = "Medication Availability in Detroit, MI | Fenkell Rx Pharmacy"
    desc = ("Live medication availability at Fenkell Rx Pharmacy, an independent pharmacy in Detroit, MI 48223. "
            "Hard-to-find medications in stock, free same-day delivery, free prescription transfers. Call (313) 519-5700.")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="icon" type="image/x-icon" href="/favicon.ico">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<link rel="canonical" href="{SITE_URL}/medications">
<script type="application/ld+json">{json.dumps(ld)}</script>
<style>{_med_page_css()}
.row{{display:flex;justify-content:space-between;gap:12px;background:#fff;border:1px solid #e1edf4;border-radius:10px;padding:14px 18px;margin-bottom:8px;text-decoration:none;color:#1e2f3c;font-size:15px}}
.row:hover{{border-color:#0089c0;box-shadow:0 8px 20px -10px rgba(0,90,130,.25)}}
.row em{{color:#66808f;font-style:normal;font-size:13px}}
.row .st{{font-weight:800;font-size:13px;white-space:nowrap}}</style>
</head>
<body>
{_site_nav_html()}
<header class="top"><div class="wrap">
  <div class="crumb"><a href="/">Home</a> &rsaquo; Medication Availability</div>
  <h1>Medication Availability - Detroit, MI</h1>
  <div class="meta">Live inventory at {PHARMACY_NAME}, {PHARMACY_ADDR}. Updated daily.</div>
</div></header>
<main><div class="wrap">
  {body_rows}
  <div class="cta" style="margin-top:26px">
    <a class="btn btn-red" href="tel:3135195700">Call {PHARMACY_PHONE}</a>
    <a class="btn btn-blue" href="/#transfer">Transfer My Prescription</a>
  </div>
  <p class="note">Do not see your medication listed? We special-order from multiple wholesalers - call and we will usually have it same or next day. Valid prescription required.</p>
</div></main>
<footer><div class="wrap">{PHARMACY_NAME} &middot; {PHARMACY_ADDR} &middot; <a href="tel:3135195700">{PHARMACY_PHONE}</a></div></footer>
</body>
</html>"""

def render_sitemap(meds):
    today = date.today().isoformat()
    urls = [
        (SITE_URL + "/", today, "1.0"),
        (SITE_URL + "/availability", today, "0.9"),
        (SITE_URL + "/medications", today, "0.9"),
        (SITE_URL + "/transfer", today, "0.8"),
        (SITE_URL + "/free-prescription-delivery-detroit", today, "0.8"),
        (SITE_URL + "/blister-packaging-detroit", today, "0.7"),
        (SITE_URL + "/compounding-pharmacy-detroit", today, "0.7"),
        (SITE_URL + "/privacy-policy", today, "0.3"),
    ]
    for m in meds:
        urls.append((SITE_URL + "/medications/" + med_slug(m.get("name", "")),
                     m.get("updatedAt", today) or today, "0.8"))
    try:
        news_items = load_news().get("items", [])
        if news_items:
            urls.append((SITE_URL + "/news", today, "0.8"))
        for it in news_items:
            if (it.get("body") or "").strip():
                urls.append((SITE_URL + "/news/" + (it.get("slug") or news_slug(it.get("title", ""))),
                             it.get("publishedAt", today) or today, "0.8"))
    except Exception:
        pass
    entries = "".join(
        f"<url><loc>{u}</loc><lastmod>{lm}</lastmod><priority>{pr}</priority></url>"
        for u, lm, pr in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + entries + "</urlset>")

def news_slug(title):
    return med_slug(title)[:80].strip("-")


def _build_availability_prerender(meds):
    """
    Returns (prerender_html, jsonld_script_tag) for the /availability page.
    prerender_html replaces <!--MEDS_PRERENDER--> so drug names are in raw HTML.
    jsonld_script_tag is injected before </head>.
    """
    # --- pre-rendered visible list ---
    cats = {}
    for m in meds:
        cat = m.get("category", "General") or "General"
        cats.setdefault(cat, []).append(m)

    rows_html = '<ul class="avail-prerender" style="list-style:none;padding:0;margin:0">'
    for cat in sorted(cats.keys()):
        rows_html += f'<li style="margin-top:1.2em"><strong style="font-size:.85em;text-transform:uppercase;letter-spacing:.06em;color:#42586a">{_esc(cat)}</strong><ul style="list-style:none;padding:0;margin:.4em 0 0">'
        for m in sorted(cats[cat], key=lambda x: x.get("name", "")):
            name = _esc(m.get("name", ""))
            gen  = _esc(m.get("genericName", "") or "")
            status_key = m.get("status", "in_stock")
            label, color, _sa = STATUS_LABELS.get(status_key, STATUS_LABELS["in_stock"])
            gen_span = f' <span style="color:#42586a;font-size:.9em">({gen})</span>' if gen else ""
            rows_html += (
                f'<li style="padding:.35em 0;border-bottom:1px solid #eee">'
                f'{name}{gen_span} '
                f'<span style="color:{color};font-size:.85em;font-weight:600">{_esc(label)}</span>'
                f'</li>'
            )
        rows_html += '</ul></li>'
    rows_html += '</ul>'

    # --- JSON-LD: Pharmacy + Drug/Offer list ---
    offers = []
    for m in meds:
        status_key = m.get("status", "in_stock")
        _label, _color, schema_avail = STATUS_LABELS.get(status_key, STATUS_LABELS["in_stock"])
        slug = med_slug(m.get("name", ""))
        offers.append({
            "@type": "Offer",
            "itemOffered": {
                "@type": "Drug",
                "name": m.get("name", ""),
                "alternateName": m.get("genericName", "") or None,
                "url": SITE_URL + "/medications/" + slug
            },
            "availability": schema_avail,
            "seller": {
                "@type": "Pharmacy",
                "name": PHARMACY_NAME,
                "url": SITE_URL,
                "telephone": PHARMACY_PHONE,
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": "18360 Fenkell Ave",
                    "addressLocality": "Detroit",
                    "addressRegion": "MI",
                    "postalCode": "48223",
                    "addressCountry": "US"
                }
            }
        })
    # Remove None values from alternateName
    for o in offers:
        if o["itemOffered"].get("alternateName") is None:
            del o["itemOffered"]["alternateName"]

    ld = {
        "@context": "https://schema.org",
        "@type": "Pharmacy",
        "name": PHARMACY_NAME,
        "url": SITE_URL,
        "telephone": PHARMACY_PHONE,
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "18360 Fenkell Ave",
            "addressLocality": "Detroit",
            "addressRegion": "MI",
            "postalCode": "48223",
            "addressCountry": "US"
        },
        "hasOfferCatalog": {
            "@type": "OfferCatalog",
            "name": "Medication Availability",
            "itemListElement": offers
        }
    }
    jsonld_tag = f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>'
    return rows_html, jsonld_tag

def _split_body_html(body):
    if not body:
        return ""
    body = body.strip()
    # If body is already HTML (from the rich text editor), render it directly
    if body.startswith("<"):
        return body
    # Legacy plain-text format: blank lines = paragraphs, ## = h2
    out = []
    for block in body.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("## "):
            out.append("<h2>" + _esc(block[3:].strip()) + "</h2>")
        else:
            out.append("<p>" + _esc(block).replace("\n", "<br>") + "</p>")
    return "".join(out)

def render_news_article(item):
    title = _esc(item.get("title", ""))
    tag = _esc(item.get("tag", "Update"))
    published = _esc(item.get("publishedAt", ""))
    slug = item.get("slug") or news_slug(item.get("title", ""))
    url = SITE_URL + "/news/" + slug
    summary = _esc(item.get("summary", ""))
    body_html = _split_body_html(item.get("body", ""))
    desc = (item.get("summary", "") or item.get("title", ""))[:158]

    ld = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": item.get("title", "")[:110],
        "description": desc,
        "datePublished": item.get("publishedAt", ""),
        "dateModified": item.get("updatedAt", item.get("publishedAt", "")),
        "mainEntityOfPage": url,
        "author": {"@type": "Organization", "name": PHARMACY_NAME, "url": SITE_URL},
        "publisher": {"@type": "Organization", "name": PHARMACY_NAME,
                      "logo": {"@type": "ImageObject", "url": SITE_URL + "/logo.png"}},
    }
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} | {PHARMACY_NAME}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="icon" type="image/x-icon" href="/favicon.ico">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<link rel="canonical" href="{url}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{_esc(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:type" content="article">
<script type="application/ld+json">{json.dumps(ld)}</script>
<style>{_med_page_css()}
article h2{{font-size:20px;color:#0b2231;margin:22px 0 8px}}
article p{{font-size:15.5px;color:#37505f;margin-bottom:12px;line-height:1.7}}
.tagline{{display:inline-block;font-size:11px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#0077a8;background:#e3f4fb;border-radius:999px;padding:4px 12px;margin-bottom:10px}}</style>
</head>
<body>
{_site_nav_html()}
<header class="top"><div class="wrap">
  <div class="crumb"><a href="/">Home</a> &rsaquo; <a href="/news">Health &amp; Pharmacy News</a></div>
  <h1>{title}</h1>
  <div class="meta">{tag} &middot; Published {published} &middot; {PHARMACY_NAME}, Detroit MI</div>
</div></header>
<main><div class="wrap">
  <div class="card"><article>
    <span class="tagline">{tag}</span>
    {("<p><strong>" + summary + "</strong></p>") if summary else ""}
    {body_html}
  </article></div>
  <div class="card">
    <h2 style="font-size:19px;margin-bottom:10px;color:#0b2231">Questions? Talk to a pharmacist who answers the phone.</h2>
    <p style="font-size:15px;color:#42586a">We are an independent pharmacy at {PHARMACY_ADDR}. Free same-day delivery across Northwest Detroit, free 2-minute prescription transfers, and real answers about your coverage.</p>
    <div class="cta">
      <a class="btn btn-red" href="tel:3135195700">Call {PHARMACY_PHONE}</a>
      <a class="btn btn-blue" href="/#transfer">Transfer My Prescription</a>
      <a class="btn btn-line" href="/medications">Medication Availability</a>
    </div>
    <p class="note">This article is general information, not medical or insurance advice. Coverage depends on your specific plan and eligibility. A valid prescription is required for all prescription medications.</p>
  </div>
</div></main>
<footer><div class="wrap">{PHARMACY_NAME} &middot; {PHARMACY_ADDR} &middot; <a href="tel:3135195700">{PHARMACY_PHONE}</a> &middot; <a href="/">fenkellrxpharmacy.com</a></div></footer>
</body>
</html>"""

def render_news_hub(items):
    rows = ""
    ld_items = []
    pos = 1
    for it in items:
        slug = it.get("slug") or news_slug(it.get("title", ""))
        has_body = bool((it.get("body") or "").strip())
        href = ("/news/" + slug) if has_body else (it.get("url") or "/")
        rows += (f'<a class="row" href="{_esc(href)}"><span>'
                 f'<strong>{_esc(it.get("title",""))}</strong>'
                 f'<em> - {_esc(it.get("publishedAt",""))}</em></span>'
                 f'<span class="st" style="color:#0077a8">{_esc(it.get("tag","Update"))}</span></a>')
        if has_body:
            ld_items.append({"@type": "ListItem", "position": pos,
                             "name": it.get("title", ""), "url": SITE_URL + "/news/" + slug})
            pos += 1
    ld = {"@context": "https://schema.org", "@type": "ItemList",
          "name": "Detroit Health and Pharmacy News - Fenkell Rx Pharmacy",
          "itemListElement": ld_items}
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Detroit Health &amp; Pharmacy News | {PHARMACY_NAME}</title>
<meta name="description" content="Health, medication availability, and insurance coverage news for Detroit from Fenkell Rx Pharmacy - an independent pharmacy at 18360 Fenkell Ave, Detroit MI 48223.">
<link rel="icon" type="image/x-icon" href="/favicon.ico">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<link rel="canonical" href="{SITE_URL}/news">
<script type="application/ld+json">{json.dumps(ld)}</script>
<style>{_med_page_css()}
.row{{display:flex;justify-content:space-between;gap:12px;background:#fff;border:1px solid #e1edf4;border-radius:10px;padding:14px 18px;margin-bottom:8px;text-decoration:none;color:#1e2f3c;font-size:15px}}
.row:hover{{border-color:#0089c0;box-shadow:0 8px 20px -10px rgba(0,90,130,.25)}}
.row em{{color:#66808f;font-style:normal;font-size:13px}}
.row .st{{font-weight:800;font-size:12px;white-space:nowrap}}</style>
</head>
<body>
{_site_nav_html()}
<header class="top"><div class="wrap">
  <div class="crumb"><a href="/">Home</a> &rsaquo; News</div>
  <h1>Detroit Health &amp; Pharmacy News</h1>
  <div class="meta">Coverage changes, medication availability, and health updates from {PHARMACY_NAME}.</div>
</div></header>
<main><div class="wrap">
  {rows if rows else '<p style="color:#42586a">No news items yet.</p>'}
  <div class="cta" style="margin-top:26px">
    <a class="btn btn-red" href="tel:3135195700">Call {PHARMACY_PHONE}</a>
    <a class="btn btn-blue" href="/#transfer">Transfer My Prescription</a>
  </div>
</div></main>
<footer><div class="wrap">{PHARMACY_NAME} &middot; {PHARMACY_ADDR} &middot; <a href="tel:3135195700">{PHARMACY_PHONE}</a></div></footer>
</body>
</html>"""

# ===================== END MEDICATION SEO PAGES =====================


# ===================== SERVER-RENDERED BANNER =====================
# The banner is injected into the HTML server-side ONLY when there is
# something to show. Crawlers (Google, AI assistants) never see a
# "we are closed" message unless it is genuinely active right now.
from datetime import timedelta

def detroit_today():
    return datetime.now(ZoneInfo("America/Detroit")).date()

def _nth_weekday(year, month, weekday, n):
    d = date(year, month, 1)
    offset = (weekday - d.weekday()) % 7
    return d + timedelta(days=offset + 7 * (n - 1))

def _last_weekday(year, month, weekday):
    if month == 12:
        d = date(year, 12, 31)
    else:
        d = date(year, month + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)

# key -> (label, date_fn(year) -> date)
# Holidays always fall on their actual calendar date, regardless of the day
# of the week it lands on. Dates are computed from `year`, so they roll
# forward automatically every year.
HOLIDAY_DEFS = {
    "new_years":     ("New Year's Day",      lambda y: date(y, 1, 1)),
    "mlk":           ("Martin Luther King Jr. Day", lambda y: _nth_weekday(y, 1, 0, 3)),
    "memorial":      ("Memorial Day",        lambda y: _last_weekday(y, 5, 0)),
    "juneteenth":    ("Juneteenth",          lambda y: date(y, 6, 19)),
    "independence":  ("Independence Day",    lambda y: date(y, 7, 4)),
    "labor":         ("Labor Day",           lambda y: _nth_weekday(y, 9, 0, 1)),
    "veterans":      ("Veterans Day",        lambda y: date(y, 11, 11)),
    "thanksgiving":  ("Thanksgiving",        lambda y: _nth_weekday(y, 11, 3, 4)),
    "christmas_eve": ("Christmas Eve",       lambda y: date(y, 12, 24)),
    "christmas":     ("Christmas Day",       lambda y: date(y, 12, 25)),
    "new_years_eve": ("New Year's Eve",      lambda y: date(y, 12, 31)),
}
HOLIDAY_ORDER = ["new_years", "mlk", "memorial", "juneteenth", "independence",
                 "labor", "veterans", "thanksgiving", "christmas_eve",
                 "christmas", "new_years_eve"]
DEFAULT_HOLIDAY_SETTINGS = {
    "enabled": ["new_years", "memorial", "independence", "labor",
                "thanksgiving", "christmas"],
    "leadDays": 7,
}

def get_holiday_settings():
    data = load_banner_data()
    hs = data.get("holidaySettings")
    if not isinstance(hs, dict):
        return dict(DEFAULT_HOLIDAY_SETTINGS)
    return {
        "enabled": [k for k in hs.get("enabled", DEFAULT_HOLIDAY_SETTINGS["enabled"])
                    if k in HOLIDAY_DEFS],
        "leadDays": max(0, min(30, int(hs.get("leadDays", 7) or 7))),
    }

def get_holiday_notice():
    """Returns (kind, text) where kind is 'today' or 'upcoming', or None."""
    hs = get_holiday_settings()
    today = detroit_today()
    lead = hs["leadDays"]
    best = None
    for key in hs["enabled"]:
        label, fn = HOLIDAY_DEFS[key]
        for year in (today.year, today.year + 1):
            hdate = fn(year)
            delta = (hdate - today).days
            if delta < 0 or delta > lead:
                continue
            if best is None or delta < best[0]:
                best = (delta, label, hdate)
    if best is None:
        return None
    delta, shown, hdate = best
    if delta == 0:
        # reopen: next day that is not Sunday and not this holiday
        nxt = hdate + timedelta(days=1)
        while nxt.weekday() == 6:
            nxt = nxt + timedelta(days=1)
        reopen_day = "tomorrow" if (nxt - hdate).days == 1 else nxt.strftime("%A")
        return ("today", f"{shown} \u2014 We are closed today. We reopen {reopen_day} at 9:30 AM.")
    day_str = hdate.strftime("%A, %B %-d") if os.name != "nt" else hdate.strftime("%A, %B %d")
    return ("upcoming", f"Heads up: we will be closed {day_str} for {shown}. Plan refills ahead \u2014 free delivery available.")

def get_banner_html():
    """Full banner markup, or empty string when nothing should show."""
    try:
        msg = get_active_message()
        text = None
        if msg and msg.get("text"):
            text = msg["text"]
        else:
            notice = get_holiday_notice()
            if notice:
                text = notice[1]
        if not text:
            return ""
        return ('<div id="frx-banner" style="background:linear-gradient(135deg,#7B1226 0%,#A01830 100%);'
                'color:#fff;text-align:center;padding:12px 20px;font-size:15px;font-weight:500;'
                'letter-spacing:0.01em;position:relative;z-index:999;">'
                '<span>' + _esc(text) + '</span></div>')
    except Exception as e:
        log(f"banner render error: {e}")
        return ""
# ===================== END SERVER-RENDERED BANNER =====================



class Handler(SimpleHTTPRequestHandler):

    def _clean_path(self):
        return urlparse(self.path).path

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _serve_html_with_seo(self, fpath):
        """Serve an HTML file with the Google verification meta tag injected if set."""
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                html = f.read()
            c = load_content()
            gsc_code = c.get("seo", {}).get("googleVerification", "").strip()
            if gsc_code:
                tag = f'<meta name="google-site-verification" content="{gsc_code}">'
                html = html.replace("</head>", f"  {tag}\n</head>", 1)
            if "<!--FRX_BANNER-->" in html:
                html = html.replace("<!--FRX_BANNER-->", get_banner_html(), 1)
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            self._respond(404, {"ok": False, "error": "Not found"})

    def do_GET(self):
        path = self._clean_path()
        if path == "/api/banner":
            msg = get_active_message()
            if not msg:
                notice = get_holiday_notice()
                if notice:
                    msg = {"text": notice[1], "kind": notice[0]}
            self._respond(200, {"ok": True, "message": msg})
        elif path in ("/", "/index.html"):
            self._serve_html_with_seo(os.path.join(BASE_DIR, "index.html"))
        elif path == "/availability":
            try:
                fpath = os.path.join(BASE_DIR, "availability.html")
                with open(fpath, "r", encoding="utf-8") as f:
                    html = f.read()
                # GSC verification tag
                c = load_content()
                gsc_code = c.get("seo", {}).get("googleVerification", "").strip()
                if gsc_code:
                    tag = f'<meta name="google-site-verification" content="{gsc_code}">'
                    html = html.replace("</head>", f"  {tag}\n</head>", 1)
                # FRX banner
                if "<!--FRX_BANNER-->" in html:
                    html = html.replace("<!--FRX_BANNER-->", get_banner_html(), 1)
                # Pre-render medication list + inject JSON-LD
                meds = load_medications().get("medications", [])
                prerender_html, jsonld_tag = _build_availability_prerender(meds)
                html = html.replace("<!--MEDS_PRERENDER-->", prerender_html, 1)
                html = html.replace("</head>", f"  {jsonld_tag}\n</head>", 1)
                body = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                self._respond(404, {"ok": False, "error": "Not found"})
        elif path == "/transfer":
            self._serve_html_with_seo(os.path.join(BASE_DIR, "transfer.html"))
        elif path == "/free-prescription-delivery-detroit":
            self._serve_html_with_seo(os.path.join(BASE_DIR, "free-prescription-delivery-detroit.html"))
        elif path == "/compounding-pharmacy-detroit":
            self._serve_html_with_seo(os.path.join(BASE_DIR, "compounding-pharmacy-detroit.html"))
        elif path == "/blister-packaging-detroit":
            self._serve_html_with_seo(os.path.join(BASE_DIR, "blister-packaging-detroit.html"))
        elif path == "/privacy-policy":
            self._serve_html_with_seo(os.path.join(BASE_DIR, "privacy-policy.html"))
        elif path == "/medications" or path == "/medications/":
            meds = load_medications().get("medications", [])
            body = render_med_hub(meds).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path.startswith("/medications/"):
            slug = path[len("/medications/"):].strip("/")
            meds = load_medications().get("medications", [])
            med = next((m for m in meds if med_slug(m.get("name", "")) == slug), None)
            if med is None:
                # drug removed or renamed: 301 to the hub so the URL keeps
                # working for visitors and its SEO equity flows to /medications
                self.send_response(301)
                self.send_header("Location", "/medications")
                self.end_headers()
            else:
                body = render_med_page(med).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        elif path == "/news" or path == "/news/":
            items = load_news().get("items", [])
            body = render_news_hub(items).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path.startswith("/news/"):
            slug = path[len("/news/"):].strip("/")
            items = load_news().get("items", [])
            item = next((i for i in items
                         if (i.get("slug") or news_slug(i.get("title",""))) == slug
                         and (i.get("body") or "").strip()), None)
            if item is None:
                self.send_response(301)
                self.send_header("Location", "/news")
                self.end_headers()
            else:
                body = render_news_article(item).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        elif path == "/sitemap.xml":
            meds = load_medications().get("medications", [])
            body = render_sitemap(meds).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/xml; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/content":
            content = load_content()
            content.pop("notifications", None)
            self._respond(200, content)
        elif path == "/api/medications":
            med_data = load_medications()
            meds = med_data.get("medications", [])[:10]
            self._respond(200, {"ok": True, "medications": meds})
        elif path == "/health":
            self._respond(200, {
                "ok": True,
                "status": "healthy",
                "emailConfigured": bool(RESEND_API_KEY),
                "emailProvider": "Resend",
                "resendFrom": RESEND_FROM,
                "adminPasswordSet": ADMIN_PASSWORD != "FenkellRx2025",
            })
        elif path == "/api/admin/export":
            qs = parse_qs(urlparse(self.path).query)
            pw = qs.get("password", [""])[0]
            if pw != ADMIN_PASSWORD:
                self._respond(401, {"ok": False, "error": "Invalid password"})
                return
            self._send_zip()
        else:
            super().do_GET()

    def do_POST(self):
        path = self._clean_path()
        log(f"[{datetime.now().strftime('%H:%M:%S')}] POST {path}")
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw)
        except Exception:
            self._respond(400, {"ok": False, "error": "Invalid JSON"})
            return

        if path == "/api/email":
            form_type = data.get("type", "Form Submission")
            subject = data.get("subject", f"New {form_type} — Fenkell Rx Pharmacy")
            body = data.get("body", json.dumps(data, indent=2))
            log_submission(form_type, data)
            email_sent = send_email(subject, body)
            customer_email = data.get("customerEmail", "").strip()
            if email_sent and customer_email:
                conf_subject, conf_body = build_confirmation_email(form_type, data)
                if conf_subject:
                    send_email(conf_subject, conf_body, to=customer_email)
            self._respond(200, {"ok": True, "emailSent": email_sent})

        elif path == "/api/admin/banner":
            if data.get("password") != ADMIN_PASSWORD:
                self._respond(401, {"ok": False, "error": "Invalid password"})
                return
            action = data.get("action")
            banner_data = load_banner_data()
            messages = banner_data.get("messages", [])
            if action == "list":
                self._respond(200, {"ok": True, "messages": messages})
            elif action == "add":
                new_msg = {
                    "id":        str(uuid.uuid4()),
                    "text":      data.get("text", ""),
                    "startDate": data.get("startDate", ""),
                    "endDate":   data.get("endDate", ""),
                    "active":    data.get("active", True),
                    "createdAt": date.today().isoformat(),
                }
                messages.append(new_msg)
                banner_data["messages"] = messages
                saved = save_banner_data(banner_data)
                self._respond(200 if saved else 500, {"ok": saved, "message": new_msg if saved else None})
            elif action == "update":
                msg_id = data.get("id")
                for msg in messages:
                    if msg["id"] == msg_id:
                        msg["text"]      = data.get("text",      msg["text"])
                        msg["startDate"] = data.get("startDate", msg["startDate"])
                        msg["endDate"]   = data.get("endDate",   msg["endDate"])
                        msg["active"]    = data.get("active",    msg["active"])
                        break
                banner_data["messages"] = messages
                saved = save_banner_data(banner_data)
                self._respond(200 if saved else 500, {"ok": saved})
            elif action == "delete":
                msg_id = data.get("id")
                banner_data["messages"] = [m for m in messages if m["id"] != msg_id]
                saved = save_banner_data(banner_data)
                self._respond(200 if saved else 500, {"ok": saved})
            elif action == "getHolidays":
                hs = get_holiday_settings()
                today = detroit_today()
                catalog = []
                for key in HOLIDAY_ORDER:
                    label, fn = HOLIDAY_DEFS[key]
                    hdate = fn(today.year)
                    if hdate < today:
                        hdate = fn(today.year + 1)
                    catalog.append({
                        "key": key, "label": label,
                        "nextDate": hdate.isoformat(),
                        "enabled": key in hs["enabled"],
                    })
                self._respond(200, {"ok": True, "holidays": catalog,
                                    "leadDays": hs["leadDays"]})
            elif action == "saveHolidays":
                enabled = [k for k in data.get("enabled", []) if k in HOLIDAY_DEFS]
                try:
                    lead = max(0, min(30, int(data.get("leadDays", 7))))
                except Exception:
                    lead = 7
                banner_data["holidaySettings"] = {"enabled": enabled, "leadDays": lead}
                saved = save_banner_data(banner_data)
                self._respond(200 if saved else 500, {"ok": saved})
            else:
                self._respond(400, {"ok": False, "error": "Unknown action"})

        elif path == "/api/admin/submissions":
            if data.get("password") != ADMIN_PASSWORD:
                self._respond(401, {"ok": False, "error": "Invalid password"})
                return
            action = data.get("action", "list")
            if action == "list":
                self._respond(200, {"ok": True, "submissions": load_submissions()})
            elif action == "clear":
                save_submissions([])
                self._respond(200, {"ok": True})
            else:
                self._respond(400, {"ok": False, "error": "Unknown action"})

        elif path == "/api/admin/medications":
            if data.get("password") != ADMIN_PASSWORD:
                self._respond(401, {"ok": False, "error": "Invalid password"})
                return
            action = data.get("action")
            med_data = load_medications()
            meds = med_data.get("medications", [])
            if action == "list":
                self._respond(200, {"ok": True, "medications": meds})
            elif action == "add":
                new_med = {
                    "id":          str(uuid.uuid4()),
                    "name":        data.get("name", "").strip(),
                    "genericName": data.get("genericName", "").strip(),
                    "category":    data.get("category", "General").strip(),
                    "status":      data.get("status", "in_stock"),
                    "notes":       data.get("notes", "").strip(),
                    "updatedAt":   date.today().isoformat(),
                }
                if not new_med["name"]:
                    self._respond(400, {"ok": False, "error": "Name is required"})
                    return
                meds.append(new_med)
                med_data["medications"] = meds
                saved = save_medications(med_data)
                self._respond(200 if saved else 500, {"ok": saved, "medication": new_med if saved else None})
            elif action == "update":
                med_id = data.get("id")
                for med in meds:
                    if med["id"] == med_id:
                        med["name"]        = data.get("name",        med["name"]).strip()
                        med["genericName"] = data.get("genericName", med["genericName"]).strip()
                        med["category"]    = data.get("category",    med["category"]).strip()
                        med["status"]      = data.get("status",      med["status"])
                        med["notes"]       = data.get("notes",       med["notes"]).strip()
                        med["updatedAt"]   = date.today().isoformat()
                        break
                med_data["medications"] = meds
                saved = save_medications(med_data)
                self._respond(200 if saved else 500, {"ok": saved})
            elif action == "delete":
                med_id = data.get("id")
                med_data["medications"] = [m for m in meds if m["id"] != med_id]
                saved = save_medications(med_data)
                self._respond(200 if saved else 500, {"ok": saved})
            else:
                self._respond(400, {"ok": False, "error": "Unknown action"})

        elif path == "/api/admin/news":
            if data.get("password") != ADMIN_PASSWORD:
                self._respond(401, {"ok": False, "error": "Invalid password"})
                return
            action = data.get("action", "list")
            news_data = load_news()
            items = news_data.get("items", [])
            if action == "list":
                self._respond(200, {"ok": True, "items": items})
            elif action == "add":
                item = {
                    "id":          str(uuid.uuid4()),
                    "title":       data.get("title", "").strip(),
                    "summary":     data.get("summary", "").strip(),
                    "url":         data.get("url", "").strip(),
                    "linkText":    data.get("linkText", "Read more").strip(),
                    "tag":         data.get("tag", "Update").strip(),
                    "body":        data.get("body", "").strip(),
                    "publishedAt": date.today().isoformat(),
                }
                if not item["title"]:
                    self._respond(400, {"ok": False, "error": "Title is required"})
                    return
                item["slug"] = news_slug(item["title"])
                # a full body means this item gets its own Google-indexable
                # article page - point the homepage card there automatically
                if item["body"] and not item["url"]:
                    item["url"] = "/news/" + item["slug"]
                    if item["linkText"] == "Read more":
                        item["linkText"] = "Read the full article"
                items.insert(0, item)
                news_data["items"] = items[:6]
                saved = save_news(news_data)
                self._respond(200 if saved else 500, {"ok": saved, "item": item if saved else None})
            elif action == "update":
                item_id = data.get("id")
                for it in items:
                    if it.get("id") == item_id:
                        it["title"]    = data.get("title", it.get("title", "")).strip()
                        it["summary"]  = data.get("summary", it.get("summary", "")).strip()
                        it["url"]      = data.get("url", it.get("url", "")).strip()
                        it["linkText"] = data.get("linkText", it.get("linkText", "Read more")).strip()
                        it["tag"]      = data.get("tag", it.get("tag", "Update")).strip()
                        it["body"]     = data.get("body", it.get("body", "")).strip()
                        if not it.get("slug"):
                            it["slug"] = news_slug(it.get("title", ""))
                        if it["body"] and not it.get("url"):
                            it["url"] = "/news/" + it["slug"]
                        break
                news_data["items"] = items
                saved = save_news(news_data)
                self._respond(200 if saved else 500, {"ok": saved})
            elif action == "delete":
                news_data["items"] = [it for it in items if it.get("id") != data.get("id")]
                saved = save_news(news_data)
                self._respond(200 if saved else 500, {"ok": saved})
            else:
                self._respond(400, {"ok": False, "error": "Unknown action"})

        elif path == "/api/admin/content":
            if data.get("password") != ADMIN_PASSWORD:
                self._respond(401, {"ok": False, "error": "Invalid password"})
                return
            action = data.get("action", "save")
            if action == "get":
                self._respond(200, {"ok": True, "content": load_content()})
                return
            content_data = data.get("content")
            if not isinstance(content_data, dict):
                self._respond(400, {"ok": False, "error": "Invalid content data"})
                return
            # Merge incoming data over existing, preserving non-empty existing
            # values when the incoming value is an empty string (prevents
            # accidental wipe of reviews and other fields from the admin panel)
            existing = load_content()
            def deep_merge(existing, incoming):
                result = dict(existing)
                for k, v in incoming.items():
                    if isinstance(v, dict) and isinstance(existing.get(k), dict):
                        result[k] = deep_merge(existing[k], v)
                    elif v == "" and isinstance(existing.get(k), str) and existing[k] != "":
                        result[k] = existing[k]
                    else:
                        result[k] = v
                return result
            merged = deep_merge(existing, content_data)
            saved = save_content(merged)
            self._respond(200 if saved else 500, {"ok": saved})

        elif path == "/api/admin/test-email":
            if data.get("password") != ADMIN_PASSWORD:
                self._respond(401, {"ok": False, "error": "Invalid password"})
                return
            if not RESEND_API_KEY:
                self._respond(200, {"ok": False, "error": "RESEND_API_KEY is not set on this server."})
                return
            test_subject = "Test Email — Fenkell Rx Pharmacy Forms"
            test_body = (
                "This is a test email sent from the Fenkell Rx admin panel.\n\n"
                "If you received this, your email configuration is working correctly "
                "and all website forms will send notifications as expected.\n\n"
                f"Resend From: {RESEND_FROM}\n"
                "Sent via: FenkellRxPharmacy.com Admin Panel"
            )
            ok = send_email(test_subject, test_body)
            self._respond(200, {"ok": ok, "error": None if ok else "Email send failed. Check RESEND_API_KEY in Render environment variables."})

        else:
            self._respond(404, {"ok": False, "error": "Not found"})

    def _send_zip(self):
        INCLUDE_FILES = [
            "index.html", "admin.html", "availability.html", "transfer.html", "privacy-policy.html",
            "compounding-pharmacy-detroit.html", "free-prescription-delivery-detroit.html", "blister-packaging-detroit.html",
            "style.css", "script.js",
            "logo.png", "server.py", "render.yaml", "requirements.txt",
            "banner.json", "submissions.json", "medications.json", "content.json",
        ]
        buf = io.BytesIO()
        today = date.today().isoformat()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname in INCLUDE_FILES:
                fpath = os.path.join(BASE_DIR, fname)
                if os.path.exists(fpath):
                    zf.write(fpath, fname)
        zip_bytes = buf.getvalue()
        filename = f"fenkellrx-backup-{today}.zip"
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(zip_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(zip_bytes)

    def _respond(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        log(f"[{datetime.now().strftime('%H:%M:%S')}] {fmt % args}")


if __name__ == "__main__":
    ensure_banner_file()
    ensure_news_file()
    ensure_submissions_file()
    ensure_medications_file()
    ensure_content_file()
    port = int(os.environ.get("PORT", 5000))
    log(f"Fenkell Rx server running on port {port}")
    log(f"Serving files from: {BASE_DIR}")
    log(f"Resend configured: {bool(RESEND_API_KEY)}")
    log(f"Resend API key length: {len(RESEND_API_KEY)}")
    log(f"Resend from: {RESEND_FROM}")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
