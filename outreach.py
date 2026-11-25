"""Outreach: audit text, email drafts, approval queue, sending, follow-ups,
reply/unsubscribe detection and the pipeline.

Nothing is ever sent unless you approved that exact email in the app.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import imaplib
import random
import re
import smtplib
import ssl
import time
from email.message import EmailMessage

import wixbot as W

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
PROVIDERS = {
    "Google Workspace / Gmail": ("smtp.gmail.com", 587, "imap.gmail.com", 993),
    "Microsoft 365 / Outlook": ("smtp.office365.com", 587, "outlook.office365.com", 993),
    "Zoho Mail": ("smtp.zoho.com", 587, "imap.zoho.com", 993),
    "Titan Mail": ("smtp.titan.email", 465, "imap.titan.email", 993),
    "Hostinger Mail": ("smtp.hostinger.com", 465, "imap.hostinger.com", 993),
    "GoDaddy / Microsoft 365": ("smtp.office365.com", 587, "outlook.office365.com", 993),
    "GoDaddy Workspace Email": ("smtpout.secureserver.net", 465, "imap.secureserver.net", 993),
    "Other": ("", 587, "", 993),
}
MX_HINTS = [("google.com", "Google Workspace / Gmail"), ("googlemail.com", "Google Workspace / Gmail"),
            ("outlook.com", "Microsoft 365 / Outlook"), ("zoho.", "Zoho Mail"),
            ("titan.email", "Titan Mail"), ("hostinger", "Hostinger Mail"),
            ("secureserver.net", "GoDaddy Workspace Email")]


def detect_provider(email_addr: str) -> tuple[str, list[str]]:
    """Look up the domain's mail servers (MX records) with Google's public DNS
    service and guess the provider. Returns (provider or "", mx hosts)."""
    import requests
    dom = email_addr.split("@")[-1].strip().lower()
    r = requests.get("https://dns.google/resolve", params={"name": dom, "type": "MX"},
                     timeout=15, headers={"User-Agent": W.USER_AGENT})
    hosts = [a["data"].split()[-1].rstrip(".").lower()
             for a in r.json().get("Answer", []) if a.get("type") == 15]
    for hint, name in MX_HINTS:
        if any(hint in h for h in hosts):
            return name, hosts
    return "", hosts

DEFAULTS = {
    "provider": "Google Workspace / Gmail",
    "smtp_host": "smtp.gmail.com", "smtp_port": 587,
    "imap_host": "imap.gmail.com", "imap_port": 993,
    "email": "info@nadevelopers.com",
    "sender_name": "Awais",
    "company": "NA Developers",
    "website": "www.nadevelopers.com",
    "calendly": "https://calendly.com/na-developers",
    "postal_address": "",
    "daily_limit": 25,
    "delay_min": 60, "delay_max": 150,
    "business_hours_only": True,
    "followup_days": [3, 7, 14],
    "job_title": "Founder",
    "autopilot": False,
    "warmup": True,
    "email_theme": "light",
    "whatsapp": "+92 315 5444281",
    "proof_line": "Wix Legend Partner · About 2,000 projects in 8 years · 24/7 support · Fixed written quote",
    "portfolio_url": "https://nadevelopers.com/portfolio",
    "offer": "Black Friday: free logo design with every new website order until December 1.",
    "offer_until": "2026-12-01",
}

# Categories where an online booking button really matters
BOOKING_CATEGORIES = {
    "dentist", "chiropractor_physio", "medical_clinic_medspa", "hair_salon_barber",
    "beauty_nails_spa", "fitness_yoga", "pet_services", "photographer", "tattoo",
    "cleaning_movers", "auto_services",
}

TEMPLATES = {
    1: ("{business}: 3 quick website fixes",
        "Hi {greeting},\n\n"
        "I took a quick look at {site} and found a few things that are probably costing you "
        "customers:\n\n"
        "{issues_bullets}\n\n"
        "I'm {sender_name} from {company}. We're a Wix Legend Partner and have built about 2,000 "
        "websites over 8 years, many for {category_plural} like you.\n\n"
        "Would a free 15-minute call to walk you through the fixes be useful? My calendar: {calendly}\n\n"
        "Or just reply \"yes\" and I'll send a short written plan instead.\n\n"
        "{sender_name}\n{company} · Wix Legend Partner\n{website}"),
    2: ("Re: {business}: 3 quick website fixes",
        "Hi {greeting},\n\n"
        "Just bringing this back to the top of your inbox. The fixes I mentioned for {site} are "
        "quick wins, and most of them we can do without changing how you run the site day to day.\n\n"
        "You'd get a fixed written quote before any work starts, so there are no surprises.\n\n"
        "Worth a quick look together?\n\n"
        "{sender_name}\n{company}"),
    3: ("One quick tip for {business}",
        "Hi {greeting},\n\n"
        "Here's one thing you can fix today, even if we never work together:\n\n"
        "{quick_win}\n\n"
        "If you'd like to see what we do for {category_plural}, here's some recent work: {portfolio}\n\n"
        "{offer}"
        "{sender_name}\n{company}"),
    4: ("Should I close your file?",
        "Hi {greeting},\n\n"
        "I haven't heard back, so I'll assume the timing isn't right and won't keep emailing.\n\n"
        "If improving {site} becomes a priority later, just reply to this email and I'll pick it "
        "up from there.\n\n"
        "{offer}"
        "All the best,\n{sender_name}\n{company}"),
    5: ("Checking back about {business}'s website",
        "Hi {greeting},\n\n"
        "A while ago you mentioned the timing wasn't right, so I'm checking back as promised.\n\n"
        "If updating {site} is on your list now, I'd be happy to show you what I'd change. "
        "It's a free 15-minute call and you'll get a fixed written quote afterwards.\n\n"
        "{offer}"
        "{sender_name}\n{company}"),
}

# Proof from nadevelopers.com (edit in Settings > Your details)
DEFAULT_TESTIMONIALS = [
    ["He went above and beyond! His patience with my small details was exceptional!", "Erica F., website client"],
    ["Fantastic service, website looks great, very fast. I'm definitely going to use him again.", "Voiyce, website client"],
    ["Prompt, patient and did an excellent job on my website redesign.", "Renea, redesign client"],
    ["He took all of my requests, answered all of my questions, and really delivered a solid product.", "Fallacious Nature, website client"],
]
# Emails that get the designed HTML version (0 = your answers to replies). The
# first email uses a lighter, personal layout.
BRANDED_STEPS = [0, 1, 2, 3, 4, 5]
STEP_LAYOUT = {0: "reply", 1: "first"}      # everything else uses the "followup" layout
DEFAULTS["testimonials"] = DEFAULT_TESTIMONIALS
DEFAULTS["branded_steps"] = BRANDED_STEPS

FOOTER = ("\n\n--\n{company} · www.nadevelopers.com\n"
          "If you'd rather not hear from us, just reply \"unsubscribe\" and we won't "
          "email you again.")

STATUSES = ["new", "draft", "emailed", "replied", "later", "call_booked", "proposal_sent",
            "won", "lost", "no_reply", "unsubscribed", "bounced", "do_not_contact"]
STATUS_LABELS = {
    "new": "New", "draft": "Draft ready", "emailed": "Emailed", "replied": "Replied",
    "later": "Not now (check back)",
    "call_booked": "Call booked", "proposal_sent": "Proposal sent", "won": "Won",
    "lost": "Lost", "no_reply": "No reply", "unsubscribed": "Unsubscribed",
    "bounced": "Bounced", "do_not_contact": "Do not contact",
}
CLOSED = {"won", "lost", "no_reply", "unsubscribed", "bounced", "do_not_contact"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS outreach (
    domain TEXT PRIMARY KEY, status TEXT, step INTEGER DEFAULT 0, to_addr TEXT,
    first_sent_at TEXT, last_sent_at TEXT, next_due_at TEXT, thread_msgid TEXT,
    notes TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, domain TEXT, step INTEGER, to_addr TEXT,
    subject TEXT, body TEXT, status TEXT, created_at TEXT, approved_at TEXT,
    sent_at TEXT, msgid TEXT, error TEXT
);
CREATE TABLE IF NOT EXISTS suppress (value TEXT PRIMARY KEY, reason TEXT, added_at TEXT);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, domain TEXT, kind TEXT, due TEXT, done INTEGER DEFAULT 0,
    UNIQUE(domain, kind)
);
CREATE INDEX IF NOT EXISTS ix_msg_status ON messages(status);
"""


def init(db: W.DB) -> None:
    with db.lock:
        db.conn.executescript(SCHEMA)
        have = {r[1] for r in db.conn.execute("PRAGMA table_info(messages)")}
        if "attachments" not in have:
            db.conn.execute("ALTER TABLE messages ADD COLUMN attachments TEXT")
        db.conn.commit()


def settings(cfg) -> dict:
    s = dict(DEFAULTS)
    s.update(cfg.get("outreach", {}))
    return s


def templates(cfg) -> dict:
    t = {k: list(v) for k, v in TEMPLATES.items()}
    for k, v in cfg.get("templates", {}).items():
        t[int(k)] = list(v)
    return t


# ---------------------------------------------------------------------------
# Audit (turns the bot's findings into plain-English points)
# ---------------------------------------------------------------------------
def _issue_points(lead: dict) -> list[tuple[str, str]]:
    """[(problem sentence, quick-win tip)] most persuasive first."""
    issues = lead.get("issues") or ""
    title = (lead.get("title") or "").strip()
    city = lead.get("city") or ""
    label = (W.load_categories().get(lead.get("category") or "", {}).get("label")
             or "your services").split("&")[0].strip().lower()
    out = []
    if "Free Wix address" in issues:
        out.append(("Your site is on a free wixsite.com address, which looks less "
                    "trustworthy to customers and is harder to find on Google.",
                    "Connect your own domain (like yourbusiness.com). It's quick and "
                    "makes the site look instantly more professional."))
    m = re.search(r"Copyright year (\d{4})", issues)
    if m:
        out.append((f"The footer still says © {m.group(1)}, which can make visitors "
                    "wonder if you're still open.",
                    "Update the copyright year in your footer (or make it show the "
                    "current year automatically)."))
    if "Generic or missing page title" in issues:
        shown = f"“{title}”" if title else "nothing useful"
        out.append((f"Your homepage title on Google shows {shown}, so Google can't "
                    "tell what you do or where.",
                    f"Change your homepage SEO title to something like “{label.title()}"
                    f"{' in ' + city if city else ''} | {lead.get('name') or 'Your Business'}”. "
                    "This alone can help you show up in local searches."))
    if "No online booking" in issues and lead.get("category") in BOOKING_CATEGORIES:
        out.append(("I couldn't find an online booking button. Most customers now "
                    "expect to book straight from their phone.",
                    "Add a “Book now” button at the top of the homepage that opens "
                    "Wix Bookings or your booking tool."))
    if "No meta description" in issues:
        out.append(("There's no Google description, so Google picks random text from "
                    "the page for your listing.",
                    "Add a 150-character description with your service, city and a "
                    "reason to call. In Wix: Pages > SEO basics."))
    m = re.search(r"Thin homepage \((\d+) words\)", issues)
    if m:
        out.append(("The homepage has very little text, so it's hard for Google (and "
                    "new customers) to see everything you offer.",
                    "Add a short section listing your main services, areas you serve "
                    "and a few customer reviews."))
    if "No H1 heading" in issues:
        out.append(("The homepage has no main heading, which Google uses to understand "
                    "the page.",
                    "Set your main homepage headline as Heading 1 in the Wix editor."))
    if not out:
        out.append(("The site works, but there's room to make it faster and clearer on "
                    "phones, which is where most of your visitors are.",
                    "Check your site on your phone: keep the phone number and a "
                    "booking/contact button visible at the top."))
    return out


def audit_text(lead: dict) -> str:
    pts = _issue_points(lead)
    name = lead.get("name") or lead.get("site_name") or lead.get("domain")
    lines = [f"Mini audit: {name}", f"Website: {lead.get('final_url') or lead.get('website')}",
             f"Opportunity score: {lead.get('score') or 0}/100", "", "What we found:"]
    lines += [f"  {i}. {p}" for i, (p, _) in enumerate(pts, 1)]
    lines += ["", "Quick wins:"]
    lines += [f"  • {t}" for _, t in pts[:3]]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Choosing the address and writing drafts
# ---------------------------------------------------------------------------
def best_email(lead: dict) -> str:
    emails = [e.strip() for e in (lead.get("emails") or "").split(";") if e.strip()]
    dom = lead.get("domain") or ""
    same = [e for e in emails if e.split("@")[-1].endswith(dom)]
    pref = sorted(same or emails, key=lambda e: (
        not e.startswith(("info@", "contact@", "hello@", "office@")), len(e)))
    return pref[0] if pref else ""


def testimonial_for(domain: str, s: dict) -> tuple[str, str] | None:
    items = [t for t in (s.get("testimonials") or []) if t and t[0]]
    if not items:
        return None
    return tuple(items[sum(map(ord, domain or "x")) % len(items)])


def _fill(text: str, lead: dict, s: dict) -> str:
    pts = _issue_points(lead)
    name = (lead.get("name") or lead.get("site_name") or "").strip()
    site = (lead.get("final_url") or lead.get("website") or lead.get("domain") or "")
    site = re.sub(r"^https?://(www\.)?", "", site).rstrip("/")
    cat = W.load_categories().get(lead.get("category") or "", {})
    plural = (cat.get("short") or (lead.get("category") or "local businesses").replace("_", " "))
    plural = plural.split(" & ")[0].split(",")[0].lower()
    offer = (s.get("offer") or "").strip()
    if offer and s.get("offer_until"):
        try:
            if dt.date.today() > dt.date.fromisoformat(s["offer_until"]):
                offer = ""
        except ValueError:
            pass
    values = {
        "category_plural": plural, "portfolio": s.get("portfolio_url", ""),
        "offer": (offer + "\n\n") if offer else "",
        "testimonial": (testimonial_for(lead.get("domain", ""), s) or ("", ""))[0],
        "business": name or site, "greeting": f"{name} team" if name else "there",
        "site": site, "city": lead.get("city") or "",
        "issues_bullets": "\n".join(f"• {p}" for p, _ in pts[:3]),
        "quick_win": pts[0][1], "calendly": s["calendly"], "company": s["company"],
        "sender_name": s["sender_name"], "website": s["website"],
        "postal_address": s["postal_address"],
    }
    try:
        return text.format(**values)
    except (KeyError, IndexError, ValueError):
        out = text
        for k, v in values.items():
            out = out.replace("{" + k + "}", v)
        return out


def make_draft(db: W.DB, cfg, lead: dict, step: int = 1, to_addr: str | None = None,
               subject: str | None = None, body: str | None = None) -> int | None:
    """Create a draft for one lead. Returns message id, or None if not allowed."""
    init(db)
    s = settings(cfg)
    to_addr = to_addr or best_email(lead)
    if not to_addr or is_suppressed(db, to_addr, lead["domain"]) or lead.get("no_solicit"):
        return None
    if step != 0 and db.q("SELECT 1 FROM messages WHERE domain=? AND step=? AND status IN"
                          " ('draft','approved','sent')", (lead["domain"], step)):
        return None
    if subject is None or body is None:
        subj, tbody = templates(cfg)[step]
        subject = _fill(subj, lead, s)
        body = _fill(tbody, lead, s)
    else:
        body = body.replace("{greeting}", _fill("{greeting}", lead, s))
    body = body.rstrip() + _fill(FOOTER, lead, s)
    with db.lock:
        cur = db.conn.execute(
            "INSERT INTO messages (domain, step, to_addr, subject, body, status, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (lead["domain"], step, to_addr, subject, body, "draft", W.now()))
        db.conn.commit()
        mid = cur.lastrowid
    if step == 1:
        set_status(db, lead["domain"], "draft", to_addr=to_addr)
        try:
            import website as WS
            url = WS.audit_url(db, lead["domain"])
            if url:
                WS.add_link_to_draft(db, lead["domain"], url)
        except Exception:
            pass
    return mid


def ai_draft(db: W.DB, cfg, lead: dict, psi_key: str = "") -> int | None:
    """Audit (if needed) + Gemini plan + custom first email as a draft."""
    import ai
    import audit as A
    a = A.get(db, lead["domain"])
    if not a:
        a = A.run(db, lead, psi_key, settings(cfg))
    plan = ai.get_plan(db, lead["domain"]) or ai.make_plan(db, cfg, lead, a)
    return make_draft(db, cfg, lead, 1, subject=plan.get("subject") or None, body=plan.get("email"))


def ai_draft_many(db: W.DB, cfg, levels=("super", "hot"), limit: int = 25, psi_key: str = "") -> int:
    init(db)
    todo = []
    for lead in db.lead_records():
        if lead["level"] not in levels or not lead.get("emails") or lead.get("no_solicit"):
            continue
        st = get_outreach(db, lead["domain"])
        if st and st["status"] != "new":
            continue
        if is_suppressed(db, best_email(lead), lead["domain"]):
            continue
        todo.append(lead)
        if len(todo) >= limit:
            break
    n = 0
    for i, lead in enumerate(todo):
        W.wait_if_paused()
        if W.send_stopped():
            break
        W.progress(phase="ai", done=i, total=len(todo),
                   label=f"Audit + Gemini email: {lead.get('name') or lead['domain']}")
        try:
            if ai_draft(db, cfg, lead, psi_key):
                n += 1
                W.log(f"  Draft ready: {lead.get('name') or lead['domain']}")
        except RuntimeError as e:
            W.log(f"  {lead['domain']}: {e}")
            if "API key" in str(e) or "refused" in str(e):
                raise
        W.progress(phase="ai", done=i + 1, total=len(todo), label="Writing emails")
    W.log(f"{n} custom drafts ready for your approval.")
    return n


def draft_for_level(db: W.DB, cfg, levels=("super", "hot"), limit: int = 50) -> int:
    """Create first-email drafts for leads that have never been contacted."""
    init(db)
    n = 0
    for lead in db.lead_records():
        if n >= limit:
            break
        if lead["level"] not in levels or not lead.get("emails") or lead.get("no_solicit"):
            continue
        st = get_outreach(db, lead["domain"])
        if st and st["status"] not in ("new",):
            continue
        if is_suppressed(db, best_email(lead), lead["domain"]):
            continue
        if make_draft(db, cfg, lead, 1):
            n += 1
    return n


def leads_to_contact(db: W.DB, levels=("super", "hot")) -> int:
    n = 0
    for lead in db.lead_records():
        if lead["level"] in levels and lead.get("emails") and not lead.get("no_solicit"):
            st = get_outreach(db, lead["domain"])
            if not st or st["status"] == "new":
                n += 1
    return n


def contact_today(db: W.DB, cfg, use_ai: bool, approve: bool, psi_key: str = "") -> dict:
    """One click: write first emails for today's Super + Hot leads (as many as today's
    sending limit allows), approve them if you said so, and send them slowly."""
    init(db)
    already = len(messages(db, "approved"))
    room = max(0, daily_limit(db, cfg) - sent_today(db) - already)
    before = {m["id"] for m in messages(db)}
    if room:
        W.log(f"\nContacting Super + Hot leads: up to {room} today.")
        if use_ai:
            ai_draft_many(db, cfg, limit=room, psi_key=psi_key)
        else:
            draft_for_level(db, cfg, limit=room)
    new = [m for m in messages(db, "draft") if m["id"] not in before and m["step"] == 1]
    out = {"drafted": len(new), "approved": 0, "sent": 0, "room": room}
    if not approve:
        return out
    for m in new:
        update_message(db, m["id"], status="approved")
    out["approved"] = len(new)
    if W.send_stopped():
        return out
    out["sent"] = send_approved(db, cfg)
    return out


def autopilot_day(db: W.DB, cfg, psi_key: str = "") -> dict:
    """Autopilot (only when you turned it on): today's follow-ups plus the next
    Super + Hot leads, approved and sent within the daily limit."""
    import ai
    s = settings(cfg)
    fu_before = {m["id"] for m in messages(db)}
    create_due_followups(db, cfg)
    for m in messages(db, "draft"):
        if m["id"] not in fu_before and m["step"] > 1:
            update_message(db, m["id"], status="approved")
    res = contact_today(db, cfg, use_ai=ai.enabled(cfg) and s.get("autopilot_ai", True), approve=True,
                        psi_key=psi_key)
    db.set_kv("autopilot_last", dt.date.today().isoformat())
    return res


# ---------------------------------------------------------------------------
# Pipeline state
# ---------------------------------------------------------------------------
def get_outreach(db: W.DB, domain: str) -> dict | None:
    init(db)
    with db.lock:
        cur = db.conn.execute("SELECT * FROM outreach WHERE domain=?", (domain,))
        row = cur.fetchone()
        names = [d[0] for d in cur.description]
    return dict(zip(names, row)) if row else None


ON_WON = None   # the app sets this to add a draft project on the website


def set_status(db: W.DB, domain: str, status: str, **fields) -> None:
    init(db)
    was = (get_outreach(db, domain) or {}).get("status")
    cur = get_outreach(db, domain) or {"domain": domain, "step": 0}
    cur.update(fields)
    cur["status"] = status
    cur["updated_at"] = W.now()
    cols = ["domain", "status", "step", "to_addr", "first_sent_at", "last_sent_at",
            "next_due_at", "thread_msgid", "notes", "updated_at"]
    db.x(f"INSERT OR REPLACE INTO outreach ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
         [cur.get(c) for c in cols])
    if status in CLOSED or status in ("replied", "call_booked", "proposal_sent"):
        # stop any follow-ups that were waiting
        db.x("UPDATE messages SET status='cancelled' WHERE domain=? AND status IN ('draft','approved')"
             " AND step > 1", (domain,))
    if status in ("unsubscribed", "do_not_contact", "bounced") and cur.get("to_addr"):
        suppress(db, cur["to_addr"], status)
    if status == "won" and was != "won" and ON_WON:
        try:
            ON_WON(domain)
        except Exception as e:
            W.log(f"  Couldn't add the project to your website: {e}")
    if status == "won":
        today = dt.date.today()
        for kind, days in (("review", 7), ("care_plan", 30), ("referral", 45)):
            db.x("INSERT OR IGNORE INTO tasks (domain, kind, due) VALUES (?,?,?)",
                 (domain, kind, (today + dt.timedelta(days=days)).isoformat()))
    if status == "later" and not fields.get("next_due_at"):
        db.x("UPDATE outreach SET next_due_at=? WHERE domain=?",
             ((dt.date.today() + dt.timedelta(days=75)).isoformat(), domain))


def set_notes(db: W.DB, domain: str, notes: str) -> None:
    st = get_outreach(db, domain)
    set_status(db, domain, st["status"] if st else "new", notes=notes)


def suppress(db: W.DB, value: str, reason: str) -> None:
    init(db)
    db.x("INSERT OR REPLACE INTO suppress VALUES (?,?,?)", (value.lower().strip(), reason, W.now()))


def unsuppress(db: W.DB, value: str) -> None:
    db.x("DELETE FROM suppress WHERE value=?", (value.lower().strip(),))


def is_suppressed(db: W.DB, email_addr: str, domain: str) -> bool:
    init(db)
    vals = [email_addr.lower(), (domain or "").lower(), email_addr.split("@")[-1].lower()]
    return bool(db.q(f"SELECT 1 FROM suppress WHERE value IN ({','.join('?' * len(vals))})", vals))


def messages(db: W.DB, status: str | None = None, domain: str | None = None) -> list[dict]:
    init(db)
    conds, args = [], []
    if status:
        conds.append("status=?"); args.append(status)
    if domain:
        conds.append("domain=?"); args.append(domain)
    sql = "SELECT * FROM messages" + (" WHERE " + " AND ".join(conds) if conds else "") + \
          " ORDER BY id DESC"
    with db.lock:
        cur = db.conn.execute(sql, args)
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]


def update_message(db: W.DB, mid: int, **fields) -> None:
    sets = ", ".join(f"{k}=?" for k in fields)
    db.x(f"UPDATE messages SET {sets} WHERE id=?", list(fields.values()) + [mid])


WARMUP_START, WARMUP_STEP = 25, 5


def bounce_rate(db: W.DB, days: int = 7) -> tuple[float, int]:
    """Share of emails sent in the last days that bounced, and how many were sent."""
    init(db)
    since = (dt.datetime.now() - dt.timedelta(days=days)).isoformat(timespec="seconds")
    sent = db.q("SELECT COUNT(DISTINCT domain) FROM messages WHERE status='sent' AND sent_at>=?", (since,))[0][0]
    bounced = db.q("SELECT COUNT(*) FROM outreach WHERE status='bounced' AND updated_at>=?", (since,))[0][0]
    return (bounced / sent if sent else 0.0), sent


def daily_limit(db: W.DB, cfg) -> int:
    """Today's sending limit. With warm-up on, it starts at 25 and rises by 5 each day
    you send, up to your 'Emails per day' setting; too many bounces send it back to 25."""
    s = settings(cfg)
    target = max(1, int(s["daily_limit"]))
    if not s.get("warmup", True) or target <= WARMUP_START:
        return target
    today = dt.date.today().isoformat()
    level = int(db.get_kv("warmup_level", "0") or 0) or WARMUP_START
    if db.get_kv("warmup_date", "") != today:
        last = db.get_kv("warmup_date", "")
        if last:
            had_sends = db.q("SELECT 1 FROM messages WHERE status='sent' AND sent_at LIKE ? LIMIT 1",
                             (last + "%",))
            rate, n = bounce_rate(db)
            if n >= 10 and rate > 0.05:
                level = WARMUP_START
                W.log(f"Warm-up: {rate:.0%} of recent emails bounced, so today's limit goes back to "
                      f"{WARMUP_START}. Clean your list or check Settings > Email account.")
            elif had_sends:
                level += WARMUP_STEP
        db.set_kv("warmup_date", today)
    level = max(1, min(target, level))
    db.set_kv("warmup_level", str(level))
    return level


def sent_today(db: W.DB) -> int:
    init(db)
    today = dt.date.today().isoformat()
    return db.q("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at LIKE ?",
                (today + "%",))[0][0]


def counts(db: W.DB) -> dict:
    init(db)
    out = {s: 0 for s in STATUSES}
    for st, n in db.q("SELECT status, COUNT(*) FROM outreach GROUP BY status"):
        out[st] = n
    out["_drafts"] = db.q("SELECT COUNT(*) FROM messages WHERE status='draft'")[0][0]
    out["_approved"] = db.q("SELECT COUNT(*) FROM messages WHERE status='approved'")[0][0]
    out["_sent_today"] = sent_today(db)
    return out


# ---------------------------------------------------------------------------
# Follow-ups
# ---------------------------------------------------------------------------
def create_due_followups(db: W.DB, cfg) -> int:
    init(db)
    s = settings(cfg)
    days = [0] + list(s["followup_days"])
    n = 0
    now = dt.datetime.now()
    leads = {l["domain"]: l for l in db.lead_records()}
    for row in db.q("SELECT domain, step, first_sent_at, to_addr FROM outreach"
                    " WHERE status='emailed'"):
        domain, step, first, to_addr = row
        if not first or step >= len(days):
            continue          # all emails sent: handled below after a grace period
        due = dt.datetime.fromisoformat(first) + dt.timedelta(days=days[step])
        if now >= due and domain in leads:
            if make_draft(db, cfg, leads[domain], step + 1, to_addr):
                n += 1
    # "not now" leads: a friendly check-back email after ~75 days
    for domain, due, to_addr in db.q("SELECT domain, next_due_at, to_addr FROM outreach"
                                     " WHERE status='later' AND next_due_at IS NOT NULL"):
        if due and dt.date.today().isoformat() >= due[:10] and domain in leads:
            if make_draft(db, cfg, leads[domain], 5, to_addr):
                n += 1
                db.x("UPDATE outreach SET next_due_at=NULL WHERE domain=?", (domain,))
    # leads that had all their emails and still no answer after the last one
    for domain, first in db.q("SELECT domain, first_sent_at FROM outreach WHERE status='emailed'"
                              " AND step >= ?", (len(days),)):
        if first and now >= dt.datetime.fromisoformat(first) + dt.timedelta(days=days[-1] + 7):
            set_status(db, domain, "no_reply")   # a week after the last email
    return n


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------
def _eastern_now() -> dt.datetime:
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        return dt.datetime.utcnow() - dt.timedelta(hours=5)


def in_business_hours(region: str | None = None) -> bool:
    """Mon-Fri 9am-5pm in the lead's own time zone (New York if unknown)."""
    t = None
    tz = W.REGION_TZ.get(region or "")
    if tz:
        try:
            from zoneinfo import ZoneInfo
            t = dt.datetime.now(ZoneInfo(tz))
        except Exception:
            t = None
    t = t or _eastern_now()
    return t.weekday() < 5 and 9 <= t.hour < 17


def _doh(name: str, rtype: str) -> list[str]:
    """DNS lookup through Google's public DNS-over-HTTPS (free, no setup)."""
    import requests
    r = requests.get("https://dns.google/resolve", params={"name": name, "type": rtype},
                     timeout=15, headers={"User-Agent": W.USER_AGENT})
    js = r.json()
    if js.get("Status") not in (0, 3):
        raise RuntimeError("DNS lookup failed")
    return [a.get("data", "") for a in js.get("Answer", [])]


_mx_cache: dict = {}


def address_ok(addr: str) -> bool | None:
    """True if the address's domain can receive email, False if it can't,
    None if we couldn't tell (then we send anyway)."""
    dom = addr.split("@")[-1].lower().strip()
    if dom in _mx_cache:
        return _mx_cache[dom]
    try:
        ok = bool(_doh(dom, "MX")) or bool(_doh(dom, "A"))
    except Exception:
        ok = None
    _mx_cache[dom] = ok
    return ok


def domain_health(email_addr: str) -> list[tuple[bool, str]]:
    """Checks that help your emails land in the inbox (SPF, DKIM, DMARC, MX)."""
    dom = email_addr.split("@")[-1].lower().strip()
    out = []
    mx = _doh(dom, "MX")
    out.append((bool(mx), f"Mail servers (MX): {', '.join(m.split()[-1] for m in mx) if mx else 'none found'}"))
    txt = [t.strip('"') for t in _doh(dom, "TXT")]
    spf = [t for t in txt if t.lower().startswith("v=spf1")]
    out.append((bool(spf), f"SPF: {spf[0][:90] if spf else 'missing - add the SPF record your email provider gives you'}"))
    dmarc = [t.strip('"') for t in _doh("_dmarc." + dom, "TXT") if "v=DMARC1" in t]
    out.append((bool(dmarc), f"DMARC: {dmarc[0][:90] if dmarc else 'missing - add a TXT record at _dmarc with v=DMARC1; p=none'}"))
    found = ""
    for sel in ("google", "selector1", "selector2", "zmail", "titan1", "default", "k1", "s1"):
        try:
            if any("p=" in t for t in _doh(f"{sel}._domainkey.{dom}", "TXT")):
                found = sel
                break
        except RuntimeError:
            continue
    out.append((bool(found), f"DKIM: found ({found})" if found else
                "DKIM: not found under common names - turn on DKIM in your email admin panel"))
    return out


def _smtp(cfg):
    import security
    s = settings(cfg)
    pw = security.get_secret(cfg, "smtp_password")
    if not (s["smtp_host"] and s["email"] and pw):
        raise RuntimeError("Add your email account and app password in Settings first.")
    ctx = ssl.create_default_context()
    if int(s["smtp_port"]) == 465:
        srv = smtplib.SMTP_SSL(s["smtp_host"], int(s["smtp_port"]), context=ctx, timeout=30)
    else:
        srv = smtplib.SMTP(s["smtp_host"], int(s["smtp_port"]), timeout=30)
        srv.starttls(context=ctx)
    srv.login(s["email"], pw)
    return srv


def design_extras(db, domain: str) -> dict:
    """Site address + phone speed score for the first email's snapshot card."""
    out = {}
    try:
        r = db.q("SELECT final_url FROM sites WHERE domain=?", (domain,))
        if r and r[0][0]:
            out["_site"] = r[0][0]
        import audit as A
        a = A.get(db, domain)
        perf = (a or {}).get("psi", {}).get("scores", {}).get("performance")
        if perf is not None:
            out["_speed"] = perf
        import website as WS
        cat = db.q("SELECT category FROM businesses WHERE domain=? LIMIT 1", (domain,))
        work = WS.work_for(db, cat[0][0] if cat else "")
        if work:
            out["work"] = work
    except Exception:
        pass
    return out


def build_message(cfg, msg: dict, thread_msgid: str | None, extras: dict | None = None) -> EmailMessage:
    s = settings(cfg)
    m = EmailMessage()
    m["From"] = email.utils.formataddr((f"{s['sender_name']} at {s['company']}", s["email"]))
    m["To"] = msg["to_addr"]
    m["Subject"] = msg["subject"]
    m["Date"] = email.utils.formatdate(localtime=True)
    m["Message-ID"] = email.utils.make_msgid(domain=s["email"].split("@")[-1])
    m["Reply-To"] = s["email"]
    m["List-Unsubscribe"] = f"<mailto:{s['email']}?subject=unsubscribe>"
    if thread_msgid:
        m["In-Reply-To"] = thread_msgid
        m["References"] = thread_msgid
    m.set_content(msg["body"])
    if msg.get("step") in (s.get("branded_steps") or []):
        import email_design
        sd = dict(s, **(extras or {}))
        m.add_alternative(email_design.to_html(msg["body"], sd, testimonial_for(msg.get("domain", ""), s),
                                               STEP_LAYOUT.get(msg.get("step"), "followup")), subtype="html")
    import json as _json
    import mimetypes
    import os
    for path in _json.loads(msg.get("attachments") or "[]"):
        if os.path.exists(path):
            ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
            maintype, subtype = ctype.split("/", 1)
            with open(path, "rb") as f:
                m.add_attachment(f.read(), maintype=maintype, subtype=subtype,
                                 filename=os.path.basename(path))
    return m


def preview_file(cfg, msg: dict, db=None) -> str:
    """Write an HTML preview of how the email will look and return its path."""
    import email_design
    import html as _h
    import os
    s = settings(cfg)
    head = (f"<div style='font:13px Segoe UI,Arial;max-width:600px;margin:16px auto;color:#16212D'>"
            f"<b>To:</b> {_h.escape(msg.get('to_addr', ''))}<br><b>Subject:</b> {_h.escape(msg.get('subject', ''))}"
            f"</div>")
    if msg.get("step") in (s.get("branded_steps") or []):
        sd = dict(s, **(design_extras(db, msg.get("domain", "")) if db else {}))
        page = email_design.to_html(msg["body"], sd, testimonial_for(msg.get("domain", ""), s),
                                    STEP_LAYOUT.get(msg.get("step"), "followup"))
        page = page.replace('<body style="margin:0;padding:0;background:#F3F5F8">',
                            '<body style="margin:0;padding:0;background:#F3F5F8">' + head, 1)
    else:
        page = ("<html><head><meta charset='utf-8'></head><body style='background:#F3F5F8;padding:8px'>" + head +
                "<div style='max-width:600px;margin:auto;background:#fff;padding:24px 28px;border-radius:10px;"
                "font:15px/1.6 Segoe UI,Arial;color:#16212D'><div style='color:#6B7785;font-size:12px;"
                "margin-bottom:10px'>Plain text only (design is switched off for this email)</div>" +
                _h.escape(msg["body"]).replace("\n", "<br>") + "</div></body></html>")
    path = os.path.join(W.HERE, "output", "email-preview.html")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    return path


def send_samples(cfg, db) -> str:
    """Send the real first email and a real follow-up to your own inbox, through
    your own email account, so you see exactly what a business owner sees."""
    s = settings(cfg)
    lead = next(iter(db.lead_records()), None) or {
        "domain": "brightsmileaustin.com", "name": "Bright Smile Dental", "final_url": "https://brightsmileaustin.com",
        "category": "dentist", "city": "Austin", "region_name": "Texas", "title": "Home | My Site",
        "issues": "Generic or missing page title (weak SEO); Copyright year 2019 (site not updated); "
                  "No online booking button found"}
    srv = _smtp(cfg)
    try:
        for step in (1, 3):
            subj, body = templates(cfg)[step]
            msg = {"to_addr": s["email"], "step": step, "domain": lead["domain"],
                   "subject": "[SAMPLE] " + _fill(subj, lead, s),
                   "body": _fill(body, lead, s) + _fill(FOOTER, lead, s)}
            srv.send_message(build_message(cfg, msg, None, design_extras(db, lead["domain"])))
    finally:
        srv.quit()
    return f"Two sample emails were sent to {s['email']}."


def send_as_client(db: W.DB, cfg, lead: dict, to_addr: str) -> str:
    """Send this lead's real first email to YOU, exactly as the business would get it
    (same subject, review-page link, design). Nothing is recorded as sent to the lead."""
    s = settings(cfg)
    row = db.q("SELECT id, subject, body FROM messages WHERE domain=? AND step=1 AND status IN ('draft','approved')"
               " ORDER BY id DESC LIMIT 1", (lead["domain"],))
    if row:
        mid, subject, body = row[0]
        msg = {"id": mid, "domain": lead["domain"], "step": 1, "subject": subject, "body": body}
        msg = _with_audit_page(db, cfg, msg)
    else:
        subj, tb = templates(cfg)[1]
        body = _fill(tb, lead, s) + _fill(FOOTER, lead, s)
        try:
            import website as WS
            if WS.enabled(cfg) and WS.settings(cfg)["audit_pages"]:
                url = WS.audit_url(db, lead["domain"]) or WS.publish_audit(db, cfg, lead)
                if url:
                    parts = body.split("\n\n")
                    body = "\n\n".join(parts[:3] + [WS.AUDIT_LINE.format(url=url)] + parts[3:])
        except Exception as e:
            W.log(f"  Review page skipped: {e}")
        msg = {"domain": lead["domain"], "step": 1, "subject": _fill(subj, lead, s), "body": body}
    msg["to_addr"] = to_addr
    srv = _smtp(cfg)
    try:
        srv.send_message(build_message(cfg, msg, None, design_extras(db, lead["domain"])))
    finally:
        srv.quit()
    return f"Sent {lead.get('name') or lead['domain']}'s first email to {to_addr}: \"{msg['subject']}\""


def test_connection(cfg, send_to_self: bool = True) -> str:
    srv = _smtp(cfg)
    try:
        if send_to_self:
            s = settings(cfg)
            m = build_message(cfg, {"to_addr": s["email"], "subject": "Wix Lead Bot test email",
                                    "step": 2, "domain": "test",
                                    "body": "Hi Awais,\n\nYour email settings work. This is how your branded "
                                            "follow-ups look.\n\n• Example point one\n• Example point two\n\n"
                                            f"{s['sender_name']}\n{s['company']}" + _fill(FOOTER, {}, s)}, None)
            srv.send_message(m)
    finally:
        srv.quit()
    return "Connected. A test email was sent to your own inbox." if send_to_self else "Connected."


def _with_audit_page(db: W.DB, cfg, msg: dict) -> dict:
    """If the website is connected, make sure the first email links to the lead's
    free audit page (publishing it now if needed). Never blocks sending."""
    try:
        import website as WS
        if not (WS.enabled(cfg) and WS.settings(cfg)["audit_pages"]):
            return msg
        url = WS.audit_url(db, msg["domain"])
        if not url:
            lead = next(iter(db.lead_records("s.domain=?", (msg["domain"],))), None)
            if lead:
                url = WS.publish_audit(db, cfg, lead)
        if url and url not in msg["body"]:
            WS.add_link_to_draft(db, msg["domain"], url)
            row = db.q("SELECT body FROM messages WHERE id=?", (msg["id"],))
            if row:
                msg = dict(msg, body=row[0][0])
    except Exception as e:
        W.log(f"  Audit page skipped for {msg['domain']}: {e}")
    return msg


def send_approved(db: W.DB, cfg) -> int:
    """Send approved emails, slowly, up to the daily limit. Uses the app's
    Pause/Stop buttons. Returns how many were sent."""
    init(db)
    s = settings(cfg)
    W.STOP.clear()
    queue = list(reversed(messages(db, "approved")))
    limit = daily_limit(db, cfg)
    room = max(0, limit - sent_today(db))
    queue = queue[:room]
    if not queue:
        W.log("Nothing to send (no approved emails, or today's limit is reached).")
        return 0
    region_of = {d: r for d, r in db.q("SELECT domain, region FROM businesses")}
    if s["business_hours_only"]:
        # send to whoever is in business hours right now first; wait for the rest
        ordered, waiting = [], list(queue)
        while waiting and not W.send_stopped():
            ready = [m for m in waiting if in_business_hours(region_of.get(m["domain"]))]
            if ready:
                ordered.append(ready[0])
                waiting.remove(ready[0])
                if len(ordered) == 1:
                    break
            else:
                W.progress(phase="send", done=0, total=len(queue),
                           label="Waiting for business hours in your leads' time zones")
                end = time.time() + 60
                while time.time() < end and not W.send_stopped():
                    time.sleep(0.5)
        queue = ordered + waiting
    W.log(f"\nSending {len(queue)} approved emails (limit today {limit}"
          + (f", warming up to {s['daily_limit']}" if limit < int(s['daily_limit']) else "") + ")...")
    sent = 0
    srv = None
    try:
        for i, msg in enumerate(queue):
            W.wait_if_paused()
            if W.send_stopped():
                break
            while s["business_hours_only"] and not in_business_hours(region_of.get(msg["domain"])) \
                    and not W.send_stopped():
                W.progress(phase="send", done=i, total=len(queue),
                           label=f"Waiting for business hours where {msg['to_addr']} is")
                time.sleep(30)
            if W.send_stopped():
                break
            if is_suppressed(db, msg["to_addr"], msg["domain"]):
                update_message(db, msg["id"], status="cancelled", error="unsubscribed")
                continue
            if address_ok(msg["to_addr"]) is False:
                update_message(db, msg["id"], status="failed",
                               error="this address's domain can't receive email")
                set_status(db, msg["domain"], "bounced")
                W.log(f"  SKIPPED {msg['to_addr']}: its domain can't receive email")
                continue
            st = get_outreach(db, msg["domain"]) or {}
            if msg["step"] > 1 and msg["step"] != 5 and st.get("status") != "emailed":
                update_message(db, msg["id"], status="cancelled", error="lead status changed")
                continue
            if msg["step"] == 1:
                msg = _with_audit_page(db, cfg, msg)
            W.progress(phase="send", done=i, total=len(queue), label=f"Sending to {msg['to_addr']}")
            try:
                if srv is None:
                    srv = _smtp(cfg)
                em = build_message(cfg, msg, st.get("thread_msgid") if msg["step"] > 1 else None,
                                   design_extras(db, msg["domain"]))
                srv.send_message(em)
            except (smtplib.SMTPException, OSError) as e:
                update_message(db, msg["id"], status="failed", error=str(e)[:300])
                W.log(f"  FAILED {msg['to_addr']}: {e}")
                srv = None
                if isinstance(e, smtplib.SMTPAuthenticationError):
                    raise RuntimeError("Email login failed. Check the app password in Settings.")
                continue
            stamp = W.now()
            update_message(db, msg["id"], status="sent", sent_at=stamp, msgid=em["Message-ID"])
            if msg["step"] == 0:          # an answer to their reply: keep the status
                cur = get_outreach(db, msg["domain"]) or {}
                set_status(db, msg["domain"], cur.get("status") or "replied", last_sent_at=stamp)
            else:
                fields = {"step": msg["step"] if msg["step"] != 5 else 4,
                          "last_sent_at": stamp, "to_addr": msg["to_addr"]}
                if msg["step"] in (1, 5):
                    fields.update(first_sent_at=stamp, thread_msgid=em["Message-ID"])
                set_status(db, msg["domain"], "emailed", **fields)
            sent += 1
            W.log(f"  SENT step {msg['step']} to {msg['to_addr']}")
            W.progress(phase="send", done=i + 1, total=len(queue), label=f"Sent {sent}")
            if i < len(queue) - 1:
                wait = random.uniform(s["delay_min"], s["delay_max"])
                end = time.time() + wait
                while time.time() < end and not W.send_stopped():
                    time.sleep(0.5)
    finally:
        if srv is not None:
            try:
                srv.quit()
            except Exception:
                pass
    W.log(f"Sent {sent} emails.")
    return sent


# ---------------------------------------------------------------------------
# Inbox check: replies, unsubscribes, bounces
# ---------------------------------------------------------------------------
AUTO_SUBJECT_RE = re.compile(r"out of (the )?office|automatic reply|auto.?reply|autoreply|auto.?response|"
                             r"away from (the )?office|on vacation|on leave|thank you for (your )?(email|"
                             r"message|contacting)|we (have )?received your (email|message)", re.I)


def is_auto_reply(raw: bytes) -> bool:
    """Out-of-office and 'thanks, we got your message' robots are not real replies."""
    import email as _email
    msg = _email.message_from_bytes(raw)
    auto = (msg.get("Auto-Submitted") or "").lower()
    if auto and auto != "no":
        return True
    if msg.get("X-Autoreply") or msg.get("X-Autorespond") or msg.get("X-Auto-Response-Suppress", "").lower() in ("all", "oof"):
        return True
    if (msg.get("Precedence") or "").lower() in ("auto_reply", "bulk", "junk"):
        return True
    return bool(AUTO_SUBJECT_RE.search(msg.get("Subject", "") or ""))


def _message_text(raw: bytes) -> tuple[str, str, str]:
    """(from address, subject, plain text) from a raw email."""
    import email as _email
    from email.header import decode_header, make_header
    msg = _email.message_from_bytes(raw)
    try:
        subject = str(make_header(decode_header(msg.get("Subject", ""))))
    except Exception:
        subject = msg.get("Subject", "")
    frm = email.utils.parseaddr(msg.get("From", ""))[1].lower()
    text = ""
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        if part.get_content_type() in ("text/plain", "text/html") and not part.get_filename():
            try:
                payload = part.get_payload(decode=True) or b""
                t = payload.decode(part.get_content_charset() or "utf-8", "ignore")
            except Exception:
                continue
            if part.get_content_type() == "text/html":
                t = W.visible_text(t)
            text = t
            if part.get_content_type() == "text/plain":
                break
    # drop the quoted original email
    text = re.split(r"\n\s*On .{5,120}wrote:|\n-{2,}\s*Original Message|\n>+", text)[0]
    return frm, subject, text.strip()


def _fetch(im, mid) -> bytes:
    typ, data = im.fetch(mid, "(BODY.PEEK[]<0.60000>)")
    return b"".join(p[1] for p in data if isinstance(p, tuple))


def _sender_matches(frm: str, to_addr: str | None, site_dom: str) -> bool:
    """IMAP's FROM search matches any part of the address ('ace.com' also finds
    'grace.com'), so check the sender properly before calling it a reply."""
    frm = (frm or "").lower()
    if to_addr and frm == to_addr.lower():
        return True
    dom = frm.rsplit("@", 1)[-1]
    site_dom = (site_dom or "").lower().removeprefix("www.")
    return bool(site_dom) and not site_dom.endswith("wixsite.com") and (dom == site_dom or dom.endswith("." + site_dom))


def _msg_date(raw: bytes):
    import email as _email
    try:
        d = email.utils.parsedate_to_datetime(_email.message_from_bytes(raw).get("Date"))
        return d.astimezone().replace(tzinfo=None) if d else None   # local time, like W.now()
    except Exception:
        return None


def _in_reply_to(raw: bytes) -> str:
    import email as _email
    m = _email.message_from_bytes(raw)
    return " ".join([m.get("In-Reply-To") or "", m.get("References") or ""])


def clean_false_replies(db: W.DB) -> int:
    """Undo 'replied' marks that came from emails that weren't really from the lead.
    (Real replies from another address are found again by their email thread.)"""
    init(db)
    fixed = 0
    for rid, domain, frm in db.q("SELECT id, domain, from_addr FROM replies"):
        if domain.startswith("inquiry-") or "@" in domain:
            continue
        o = get_outreach(db, domain) or {}
        if not _sender_matches(frm, o.get("to_addr"), domain.split("/")[0]):
            db.x("DELETE FROM replies WHERE id=?", (rid,))
            fixed += 1
    for (domain,) in db.q("SELECT domain FROM outreach WHERE status IN ('replied','later','lost')"):
        if not db.q("SELECT 1 FROM replies WHERE domain=?", (domain,)) and \
                db.q("SELECT 1 FROM messages WHERE domain=? AND status='sent'", (domain,)):
            db.x("UPDATE outreach SET status='emailed' WHERE domain=?", (domain,))
    return fixed


def _imap(cfg):
    import security
    s = settings(cfg)
    pw = security.get_secret(cfg, "smtp_password")
    if not (s["imap_host"] and pw):
        raise RuntimeError("Add your email account in Settings > Email account first.")
    im = imaplib.IMAP4_SSL(s["imap_host"], int(s["imap_port"]))
    im.login(s["email"], pw)
    return im


def lead_for_sender(db: W.DB, frm: str, refs: str = "") -> str | None:
    """Which lead (domain) an email is from, or None."""
    frm = (frm or "").lower()
    for domain, to_addr in db.q("SELECT domain, to_addr FROM outreach"):
        if _sender_matches(frm, to_addr, domain.split("/")[0]):
            return domain
    if refs.strip():
        for domain, msgid in db.q("SELECT domain, msgid FROM messages WHERE msgid IS NOT NULL"):
            if msgid in refs:
                return domain
    return None


def inbox_list(db: W.DB, cfg, limit: int = 80, folder: str = "INBOX") -> list[dict]:
    """The newest emails in your inbox, each matched to a lead when it is from one."""
    import email as _email
    from email.header import decode_header, make_header
    im = _imap(cfg)
    try:
        im.select(folder, readonly=True)
        typ, data = im.uid("search", None, "ALL")
        uids = data[0].split()[-limit:] if typ == "OK" and data and data[0] else []
        out = []
        if not uids:
            return out
        typ, data = im.uid("fetch", b",".join(uids).decode(),
                           "(FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE IN-REPLY-TO REFERENCES "
                           "AUTO-SUBMITTED X-AUTOREPLY PRECEDENCE)])")
        for part in data or []:
            if not isinstance(part, tuple):
                continue
            meta = part[0].decode("utf-8", "ignore")
            uid = re.search(r"UID (\d+)", meta)
            m = _email.message_from_bytes(part[1])
            try:
                subject = str(make_header(decode_header(m.get("Subject", ""))))
            except Exception:
                subject = m.get("Subject", "")
            name, addr = email.utils.parseaddr(m.get("From", ""))
            try:
                name = str(make_header(decode_header(name)))
            except Exception:
                pass
            refs = " ".join([m.get("In-Reply-To") or "", m.get("References") or ""])
            d = None
            try:
                d = email.utils.parsedate_to_datetime(m.get("Date")).astimezone()
            except Exception:
                pass
            out.append({"uid": uid.group(1) if uid else "", "from": addr.lower(), "name": name or addr,
                        "subject": subject or "(no subject)", "date": d.strftime("%d %b %H:%M") if d else "",
                        "ts": d.timestamp() if d else 0, "unread": "\\Seen" not in meta,
                        "auto": is_auto_reply(part[1]), "refs": refs,
                        "lead": lead_for_sender(db, addr, refs)})
        out.sort(key=lambda x: x["ts"], reverse=True)
        return out
    finally:
        try:
            im.logout()
        except Exception:
            pass


def inbox_read(cfg, uid: str, folder: str = "INBOX") -> dict:
    """Full text of one email (without marking it as read)."""
    import email as _email
    im = _imap(cfg)
    try:
        im.select(folder, readonly=True)
        typ, data = im.uid("fetch", uid, "(BODY.PEEK[]<0.200000>)")
        raw = b"".join(p[1] for p in data if isinstance(p, tuple))
        m = _email.message_from_bytes(raw)
        frm, subject, _ = _message_text(raw)
        full = ""
        for part in (m.walk() if m.is_multipart() else [m]):
            if part.get_content_type() in ("text/plain", "text/html") and not part.get_filename():
                try:
                    t = (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", "ignore")
                except Exception:
                    continue
                full = W.visible_text(t) if part.get_content_type() == "text/html" else t
                if part.get_content_type() == "text/plain":
                    break
        return {"from": frm, "subject": subject, "text": full.strip(), "refs": _in_reply_to(raw)}
    finally:
        try:
            im.logout()
        except Exception:
            pass


def check_inbox(db: W.DB, cfg, days: int = 30) -> dict:
    """Reads your inbox: sorts replies (interested / question / not now / no /
    unsubscribe), spots Calendly bookings and bounces."""
    import ai
    import security
    init(db)
    ai.init(db)
    s = settings(cfg)
    pw = security.get_secret(cfg, "smtp_password")
    if not (s["imap_host"] and pw):
        raise RuntimeError("Add your email account in Settings first.")
    since = (dt.date.today() - dt.timedelta(days=days)).strftime("%d-%b-%Y")
    res = {"replied": 0, "unsubscribed": 0, "bounced": 0, "booked": 0}
    if db.get_kv("replies_checked_v2", "") != "1":
        n = clean_false_replies(db)
        db.set_kv("replies_checked_v2", "1")
        if n:
            W.log(f"  Removed {n} wrong 'replied' mark(s) from emails that weren't from the lead.")
    contacted = db.q("SELECT domain, to_addr, status FROM outreach WHERE status IN"
                     " ('emailed','no_reply','replied','later','call_booked','proposal_sent')")
    if not contacted:
        return res
    W.log("\nChecking your inbox...")
    leads = {l["domain"]: l for l in db.lead_records()}
    im = imaplib.IMAP4_SSL(s["imap_host"], int(s["imap_port"]))
    try:
        im.login(s["email"], pw)
        im.select("INBOX", readonly=True)
        for i, (domain, to_addr, status) in enumerate(contacted):
            W.progress(phase="inbox", done=i, total=len(contacted), label=f"Checking {domain}")
            ids = set()
            site_dom = domain.split("/")[0]
            for who in {to_addr or "", "" if site_dom.endswith(".wixsite.com") else site_dom}:
                if not who:
                    continue
                typ, data = im.search(None, "SINCE", since, "FROM", f'"{who}"')
                if typ == "OK" and data and data[0]:
                    ids.update(data[0].split())
            # Replies from a different address (e.g. the owner's Gmail) still answer our email thread.
            sent_ids = [m for (m,) in db.q("SELECT msgid FROM messages WHERE domain=? AND msgid IS NOT NULL",
                                           (domain,))]
            for sent_id in sent_ids:
                typ, data = im.search(None, "SINCE", since, "HEADER", "In-Reply-To", sent_id)
                if typ == "OK" and data and data[0]:
                    ids.update(data[0].split())
            first = (get_outreach(db, domain) or {}).get("first_sent_at") or ""
            for mid in sorted(ids, key=int)[-3:]:
                raw = _fetch(im, mid)
                frm, subject, text = _message_text(raw)
                if frm == (s.get("email") or "").lower():
                    continue            # our own sent copy
                in_thread = any(x and x in _in_reply_to(raw) for x in sent_ids)
                if not in_thread and not _sender_matches(frm, to_addr, site_dom):
                    continue            # someone else whose address only looks similar
                when = _msg_date(raw)
                if first and when and when.isoformat() < first[:19]:
                    continue            # older than our first email, so not a reply to it
                if is_auto_reply(raw):
                    W.log(f"  Auto-reply from {domain} ignored (out of office / robot).")
                    continue
                snippet = text[:3000]
                if db.q("SELECT 1 FROM replies WHERE domain=? AND subject=? AND snippet=?",
                        (domain, subject, snippet)):
                    continue                     # already sorted earlier
                kind = ai.classify(cfg, f"Subject: {subject}\n{text}")
                db.x("INSERT OR IGNORE INTO replies (domain, from_addr, subject, snippet, kind,"
                     " received_at) VALUES (?,?,?,?,?,?)", (domain, frm, subject, snippet, kind, W.now()))
                new_status = {"unsubscribe": "unsubscribed", "no": "lost", "later": "later"}.get(kind, "replied")
                if status in ("call_booked", "proposal_sent") and new_status == "replied":
                    new_status = status          # don't move them backwards
                if kind == "unsubscribe":
                    res["unsubscribed"] += 1
                else:
                    res["replied"] += 1
                set_status(db, domain, new_status)
                status = new_status
                W.log(f"  REPLY from {domain}: {ai.REPLY_KINDS[kind]}")
        # Calendly bookings
        typ, data = im.search(None, "SINCE", since, "FROM", '"calendly"')
        ids = data[0].split() if typ == "OK" and data and data[0] else []
        addr_to_domain = {(a or "").lower(): d for d, a, _ in contacted if a}
        for mid in ids[-100:]:
            frm, subject, text = _message_text(_fetch(im, mid))
            if not re.search(r"new event|scheduled|booked|invitee", subject + " " + text[:500], re.I):
                continue
            blob = text.lower()
            for a, d in addr_to_domain.items():
                site = d.split("/")[0]
                if a in blob or (site and not site.endswith("wixsite.com") and site in blob):
                    st = (get_outreach(db, d) or {}).get("status")
                    if st not in ("call_booked", "proposal_sent", "won"):
                        set_status(db, d, "call_booked")
                        res["booked"] += 1
                        W.log(f"  CALL BOOKED (Calendly): {leads.get(d, {}).get('name') or d}")
        # bounces
        typ, data = im.search(None, "SINCE", since, "FROM", '"mailer-daemon"')
        ids = data[0].split() if typ == "OK" and data and data[0] else []
        for mid in ids[-200:]:
            typ, msgdata = im.fetch(mid, "(BODY.PEEK[TEXT]<0.6000>)")
            blob = b" ".join(p[1] for p in msgdata if isinstance(p, tuple)).decode("utf-8", "ignore").lower()
            for a, d in addr_to_domain.items():
                if a and a in blob and (get_outreach(db, d) or {}).get("status") != "bounced":
                    set_status(db, d, "bounced")
                    res["bounced"] += 1
                    W.log(f"  BOUNCED {a}")
    finally:
        try:
            im.logout()
        except Exception:
            pass
    W.progress(phase="inbox", done=len(contacted), total=len(contacted), label="Inbox checked")
    W.log(f"Inbox: {res['replied']} replies, {res['booked']} calls booked, "
          f"{res['unsubscribed']} unsubscribes, {res['bounced']} bounces.")
    return res


# ---------------------------------------------------------------------------
# After-sale reminders, results, backups
# ---------------------------------------------------------------------------
TASK_LABELS = {"review": "Ask for a Google review", "care_plan": "Offer the monthly care / SEO plan",
               "referral": "Ask for a referral",
               "viewed": "🔥 Opened their free review, follow up today",
               "inquiry": "New inquiry from your website, reply"}


def due_tasks(db: W.DB) -> list[tuple]:
    init(db)
    return db.q("SELECT id, domain, kind, due FROM tasks WHERE done=0 AND due <= ? ORDER BY due",
                (dt.date.today().isoformat(),))


def done_task(db: W.DB, tid: int) -> None:
    db.x("UPDATE tasks SET done=1 WHERE id=?", (tid,))


def funnel(db: W.DB) -> list[dict]:
    """Results by category: contacted, replied, booked, won."""
    init(db)
    rows = db.q("""SELECT b.category, o.status FROM outreach o
                   JOIN businesses b ON b.domain = o.domain
                   WHERE o.status NOT IN ('new','draft') GROUP BY o.domain""")
    out: dict = {}
    for cat, st in rows:
        r = out.setdefault(cat or "other", {"category": cat or "other", "emailed": 0, "replied": 0,
                                            "booked": 0, "won": 0})
        r["emailed"] += 1
        if st in ("replied", "later", "call_booked", "proposal_sent", "won", "lost"):
            r["replied"] += 1
        if st in ("call_booked", "proposal_sent", "won"):
            r["booked"] += 1
        if st == "won":
            r["won"] += 1
    return sorted(out.values(), key=lambda r: -r["emailed"])


def backup(db_path: str, keep: int = 14) -> str | None:
    """Once a day, copy the database to backups/ (keeps the last 14)."""
    import os
    import sqlite3
    folder = os.path.join(os.path.dirname(db_path), "backups")
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, f"wixbot-{dt.date.today().isoformat()}.sqlite")
    if os.path.exists(target) or not os.path.exists(db_path):
        return None
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(target)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    files = sorted(f for f in os.listdir(folder) if f.startswith("wixbot-"))
    for old in files[:-keep]:
        try:
            os.remove(os.path.join(folder, old))
        except OSError:
            pass
    return target
