import os
import io
import json
import requests
import textwrap
import xml.etree.ElementTree as ET
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
FB_PAGE_ID        = os.environ.get("FB_PAGE_ID")
FB_ACCESS_TOKEN   = os.environ.get("FB_ACCESS_TOKEN")

RED   = (200, 16, 46)
CYAN  = (0, 174, 239)
DARK  = (11, 37, 69)
WHITE = (255, 255, 255)
LIGHT = (220, 235, 245)

RSS_FEEDS = [
    "https://medlineplus.gov/feeds/news_en.xml",
    "https://newsinhealth.nih.gov/rss",
    "https://tools.cdc.gov/podcasts/feed.asp",
]

SERVICES = [
    {
        "title": "Free same-day delivery",
        "bullets": [
            "Free delivery to North Rosedale, Grandmont & Brightmoor",
            "Same-day delivery where possible",
            "No delivery fee — ever",
            "Call (313) 519-5700 to arrange",
        ],
        "caption": "Can't make it in? We deliver your prescriptions FREE to your door. Serving Northwest Detroit and surrounding areas. Call us at (313) 519-5700 or visit fenkellrxpharmacy.com",
    },
    {
        "title": "Walk-in vaccines — no appointment",
        "bullets": [
            "Flu, COVID, Shingles, RSV & more",
            "No appointment needed",
            "Most insurance covers vaccines at $0",
            "In and out in 5 minutes",
        ],
        "caption": "Protect yourself and your family. Walk-in vaccines available now — no appointment needed. Most insurance accepted at no cost. 18360 Fenkell Ave, Detroit (313) 519-5700",
    },
    {
        "title": "Custom compounding pharmacy",
        "bullets": [
            "Medications made to your doctor's exact specs",
            "Unique dosages unavailable commercially",
            "Custom flavors for kids & pets",
            "Board-certified pharmacists on staff",
        ],
        "caption": "Need a medication in a special dose or form? We compound custom medications tailored to you. Call (313) 519-5700 or visit fenkellrxpharmacy.com",
    },
    {
        "title": "Medication synchronization",
        "bullets": [
            "All refills aligned to ONE pickup date",
            "Never run out of medication again",
            "Free service for all patients",
            "Ask us to sync your prescriptions today",
        ],
        "caption": "Managing multiple medications? We sync all your refills to one convenient pickup date per month. No more running out. Ask your Fenkell RX pharmacist today. (313) 519-5700",
    },
    {
        "title": "Blister packaging — PillPack",
        "bullets": [
            "Pre-sorted daily dose packs",
            "Perfect for seniors & complex regimens",
            "Reduces medication errors",
            "Free for eligible patients",
        ],
        "caption": "Managing multiple medications daily? Our blister packaging pre-sorts your doses so you always take the right pill at the right time. Ask us about PillPack. (313) 519-5700",
    },
    {
        "title": "Free medication therapy management",
        "bullets": [
            "Comprehensive review of ALL your medications",
            "Identify dangerous drug interactions",
            "Improve adherence & health outcomes",
            "Free consultation — walk in anytime",
        ],
        "caption": "Taking 5 or more medications? A free medication review could save your life. Our pharmacists identify interactions and help optimize your health. Walk in today at 18360 Fenkell Ave.",
    },
    {
        "title": "Free health screenings",
        "bullets": [
            "Blood pressure checks — free",
            "Blood glucose screening — free",
            "No appointment needed",
            "Walk in anytime during pharmacy hours",
        ],
        "caption": "Know your numbers. Free blood pressure and blood sugar checks at Fenkell RX — no appointment, no charge. Early detection saves lives. 18360 Fenkell Ave, Detroit.",
    },
    {
        "title": "Easy prescription transfer",
        "bullets": [
            "Switch from CVS, Walgreens or any pharmacy",
            "We handle all the paperwork",
            "Takes less than 5 minutes",
            "Call (313) 519-5700 to transfer today",
        ],
        "caption": "Tired of long waits at the big chains? Switch to Fenkell RX in minutes — we handle everything. Call (313) 519-5700 or visit fenkellrxpharmacy.com",
    },
    {
        "title": "GoodRx & patient savings programs",
        "bullets": [
            "We accept GoodRx discounts",
            "Manufacturer assistance programs available",
            "Some medications free or near-free",
            "We find you the lowest price",
        ],
        "caption": "Struggling with medication costs? We accept GoodRx and help connect patients with programs that make medications free or very low cost. Ask us today. (313) 519-5700",
    },
]

def get_week_number():
    return datetime.now().isocalendar()[1]

def fetch_rss_article():
    for url in RSS_FEEDS:
        try:
            r = requests.get(url, timeout=10)
            root = ET.fromstring(r.content)
            items = root.findall(".//item")
            if items:
                item = items[0]
                title = item.findtext("title", "").strip()
                desc  = item.findtext("description", "").strip()
                link  = item.findtext("link", "").strip()
                if title and desc:
                    return {"title": title, "description": desc, "link": link}
        except Exception:
            continue
    return None

def rewrite_with_claude(article):
    prompt = f"""You are the social media manager for Fenkell RX Pharmacy, an independent community pharmacy at 18360 Fenkell Ave, Detroit MI, serving North Rosedale, Grandmont, and Brightmoor neighborhoods.

Rewrite the following NIH/CDC health article into a Facebook post for the pharmacy.

Article title: {article['title']}
Article content: {article['description']}

Return ONLY a valid JSON object with exactly these fields, no other text, no markdown:
{{
  "image_title": "5 words max bold headline",
  "image_subtitle": "one short line 8 words max",
  "bullets": ["fact 1", "fact 2", "fact 3", "fact 4"],
  "caption": "2-3 sentence Facebook caption with CTA mentioning Fenkell RX and phone (313) 519-5700",
  "hashtags": "#FenkellRX #DetroitHealth #NorthRosedale plus 2 topic hashtags"
}}

Rules: bullets under 10 words each, caption mentions Detroit or neighborhood names, keep it simple for everyday Detroit residents."""

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 600,
        "messages": [{"role": "user", "content": prompt}],
    }
    r = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=body, timeout=30)
    data = r.json()
    text = data["content"][0]["text"].strip()
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)

def build_service_post():
    idx = get_week_number() % len(SERVICES)
    svc = SERVICES[idx]
    return {
        "image_title": svc["title"],
        "image_subtitle": "Fenkell RX Pharmacy · Detroit MI",
        "bullets": svc["bullets"],
        "caption": svc["caption"],
        "hashtags": "#FenkellRX #DetroitHealth #NorthRosedale #CommunityPharmacy",
    }

def make_image(post_data, is_service=False):
    W, H = 1200, 630
    img  = Image.new("RGB", (W, H), DARK)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, W, 80], fill=RED)
    draw.rectangle([0, H - 14, W, H], fill=CYAN)
    draw.rectangle([0, 80, 8, H - 14], fill=CYAN)

    try:
        font_big   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
        font_med   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        font_tiny  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        font_logo  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
    except Exception:
        font_big = font_med = font_small = font_tiny = font_logo = ImageFont.load_default()

    draw.text((30, 22), "Fenkell RX Pharmacy", font=font_logo, fill=WHITE)
    draw.text((W - 320, 22), "fenkellrxpharmacy.com", font=font_tiny, fill=WHITE)

    badge_text  = "SERVICE SPOTLIGHT" if is_service else "HEALTH TIP"
    badge_color = CYAN if is_service else (240, 180, 0)
    bw = len(badge_text) * 13 + 20
    draw.rounded_rectangle([30, 105, 30 + bw, 140], radius=12, fill=badge_color)
    draw.text((40, 110), badge_text, font=font_tiny, fill=DARK)

    title = post_data.get("image_title", "")
    lines = textwrap.wrap(title, width=22)
    y = 155
    for line in lines[:2]:
        draw.text((30, y), line, font=font_big, fill=WHITE)
        y += 62

    subtitle = post_data.get("image_subtitle", "")
    draw.text((30, y + 4), subtitle, font=font_med, fill=CYAN)
    y += 52

    draw.rectangle([30, y + 10, W - 30, y + 12], fill=(100, 140, 180))
    y += 28

    for i, bullet in enumerate(post_data.get("bullets", [])[:4]):
        bx, by = 30, y + i * 46
        draw.ellipse([bx, by + 8, bx + 16, by + 24], fill=CYAN)
        btext = bullet if len(bullet) <= 58 else bullet[:55] + "..."
        draw.text((bx + 28, by), btext, font=font_small, fill=LIGHT)

    draw.text((30, H - 40), "Source: NIH / MedlinePlus / CDC — Public domain", font=font_tiny, fill=(160, 190, 215))
    draw.text((W - 360, H - 40), "18360 Fenkell Ave, Detroit MI 48223", font=font_tiny, fill=(160, 190, 215))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf

def post_to_facebook(post_data, image_buf):
    caption = post_data.get("caption", "") + "\n\n" + post_data.get("hashtags", "")
    url     = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/photos"
    files   = {"source": ("post.png", image_buf, "image/png")}
    data    = {"caption": caption, "access_token": FB_ACCESS_TOKEN}
    r       = requests.post(url, files=files, data=data, timeout=30)
    result  = r.json()
    if "id" in result:
        print(f"Facebook posted successfully — ID: {result['id']}")
        return True
    else:
        print(f"Facebook error: {result}")
        return False

def run():
    print(f"\nFenkell RX Social Post — {datetime.now().strftime('%A %B %d, %Y')}")
    today = datetime.now().weekday()
    is_service_day = (today == 4)

    if is_service_day:
        print("Friday — Service spotlight post")
        post_data = build_service_post()
        image_buf = make_image(post_data, is_service=True)
    else:
        print("Health tip post — fetching NIH/CDC content...")
        article = fetch_rss_article()
        if not article:
            print("Could not fetch RSS — exiting")
            return
        print(f"Article: {article['title'][:60]}...")
        print("Rewriting with Claude...")
        post_data = rewrite_with_claude(article)
        image_buf = make_image(post_data, is_service=False)

    post_to_facebook(post_data, image_buf)
    print("Done.")

if __name__ == "__main__":
    run()
