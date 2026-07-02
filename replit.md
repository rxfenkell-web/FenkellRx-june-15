# Fenkell Rx Pharmacy Website

A pharmacy website for Fenkell Rx Pharmacy (Detroit, MI) with a Python backend serving static HTML pages, form handling, and an admin panel.

## Stack

- **Backend**: Python 3.13, `http.server.SimpleHTTPRequestHandler`
- **Frontend**: Vanilla HTML/CSS/JS (no build step)
- **Email**: [Resend](https://resend.com) for form notifications and customer confirmations
- **Data**: JSON files (`banner.json`, `submissions.json`, `medications.json`, `content.json`)

## How to run

```
python3 server.py
```

Runs on port 5000. The workflow "Start application" is configured to start this automatically.

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `RESEND_API_KEY` | Yes (for email) | — | Resend API key for sending notification/confirmation emails |
| `RESEND_FROM` | No | `Fenkell Rx Pharmacy <onboarding@resend.dev>` | Sender address for outbound emails |
| `ADMIN_PASSWORD` | No | `FenkellRx2025` | Password for the admin panel (`/admin.html`) |
| `NOTIFICATION_EMAIL` | No | `fenkellrxpharmacy@gmail.com` | Fallback recipient for form submissions |

## Key pages

- `/` — Main homepage (`index.html`)
- `/availability` — Medication availability checker
- `/admin.html` — Admin panel (submissions, banner, medications, content, export)
- `/compounding-pharmacy-detroit` — SEO landing page
- `/free-prescription-delivery-detroit` — SEO landing page
- `/blister-packaging-detroit` — SEO landing page

## API endpoints

- `GET /api/banner` — Active banner message
- `GET /api/content` — Site content (from `content.json`)
- `GET /api/medications` — First 10 medications in stock
- `POST /api/email` — Form submissions (refill, transfer, contact, newsletter)
- `POST /api/admin/*` — Admin actions (password-protected)
- `GET /health` — Health check

## User preferences

- Keep the existing project structure and stack (no framework migration).
