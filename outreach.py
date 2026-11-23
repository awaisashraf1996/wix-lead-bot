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
    "Other": ("", 587, "", 993),
}

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
}

# Categories where an online booking button really matters
BOOKING_CATEGORIES = {
    "dentist", "chiropractor_physio", "medical_clinic_medspa", "hair_salon_barber",
    "beauty_nails_spa", "fitness_yoga", "pet_services", "photographer", "tattoo",
    "cleaning_movers", "auto_services",
}

TEMPLATES = {
    1: ("Quick idea for {business}'s website",
        "Hi {greeting},\n\n"
        "I was looking at {site} and noticed a few quick wins that could bring you "
        "more calls and bookings:\n\n"
        "{issues_bullets}\n\n"
        "We're {company}, a Wix Legend Partner studio. We fix and redesign Wix "
        "sites for local businesses like yours.\n\n"
        "Want me to send you a free one-page plan for your site? Or grab 15 minutes "
        "here: {calendly}\n\n"
        "{sender_name}\n{company} · Wix Legend Partner\n{website}"),
    2: ("Re: Quick idea for {business}'s website",
        "Hi {greeting},\n\n"
        "Just bumping this up. Happy to put together that free plan for {site}. "
        "It takes me about 10 minutes and there are no strings attached.\n\n"
        "Should I send it over?\n\n{sender_name}"),
    3: ("Re: Quick idea for {business}'s website",
        "Hi {greeting},\n\n"
        "One quick tip you can use even if we never work together:\n\n"
        "{quick_win}\n\n"
        "If you'd like us to handle this (and the rest), you can book a short call "
        "here: {calendly}\n\n{sender_name}"),
    4: ("Re: Quick idea for {business}'s website",
        "Hi {greeting},\n\n"
        "I don't want to fill your inbox, so this is my last note. If improving "
        "{site} becomes a priority, just reply to this email and I'll pick it up "
        "from there.\n\n"
        "Wishing you a great season,\n{sender_name}\n{company}"),
}

FOOTER = ("\n\n--\n{company} · {postal_address}\n"
          "If you'd rather not hear from us, just reply \"unsubscribe\" and we won't "
          "email you again.")

STATUSES = ["new", "draft", "emailed", "replied", "call_booked", "proposal_sent",
            "won", "lost", "no_reply", "unsubscribed", "bounced", "do_not_contact"]
STATUS_LABELS = {
    "new": "New", "draft": "Draft ready", "emailed": "Emailed", "replied": "Replied",
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
CREATE INDEX IF NOT EXISTS ix_msg_status ON messages(status);
"""


def init(db: W.DB) -> None:
    with db.lock:
        db.conn.executescript(SCHEMA)
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


def _fill(text: str, lead: dict, s: dict) -> str:
    pts = _issue_points(lead)
    name = (lead.get("name") or lead.get("site_name") or "").strip()
    site = (lead.get("final_url") or lead.get("website") or lead.get("domain") or "")
    site = re.sub(r"^https?://(www\.)?", "", site).rstrip("/")
    values = {
        "business": name or site, "greeting": f"{name} team" if name else "there",
        "site": site, "city": lead.get("city") or "",
        "issues_bullets": "\n".join(f"• {p}" for p, _ in pts[:3]),
        "quick_win": pts[0][1], "calendly": s["calendly"], "company": s["company"],
        "sender_name": s["sender_name"], "website": s["website"],
        "postal_address": s["postal_address"] or "[add your postal address in Settings]",
    }
    try:
        return text.format(**values)
    except (KeyError, IndexError, ValueError):
        out = text
        for k, v in values.items():
            out = out.replace("{" + k + "}", v)
        return out


def make_draft(db: W.DB, cfg, lead: dict, step: int = 1, to_addr: str | None = None) -> int | None:
    """Create a draft for one lead. Returns message id, or None if not allowed."""
    init(db)
    s = settings(cfg)
    to_addr = to_addr or best_email(lead)
    if not to_addr or is_suppressed(db, to_addr, lead["domain"]):
        return None
    if db.q("SELECT 1 FROM messages WHERE domain=? AND step=? AND status IN"
            " ('draft','approved','sent')", (lead["domain"], step)):
        return None
    subj, body = templates(cfg)[step]
    subject = _fill(subj, lead, s)
    body = _fill(body, lead, s) + _fill(FOOTER, lead, s)
    with db.lock:
        cur = db.conn.execute(
            "INSERT INTO messages (domain, step, to_addr, subject, body, status, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (lead["domain"], step, to_addr, subject, body, "draft", W.now()))
        db.conn.commit()
        mid = cur.lastrowid
    if step == 1:
        set_status(db, lead["domain"], "draft", to_addr=to_addr)
    return mid


def draft_for_level(db: W.DB, cfg, levels=("super", "hot"), limit: int = 50) -> int:
    """Create first-email drafts for leads that have never been contacted."""
    init(db)
    n = 0
    for lead in db.lead_records():
        if n >= limit:
            break
        if lead["level"] not in levels or not lead.get("emails"):
            continue
        st = get_outreach(db, lead["domain"])
        if st and st["status"] not in ("new",):
            continue
        if make_draft(db, cfg, lead, 1):
            n += 1
    return n


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


def set_status(db: W.DB, domain: str, status: str, **fields) -> None:
    init(db)
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
            if step >= len(days):
                set_status(db, domain, "no_reply")
            continue
        due = dt.datetime.fromisoformat(first) + dt.timedelta(days=days[step])
        if now >= due and domain in leads:
            if make_draft(db, cfg, leads[domain], step + 1, to_addr):
                n += 1
    # leads that had all their emails and still no answer after the last one
    for domain, first in db.q("SELECT domain, first_sent_at FROM outreach WHERE status='emailed'"
                              " AND step >= ?", (len(days),)):
        if first and now >= dt.datetime.fromisoformat(first) + dt.timedelta(days=days[-1] + 7):
            set_status(db, domain, "no_reply")
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


def in_business_hours() -> bool:
    t = _eastern_now()
    return t.weekday() < 5 and 9 <= t.hour < 17


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


def build_message(cfg, msg: dict, thread_msgid: str | None) -> EmailMessage:
    s = settings(cfg)
    m = EmailMessage()
    m["From"] = email.utils.formataddr((f"{s['sender_name']} at {s['company']}", s["email"]))
    m["To"] = msg["to_addr"]
    m["Subject"] = msg["subject"]
    m["Date"] = email.utils.formatdate(localtime=True)
    m["Message-ID"] = email.utils.make_msgid(domain=s["email"].split("@")[-1])
    m["List-Unsubscribe"] = f"<mailto:{s['email']}?subject=unsubscribe>"
    if thread_msgid:
        m["In-Reply-To"] = thread_msgid
        m["References"] = thread_msgid
    m.set_content(msg["body"])
    return m


def test_connection(cfg, send_to_self: bool = True) -> str:
    srv = _smtp(cfg)
    try:
        if send_to_self:
            s = settings(cfg)
            m = build_message(cfg, {"to_addr": s["email"], "subject": "Wix Lead Bot test email",
                                    "body": "Your email settings work. You can start sending."}, None)
            srv.send_message(m)
    finally:
        srv.quit()
    return "Connected. A test email was sent to your own inbox." if send_to_self else "Connected."


def send_approved(db: W.DB, cfg) -> int:
    """Send approved emails, slowly, up to the daily limit. Uses the app's
    Pause/Stop buttons. Returns how many were sent."""
    init(db)
    s = settings(cfg)
    if not s["postal_address"].strip():
        raise RuntimeError("Add a postal address in Settings > Your details. US law "
                           "(CAN-SPAM) requires one in every sales email.")
    W.STOP.clear()
    queue = list(reversed(messages(db, "approved")))
    room = max(0, int(s["daily_limit"]) - sent_today(db))
    queue = queue[:room]
    if not queue:
        W.log("Nothing to send (no approved emails, or today's limit is reached).")
        return 0
    W.log(f"\nSending {len(queue)} approved emails (limit {s['daily_limit']}/day)...")
    sent = 0
    srv = None
    try:
        for i, msg in enumerate(queue):
            W.wait_if_paused()
            if W.STOP.is_set():
                break
            while s["business_hours_only"] and not in_business_hours() and not W.STOP.is_set():
                W.progress(phase="send", done=i, total=len(queue),
                           label="Waiting for US business hours (Mon-Fri 9am-5pm New York)")
                time.sleep(30)
            if W.STOP.is_set():
                break
            if is_suppressed(db, msg["to_addr"], msg["domain"]):
                update_message(db, msg["id"], status="cancelled", error="unsubscribed")
                continue
            st = get_outreach(db, msg["domain"]) or {}
            if msg["step"] > 1 and st.get("status") != "emailed":
                update_message(db, msg["id"], status="cancelled", error="lead status changed")
                continue
            W.progress(phase="send", done=i, total=len(queue), label=f"Sending to {msg['to_addr']}")
            try:
                if srv is None:
                    srv = _smtp(cfg)
                em = build_message(cfg, msg, st.get("thread_msgid") if msg["step"] > 1 else None)
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
            fields = {"step": msg["step"], "last_sent_at": stamp, "to_addr": msg["to_addr"]}
            if msg["step"] == 1:
                fields.update(first_sent_at=stamp, thread_msgid=em["Message-ID"])
            set_status(db, msg["domain"], "emailed", **fields)
            sent += 1
            W.log(f"  SENT step {msg['step']} to {msg['to_addr']}")
            W.progress(phase="send", done=i + 1, total=len(queue), label=f"Sent {sent}")
            if i < len(queue) - 1:
                wait = random.uniform(s["delay_min"], s["delay_max"])
                end = time.time() + wait
                while time.time() < end and not W.STOP.is_set():
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
def check_inbox(db: W.DB, cfg, days: int = 30) -> dict:
    import security
    init(db)
    s = settings(cfg)
    pw = security.get_secret(cfg, "smtp_password")
    if not (s["imap_host"] and pw):
        raise RuntimeError("Add your email account in Settings first.")
    since = (dt.date.today() - dt.timedelta(days=days)).strftime("%d-%b-%Y")
    res = {"replied": 0, "unsubscribed": 0, "bounced": 0}
    contacted = db.q("SELECT domain, to_addr, status FROM outreach WHERE status IN"
                     " ('emailed','replied','call_booked','proposal_sent')")
    if not contacted:
        return res
    W.log("\nChecking your inbox for replies...")
    im = imaplib.IMAP4_SSL(s["imap_host"], int(s["imap_port"]))
    try:
        im.login(s["email"], pw)
        im.select("INBOX", readonly=True)
        for i, (domain, to_addr, status) in enumerate(contacted):
            W.progress(phase="inbox", done=i, total=len(contacted), label=f"Checking {domain}")
            typ, data = im.search(None, "SINCE", since, "FROM", f'"{domain}"')
            ids = data[0].split() if typ == "OK" and data and data[0] else []
            if not ids:
                continue
            unsub = False
            for mid in ids[-5:]:
                typ, msgdata = im.fetch(mid, "(BODY.PEEK[TEXT]<0.2000> BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
                blob = b" ".join(p[1] for p in msgdata if isinstance(p, tuple)).decode("utf-8", "ignore")
                if re.search(r"\bunsubscribe\b|\bremove me\b|\bstop emailing\b|\bnot interested\b", blob, re.I):
                    unsub = "unsubscribe" in blob.lower() or "remove me" in blob.lower() \
                            or "stop emailing" in blob.lower()
            if unsub:
                set_status(db, domain, "unsubscribed")
                res["unsubscribed"] += 1
                W.log(f"  UNSUBSCRIBED {domain}")
            elif status == "emailed":
                set_status(db, domain, "replied")
                res["replied"] += 1
                W.log(f"  REPLIED {domain}")
        # bounces
        typ, data = im.search(None, "SINCE", since, "FROM", '"mailer-daemon"')
        ids = data[0].split() if typ == "OK" and data and data[0] else []
        addr_to_domain = {a.lower(): d for d, a, _ in contacted if a}
        for mid in ids[-200:]:
            typ, msgdata = im.fetch(mid, "(BODY.PEEK[TEXT]<0.6000>)")
            blob = b" ".join(p[1] for p in msgdata if isinstance(p, tuple)).decode("utf-8", "ignore").lower()
            for a, d in addr_to_domain.items():
                if a in blob:
                    set_status(db, d, "bounced")
                    res["bounced"] += 1
                    W.log(f"  BOUNCED {a}")
    finally:
        try:
            im.logout()
        except Exception:
            pass
    W.progress(phase="inbox", done=len(contacted), total=len(contacted), label="Inbox checked")
    W.log(f"Inbox: {res['replied']} new replies, {res['unsubscribed']} unsubscribes, "
          f"{res['bounced']} bounces.")
    return res
