"""Connection to nadevelopers.com (WordPress + the "NA Lead Bot Bridge" plugin).

What it does:
- publishes a private, hidden-from-Google audit page for a lead and puts the link
  in the first email
- tells you when a business opens its audit page (the hottest signal there is)
- brings website contact-form inquiries into the app
- uses your real projects, client reviews and the announcement-bar offer in emails
- adds a draft project on the site when you mark a deal as Won

It signs in with a WordPress Application Password (Users > Profile >
Application Passwords). The password is stored encrypted.
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import os
import re
import time

import requests

import wixbot as W

DEFAULTS = {
    "url": "https://nadevelopers.com",
    "user": "",
    "enabled": False,
    "audit_pages": True,      # link to a free audit page in the first email
    "audit_days": 60,         # how long audit pages stay up
    "use_offer": True,        # announcement bar text becomes the email offer
    "use_portfolio": True,    # real projects + reviews in emails
    "inquiries": True,        # contact-form inquiries come into the app
    "won_projects": True,     # Won -> draft project on the site
}
AUDIT_LINE = "Your free website review is ready: {url}"
FREE_MAIL = re.compile(r"@(gmail|googlemail|yahoo|ymail|hotmail|outlook|icloud|me|mac|aol|live|msn|proton|"
                       r"protonmail|pm|zoho|gmx|yandex|mail|inbox|hey|fastmail|tutanota|rocketmail|att|comcast|"
                       r"verizon|sbcglobal)\.", re.I)


def settings(cfg) -> dict:
    s = dict(DEFAULTS)
    s.update(cfg.get("website", {}) or {})
    return s


def _password(cfg) -> str:
    import security
    return security.get_secret(cfg, "wp_app_password")


def enabled(cfg) -> bool:
    s = settings(cfg)
    return bool(s["enabled"] and s["url"] and s["user"] and _password(cfg))


def _call(cfg, method: str, path: str, payload=None, params=None, timeout: int = 60):
    s = settings(cfg)
    base = s["url"].rstrip("/")
    # ?rest_route= works whatever the permalink settings are.
    p = {"rest_route": "/nalb/v1" + path}
    p.update(params or {})
    auth = (s["user"], _password(cfg).replace(" ", ""))
    try:
        r = requests.request(method, base + "/", params=p, json=payload, auth=auth, timeout=timeout,
                             headers={"User-Agent": "WixLeadBot/" + W.VERSION,
                                      # many hosts drop "Authorization"; the plugin also reads this one
                                      "X-NALB-Auth": base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()})
    except requests.RequestException as e:
        raise RuntimeError(f"Couldn't reach {base}: {e}") from None
    if r.status_code in (401, 403):
        try:
            code = r.json().get("code", "")
        except ValueError:
            code = ""
        if code in ("incorrect_password", "invalid_username", "invalid_email"):
            raise RuntimeError("Wrong username or Application Password. In WordPress the username is the one "
                               "shown top-right ('Howdy, admin' means admin). Paste the password again.")
        raise RuntimeError("The website didn't accept the sign-in. Update the NA Lead Bot Bridge plugin to "
                           "1.0.1 (Plugins > Add New > Upload, then 'Replace current with uploaded').")
    if r.status_code == 404:
        raise RuntimeError("The NA Lead Bot Bridge plugin isn't active on the website.")
    if r.status_code >= 400:
        try:
            msg = r.json().get("message", "")
        except ValueError:
            msg = r.text[:200]
        raise RuntimeError(f"Website error {r.status_code}: {msg}")
    try:
        return r.json()
    except ValueError:
        raise RuntimeError("The website answered with something unexpected (is a security plugin "
                           "blocking the REST API?).") from None


def test(cfg) -> str:
    j = _call(cfg, "GET", "/ping")
    return (f"Connected to {j.get('site')} as {j.get('user')}. Plugin {j.get('version')}, "
            f"{j.get('audits', 0)} audit pages so far.")


# ---------------------------------------------------------------------------
# Audit pages
# ---------------------------------------------------------------------------
def audit_url(db: W.DB, domain: str) -> str:
    return db.get_kv(f"audit_url:{domain}", "") or ""


def _b64(path: str | None, max_side: int = 1400) -> str:
    if not path or not os.path.exists(path):
        return ""
    try:
        from PIL import Image
        import io
        im = Image.open(path)
        im.thumbnail((max_side, max_side * 3))
        if im.mode not in ("RGB", "L"):
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.convert("RGBA").split()[-1])
            im = bg
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()


def publish_audit(db: W.DB, cfg, lead: dict, run_audit_if_missing: bool = True) -> str:
    """Create or update the lead's audit page. Returns its address."""
    import audit as A
    import outreach as O
    s = O.settings(cfg)
    a = A.get(db, lead["domain"])
    if not a and run_audit_if_missing:
        import security
        a = A.run(db, lead, security.get_secret(cfg, "psi_key"), s)
    if not a:
        raise RuntimeError("No audit yet for this business.")
    name = (lead.get("name") or lead.get("site_name") or lead["domain"]).strip()
    site = re.sub(r"^https?://(www\.)?", "", lead.get("final_url") or lead.get("website") or lead["domain"]).rstrip("/")
    fixes = [tip for _, tip in O._issue_points(lead)][:6]
    reviews = [{"text": t, "by": b} for t, b in (O.settings(cfg).get("testimonials") or [])[:3]]
    wa = re.sub(r"\D", "", s.get("whatsapp") or "")
    data = {
        "business": name, "domain": site, "city": lead.get("city") or "",
        "overall": a.get("overall"),
        "scores": a.get("psi", {}).get("scores", {}),
        "checks": [{"group": c.get("group"), "ok": bool(c.get("ok")), "text": c.get("text")}
                   for c in a.get("checks", [])],
        "fixes": fixes,
        "calendly": s.get("calendly"),
        "whatsapp_link": f"https://wa.me/{wa}" if wa else "",
        "testimonials": reviews,
    }
    payload = {
        "domain": lead["domain"], "data": data,
        "expires_days": int(settings(cfg)["audit_days"]),
        "screenshot_b64": _b64(a.get("screenshot"), 600),
        "mockup_b64": _b64(A.mockup_file(lead["domain"])),
    }
    j = _call(cfg, "POST", "/audit", payload, timeout=120)
    url = j.get("url", "")
    if url:
        db.set_kv(f"audit_url:{lead['domain']}", url)
        W.log(f"  Audit page ready for {name}: {url}")
    return url


def add_link_to_draft(db: W.DB, domain: str, url: str) -> bool:
    """Put the audit link into the lead's first email if it isn't there yet."""
    rows = db.q("SELECT id, body FROM messages WHERE domain=? AND step=1 AND status IN ('draft','approved')",
                (domain,))
    changed = False
    for mid, body in rows:
        if url in body:
            continue
        line = AUDIT_LINE.format(url=url)
        body = re.sub(r"\n*Your free website review is ready: \S+\n*", "\n\n", body)
        marker = re.search(r"\n\n(Would a free 15-minute call|Would you like|Worth a quick)", body)
        if marker:
            body = body[:marker.start()] + "\n\n" + line + body[marker.start():]
        else:
            parts = body.split("\n\n")
            body = "\n\n".join(parts[:2] + [line] + parts[2:])
        db.x("UPDATE messages SET body=? WHERE id=?", (body, mid))
        changed = True
    return changed


def publish_for_drafts(db: W.DB, cfg) -> int:
    """Audit pages for every lead whose first email is waiting to go out."""
    doms = [d for (d,) in db.q("SELECT DISTINCT domain FROM messages WHERE step=1 AND status IN ('draft','approved')")]
    n = 0
    for i, d in enumerate(doms):
        W.wait_if_paused()
        if W.STOP.is_set():
            break
        lead = next(iter(db.lead_records("s.domain=?", (d,))), None)
        if not lead:
            continue
        W.progress(phase="audit", done=i, total=len(doms), label=f"Audit page for {lead.get('name') or d}")
        try:
            url = audit_url(db, d) or publish_audit(db, cfg, lead)
            if url and add_link_to_draft(db, d, url):
                n += 1
        except Exception as e:
            W.log(f"  Audit page failed for {d}: {e}")
    W.progress(phase="audit", done=len(doms), total=len(doms), label="Audit pages")
    return n


# ---------------------------------------------------------------------------
# Who opened their audit page
# ---------------------------------------------------------------------------
def check_views(db: W.DB, cfg) -> list[dict]:
    """New views since last time. Adds a 'they're looking' task for each."""
    import outreach as O
    O.init(db)
    since = int(db.get_kv("wp_seen_since", "0") or 0)
    j = _call(cfg, "GET", "/seen", params={"since": since})
    news = []
    for it in j.get("items", []):
        d = it.get("domain")
        if not d:
            continue
        old = json.loads(db.get_kv(f"views:{d}", "{}") or "{}")
        db.set_kv(f"views:{d}", json.dumps(it))
        if int(it.get("views", 0)) > int(old.get("views", 0)) or it.get("last", 0) > old.get("last", 0):
            news.append(it)
            today = dt.date.today().isoformat()
            db.x("INSERT OR IGNORE INTO tasks (domain, kind, due) VALUES (?,?,?)", (d, "viewed", today))
            db.x("UPDATE tasks SET done=0, due=? WHERE domain=? AND kind='viewed'", (today, d))
    db.set_kv("wp_seen_since", str(j.get("now", int(time.time())) - 5))
    return news


def views(db: W.DB, domain: str) -> dict:
    return json.loads(db.get_kv(f"views:{domain}", "{}") or "{}")


# ---------------------------------------------------------------------------
# Website inquiries
# ---------------------------------------------------------------------------
SPAM_RE = re.compile(
    r"\bseo\b|backlink|guest post|rank (your|on)|first page of google|more traffic|increase (your )?traffic|"
    r"web ?traffic|crypto|bitcoin|forex|loan|casino|viagra|cbd|investment opportunit|lead generation service|"
    r"we (can|will) (build|design|redesign) your|app development|outsourc|offshore|virtual assistant|"
    r"unsubscribe|opt.?out|whatsapp me|telegram|marketing services|press release|domain (name )?(for sale|expir)|"
    r"buy (followers|likes)|youtube (views|subscribers)|instagram followers|\$\d+ (per|/) ?month|"
    # people selling their own services to you
    r"\bwe (offer|provide|specialize|specialise|help (businesses|companies|agencies))|our (team|agency|company|"
    r"services|experts)|\bi('m| am) an? (expert|freelancer|developer|designer|seo|digital|marketing|web)|"
    r"hire (me|us|our)|white.?label|partner with you|appointment setting|cold (email|calling) service|"
    r"would you be (interested|open) (in|to) (our|a partnership|working with us)|free (trial|audit) of our",
    re.I)


def is_spam_inquiry(it: dict) -> bool:
    """Contact-form spam: sales pitches for SEO/marketing/dev services, crypto, link drops."""
    text = " ".join(str(it.get(k) or "") for k in ("title", "name", "message", "website"))
    links = len(re.findall(r"https?://|www\.", text))
    return bool(SPAM_RE.search(text)) or links >= 3 or (len((it.get("message") or "").strip()) < 15
                                                     and not it.get("website"))


def import_inquiries(db: W.DB, cfg) -> int:
    import ai
    import outreach as O
    O.init(db)
    ai.init(db)
    if db.get_kv("inq_cleanup_v3", "") != "1":
        # earlier versions counted inquiries as lead replies: undo that
        for key, kind, subj, snip in db.q("SELECT domain, kind, subject, snippet FROM replies "
                                          "WHERE snippet LIKE '[Website inquiry%'"):
            if not db.q("SELECT 1 FROM messages WHERE domain=? AND status='sent'", (key,)):
                db.x("DELETE FROM outreach WHERE domain=?", (key,))
            spam = is_spam_inquiry({"title": subj, "message": snip.split("] ", 1)[-1]})
            db.x("UPDATE replies SET kind=?, handled=? WHERE domain=? AND snippet LIKE '[Website inquiry%'",
                 ("spam" if spam else "inquiry", 1 if spam else 0, key))
            if spam:
                db.x("UPDATE tasks SET done=1 WHERE domain=? AND kind='inquiry'", (key,))
        db.set_kv("inq_cleanup_v3", "1")
    if db.get_kv("inq_cleanup_v1", "") != "1":
        # inquiries from personal mailboxes (proton.me, gmail...) are not company websites
        for (d,) in db.q("SELECT DISTINCT domain FROM businesses WHERE category='inquiry'"):
            if d and FREE_MAIL.search("@" + d):
                db.x("DELETE FROM businesses WHERE category='inquiry' AND domain=?", (d,))
        db.set_kv("inq_cleanup_v1", "1")
    after = int(db.get_kv("wp_inquiry_after", "0") or 0)
    items = _call(cfg, "GET", "/inquiries", params={"after_id": after})
    n = 0
    for it in items:
        after = max(after, int(it.get("id") or 0))
        email_addr = (it.get("email") or "").strip().lower()
        site = (it.get("website") or "").strip()
        if not site and email_addr and not FREE_MAIL.search(email_addr):
            site = email_addr.split("@")[-1]
        domain = W.domain_of(W.normalise_url(site)) if site else ""
        key = domain or email_addr or f"inquiry-{it.get('id')}"
        W.add_captured([{"name": it.get("name") or key, "website": site, "category": "inquiry",
                         "found_on": "nadevelopers.com contact form"}], db) if domain else None
        if domain and not db.site_checked(domain, True):
            try:
                db.save_site(W.check_site(W.normalise_url(site), W.PoliteFetcher()))
            except Exception:
                pass
        snippet = f"[Website inquiry · {it.get('type') or 'contact form'}] {it.get('message') or ''}".strip()
        spam = is_spam_inquiry(it)
        # Inquiries are kept apart from lead replies: they never change a lead's status
        # or the "Replied" numbers.
        db.x("INSERT OR IGNORE INTO replies (domain, from_addr, subject, snippet, kind, received_at, handled)"
             " VALUES (?,?,?,?,?,?,?)",
             (key, email_addr, it.get("title") or "Website inquiry", snippet[:2000],
              "spam" if spam else "inquiry", it.get("date") or W.now(), 1 if spam else 0))
        if spam:
            W.log(f"  Website inquiry from {email_addr or key} looks like spam: filed away, no task.")
            continue
        db.x("INSERT OR IGNORE INTO tasks (domain, kind, due) VALUES (?,?,?)",
             (key, "inquiry", dt.date.today().isoformat()))
        n += 1
    db.set_kv("wp_inquiry_after", str(after))
    if n:
        W.log(f"  {n} new inquir{'y' if n == 1 else 'ies'} from your website.")
    return n


# ---------------------------------------------------------------------------
# Projects, reviews and the offer
# ---------------------------------------------------------------------------
def sync(db: W.DB, cfg) -> str:
    """Pull projects, reviews and the offer from the site into the app's settings."""
    s = settings(cfg)
    parts = []
    if s["use_portfolio"]:
        j = _call(cfg, "GET", "/portfolio")
        db.set_kv("wp_portfolio", json.dumps(j))
        reviews = [[t["text"], t["by"] + ", website client"] for t in j.get("testimonials", [])
                   if t.get("text") and 30 <= len(t["text"]) <= 220]
        if reviews:
            out = dict(cfg.get("outreach", {}) or {})
            out["testimonials"] = reviews
            cfg.set("outreach", out)
        parts.append(f"{len(j.get('projects', []))} projects, {len(reviews)} reviews")
    if s["use_offer"]:
        o = _call(cfg, "GET", "/offer")
        out = dict(cfg.get("outreach", {}) or {})
        text = (o.get("text") or "").strip() if o.get("enabled") else ""
        if text != out.get("offer", ""):
            out["offer"] = text
            out["offer_until"] = ""
            cfg.set("outreach", out)
        parts.append("offer: " + (text.rstrip(".") or "none (announcement bar is off)"))
    cfg.save()
    db.set_kv("wp_synced_at", W.now())
    return "Synced " + "; ".join(parts) + "."


def _kind_of(about: str) -> str:
    m = re.match(r"\s*an?\s+(.+?)\s+(website|online store|site|store)\b", about or "", re.I)
    return m.group(1).strip().capitalize() if m else ""


def work_for(db: W.DB, category: str, n: int = 3) -> list[list[str]]:
    """Up to n projects with pictures, ones matching the lead's trade first."""
    try:
        projects = json.loads(db.get_kv("wp_portfolio", "{}") or "{}").get("projects", [])
    except ValueError:
        return []
    projects = [p for p in projects if p.get("image")]
    if not projects:
        return []
    cat = W.load_categories().get(category or "", {})
    words = set(re.findall(r"[a-z]{4,}", " ".join([category or "", cat.get("label", ""), cat.get("short", "")]).lower()))
    words = {w.rstrip("s") for w in words} - {"services", "service", "store", "shop", "business"}

    def score(p):
        text = (p.get("title", "") + " " + p.get("about", "")).lower()
        return sum(w in text for w in words)
    ranked = sorted(projects, key=score, reverse=True)
    return [[p["title"], _kind_of(p.get("about", "")) or "Website", p["image"]] for p in ranked[:n]]


# ---------------------------------------------------------------------------
# Won -> draft project
# ---------------------------------------------------------------------------
def won_project(db: W.DB, cfg, domain: str) -> str:
    lead = next(iter(db.lead_records("s.domain=?", (domain,))), None) or {"domain": domain}
    cat = W.load_categories().get(lead.get("category") or "", {})
    kind = (cat.get("label") or "business").lower()
    title = (lead.get("name") or domain).strip()
    j = _call(cfg, "POST", "/project", {
        "title": title, "platform": "Wix",
        "about": f"A {kind} website designed and built by NA Developers.",
        "url": lead.get("final_url") or lead.get("website") or "",
        "note": "Draft added by Wix Lead Bot when the deal was marked Won. Add photos and the live link.",
    })
    W.log(f"  Draft project for {title} added on your website.")
    return j.get("edit", "")


def run_background(db: W.DB, cfg) -> dict:
    """What the app does every few minutes when the website is connected."""
    out = {"views": [], "inquiries": 0}
    if not enabled(cfg):
        return out
    s = settings(cfg)
    try:
        out["views"] = check_views(db, cfg)
    except Exception as e:
        out["error"] = str(e)
    if s["inquiries"]:
        try:
            out["inquiries"] = import_inquiries(db, cfg)
        except Exception as e:
            out["error"] = str(e)
    last = db.get_kv("wp_synced_at", "")
    if not last or last[:10] != dt.date.today().isoformat():
        try:
            sync(db, cfg)
        except Exception as e:
            out["error"] = str(e)
    return out
