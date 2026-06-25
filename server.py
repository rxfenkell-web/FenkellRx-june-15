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
        fields = [
            ("Patient Name",         contact),
            ("Date of Birth",        data.get("dob", "—")),
            ("Patient Phone",        data.get("phone", "—")),
            ("Previous Pharmacy",    data.get("rxName", "—")),
            ("Prev. Pharmacy Phone", data.get("rxPhone", "—")),
            ("Email",                data.get("customerEmail", "Not provided")),
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
        return True
    except Exception as e:
        log(f"Error saving medications: {e}")
        return False


def ensure_medications_file():
    if not os.path.exists(MEDICATIONS_FILE):
        save_medications({"medications": []})


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
        return True
    except Exception as e:
        log(f"Error saving banner data: {e}")
        return False


def ensure_banner_file():
    if not os.path.exists(BANNER_FILE):
        save_banner_data({"messages": []})


def get_active_message():
    data = load_banner_data()
    today = date.today().isoformat()
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
            self._respond(200, {"ok": True, "message": msg})
        elif path in ("/", "/index.html"):
            self._serve_html_with_seo(os.path.join(BASE_DIR, "index.html"))
        elif path == "/availability":
            self._serve_html_with_seo(os.path.join(BASE_DIR, "availability.html"))
        elif path == "/free-prescription-delivery-detroit":
            self._serve_html_with_seo(os.path.join(BASE_DIR, "free-prescription-delivery-detroit.html"))
        elif path == "/compounding-pharmacy-detroit":
            self._serve_html_with_seo(os.path.join(BASE_DIR, "compounding-pharmacy-detroit.html"))
        elif path == "/blister-packaging-detroit":
            self._serve_html_with_seo(os.path.join(BASE_DIR, "blister-packaging-detroit.html"))
            elif path == "/privacy-policy":
            self._serve_html_with_seo(os.path.join(BASE_DIR, "privacy-policy.html"))
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
            "index.html", "admin.html", "availability.html","privacy-policy.html",
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
