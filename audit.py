"""Full website audit: Google PageSpeed (speed, SEO, accessibility, best
practices + a phone screenshot) plus our own design / SEO / business checks.
Saves results in the database and makes a one-page HTML report with your logo.
"""
from __future__ import annotations

import base64
import datetime as dt
import html
import json
import os
import re

import requests

import wixbot as W

PSI_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
CATEGORIES = [("performance", "Speed"), ("seo", "SEO"), ("accessibility", "Design & readability"),
              ("best-practices", "Best practices")]
SCHEMA = """
CREATE TABLE IF NOT EXISTS audits (domain TEXT PRIMARY KEY, data TEXT, created_at TEXT);
"""
FREE_MAIL = ("gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", "icloud.com",
             "live.com", "msn.com", "ymail.com", "comcast.net", "att.net")


def init(db: W.DB) -> None:
    with db.lock:
        db.conn.executescript(SCHEMA)
        db.conn.commit()


def audit_dir() -> str:
    d = os.path.join(W.HERE, "output", "audits")
    os.makedirs(d, exist_ok=True)
    return d


def safe_name(domain: str) -> str:
    return re.sub(r"[^a-z0-9.-]+", "_", domain.lower())


def get(db: W.DB, domain: str) -> dict | None:
    init(db)
    r = db.q("SELECT data FROM audits WHERE domain=?", (domain,))
    return json.loads(r[0][0]) if r else None


# ---------------------------------------------------------------------------
# Google PageSpeed Insights (free)
# ---------------------------------------------------------------------------
def pagespeed(url: str, key: str = "") -> dict:
    params = [("url", url), ("strategy", "mobile")] + [("category", c) for c, _ in CATEGORIES]
    if key:
        params.append(("key", key))
    last = ""
    for attempt in range(3):
        try:
            r = requests.get(PSI_URL, params=params, timeout=120,
                             headers={"User-Agent": W.USER_AGENT})
        except requests.RequestException as e:
            last = str(e)
            continue
        if r.status_code == 200:
            break
        last = f"HTTP {r.status_code}"
        if r.status_code == 429:
            raise RuntimeError("Google PageSpeed daily limit reached. Add a free PageSpeed key in "
                               "Settings > AI & audit.")
        if r.status_code in (400, 500):
            try:
                last = r.json().get("error", {}).get("message", last)
            except ValueError:
                pass
            break
    else:
        raise RuntimeError(f"PageSpeed didn't answer ({last})")
    if r.status_code != 200:
        raise RuntimeError(f"PageSpeed couldn't test this site ({last[:150]})")
    lh = r.json().get("lighthouseResult", {})
    audits = lh.get("audits", {})
    out = {"scores": {}, "failing": {}, "metrics": {}, "screenshot": ""}
    for cid, label in CATEGORIES:
        cat = lh.get("categories", {}).get(cid) or {}
        if cat.get("score") is not None:
            out["scores"][cid] = round(cat["score"] * 100)
        fails = []
        for ref in sorted(cat.get("auditRefs", []), key=lambda a: -a.get("weight", 0)):
            a = audits.get(ref.get("id"), {})
            sc = a.get("score")
            if sc is None or a.get("scoreDisplayMode") in ("notApplicable", "manual", "informative"):
                continue
            if sc < 0.9:
                fails.append(re.sub(r"\s*\[[^\]]+\]\([^)]+\)\.?", "", a.get("title", "")).strip())
        out["failing"][cid] = fails[:6]
    for mid, label in (("largest-contentful-paint", "Main content shows after"),
                       ("first-contentful-paint", "First text shows after"),
                       ("speed-index", "Speed index"), ("cumulative-layout-shift", "Layout shift"),
                       ("total-blocking-time", "Blocked for")):
        if audits.get(mid, {}).get("displayValue"):
            out["metrics"][label] = audits[mid]["displayValue"]
    shot = (audits.get("final-screenshot", {}).get("details") or {}).get("data", "")
    if shot.startswith("data:image"):
        out["screenshot"] = shot
    return out


# ---------------------------------------------------------------------------
# Our own checks (read the homepage)
# ---------------------------------------------------------------------------
def page_checks(html_text: str, final_url: str, lead: dict, session) -> list[dict]:
    """[{"group", "ok", "text"}] where group is design / seo / business."""
    h = html_text
    low = h.lower()
    text = W.visible_text(h)
    checks = []

    def add(group, ok, good, bad):
        checks.append({"group": group, "ok": bool(ok), "text": good if ok else bad})

    imgs = re.findall(r"<img\b[^>]*>", h, re.I)
    no_alt = [i for i in imgs if not re.search(r'\balt=["\'][^"\']+', i, re.I)]
    title = (re.search(r"<title[^>]*>(.*?)</title>", h, re.I | re.S) or [None, ""])[1].strip()
    desc_m = W.META_DESC_RE.search(h) or W.META_DESC_RE2.search(h)
    h1s = re.findall(r"<h1\b", h, re.I)
    # --- SEO
    add("seo", 15 <= len(title) <= 65 and title.lower() not in ("home", "my site", "home | my site"),
        f"Google title looks good: “{title[:70]}”",
        f"Google title is weak: “{title[:70] or 'missing'}”. It should say what you do and where.")
    add("seo", desc_m and 70 <= len(desc_m.group(1)) <= 170, "Has a good Google description.",
        "Google description is missing or too short, so Google picks random text.")
    add("seo", len(h1s) == 1, "Has one clear main heading.",
        f"Homepage has {len(h1s)} main headings (should be exactly 1).")
    add("seo", not imgs or len(no_alt) <= len(imgs) * 0.2,
        "Images have descriptions for Google.",
        f"{len(no_alt)} of {len(imgs)} images have no description (alt text), so Google can't read them.")
    add("seo", "localbusiness" in low or ('"@type"' in low and '"address"' in low),
        "Tells Google its business details (address, hours).",
        "Doesn't give Google structured business details (address, hours, phone).")
    try:
        from urllib.parse import urlparse
        pu = urlparse(final_url)
        sm = session.get(f"{pu.scheme}://{pu.netloc}/sitemap.xml", timeout=15)
        head = sm.text[:3000] if sm.status_code == 200 else ""
        add("seo", "<urlset" in head or "<sitemapindex" in head,
            "Has a sitemap for Google.", "No sitemap found, so Google may miss pages.")
    except requests.RequestException:
        pass
    add("seo", not re.search(r'<meta[^>]+name=["\']robots["\'][^>]+noindex', h, re.I),
        "Google is allowed to show the homepage.", "Homepage is hidden from Google (noindex)!")
    # --- design / experience
    add("design", 'name="viewport"' in low or "name='viewport'" in low, "Set up for phones.",
        "Not set up for phones (no mobile viewport).")
    add("design", len(text.split()) >= 300, "Homepage has enough content.",
        f"Homepage is thin ({len(text.split())} words), so visitors don't see what you offer.")
    yr = lead.get("copyright_year")
    add("design", not yr or int(yr) >= dt.date.today().year - 1, "Footer year is current.",
        f"Footer still says © {yr}, so the site looks abandoned.")
    add("design", final_url.startswith("https://"), "Secure (https).", "Not secure (no https).")
    # --- business / digital
    add("business", "tel:" in low, "Phone number can be tapped to call.",
        "No tap-to-call phone link, which loses calls from mobile visitors.")
    add("business", "<form" in low or "wix-forms" in low or "contact-form" in low,
        "Has a contact form.", "No contact form on the homepage.")
    add("business", bool(lead.get("has_booking")), "Has online booking.",
        "No online booking button, so customers can't book from their phone.")
    add("business", re.search(r"review|testimonial|what our (clients|customers|patients) say|stars?",
                              text, re.I), "Shows reviews or testimonials.",
        "No reviews or testimonials on the homepage, which are big for trust.")
    add("business", "google.com/maps" in low or "maps.googleapis" in low or "wix-google-map" in low,
        "Shows a map / location.", "No map, so it's harder for locals to find you.")
    add("business", bool(lead.get("socials")), "Links to social media.", "No social media links.")
    add("business", "googletagmanager.com" in low or "gtag(" in low or "google-analytics" in low,
        "Has Google Analytics (tracks visitors).",
        "No Google Analytics, so they can't see how many visitors they get.")
    add("business", "fbq(" in low or "connect.facebook.net" in low, "Has Facebook/Meta Pixel for ads.",
        "No Facebook/Meta Pixel, so they can't retarget visitors with ads.")
    add("business", re.search(r"subscribe|newsletter|join our (list|mailing)", text, re.I),
        "Collects emails (newsletter).", "Doesn't collect visitor emails (no newsletter signup).")
    emails = [e for e in (lead.get("emails") or "").split(";") if e.strip()]
    if emails:
        free = all(e.strip().split("@")[-1] in FREE_MAIL for e in emails)
        add("business", not free, "Uses a professional email address.",
            f"Uses a free email ({emails[0].strip()}) instead of one on their own domain.")
    return checks


def run(db: W.DB, lead: dict, psi_key: str = "", settings: dict | None = None) -> dict:
    """Audit one lead's website. Returns the audit dict (also saved)."""
    init(db)
    url = lead.get("final_url") or W.normalise_url(lead.get("website") or "")
    W.log(f"  Auditing {url} ...")
    data = {"url": url, "created_at": W.now(), "psi_error": ""}
    try:
        data["psi"] = pagespeed(url, psi_key)
    except RuntimeError as e:
        data["psi"] = {}
        data["psi_error"] = str(e)
        W.log(f"    PageSpeed: {e}")
    s = requests.Session()
    s.headers["User-Agent"] = W.USER_AGENT
    try:
        r = s.get(url, timeout=30)
        data["checks"] = page_checks(r.text or "", r.url, lead, s)
    except requests.RequestException as e:
        data["checks"] = []
        W.log(f"    Couldn't open the site: {e}")
    shot = data.get("psi", {}).pop("screenshot", "")
    if shot:
        path = os.path.join(audit_dir(), safe_name(lead["domain"]) + ".jpg")
        with open(path, "wb") as f:
            f.write(base64.b64decode(shot.split(",", 1)[1]))
        data["screenshot"] = path
    sc = data.get("psi", {}).get("scores", {})
    checks = data.get("checks", [])
    passed = sum(c["ok"] for c in checks)
    data["overall"] = round(((sum(sc.values()) / len(sc)) if sc else 50) * 0.6 +
                            (100 * passed / len(checks) if checks else 50) * 0.4)
    db.x("INSERT OR REPLACE INTO audits VALUES (?,?,?)", (lead["domain"], json.dumps(data), W.now()))
    data["report"] = write_report(lead, data, settings)
    db.x("INSERT OR REPLACE INTO audits VALUES (?,?,?)", (lead["domain"], json.dumps(data), W.now()))
    W.log(f"    Done: overall {data['overall']}/100")
    return data


def run_many(db: W.DB, leads: list[dict], psi_key: str = "", settings: dict | None = None) -> int:
    n = 0
    for i, lead in enumerate(leads):
        W.wait_if_paused()
        if W.STOP.is_set():
            break
        W.progress(phase="audit", done=i, total=len(leads),
                   label=f"Auditing {lead.get('name') or lead['domain']}")
        try:
            run(db, lead, psi_key, settings)
            n += 1
        except Exception as e:  # keep going with the next site
            W.log(f"    Audit failed for {lead['domain']}: {e}")
        W.progress(phase="audit", done=i + 1, total=len(leads), label="Auditing")
    return n


# ---------------------------------------------------------------------------
# Plain-English findings for emails / AI
# ---------------------------------------------------------------------------
def top_findings(a: dict | None, limit: int = 6) -> list[str]:
    if not a:
        return []
    out = []
    perf = a.get("psi", {}).get("scores", {}).get("performance")
    lcp = a.get("psi", {}).get("metrics", {}).get("Main content shows after")
    if perf is not None and perf < 50:
        out.append(f"On a phone the site scores {perf}/100 for speed"
                   + (f" and takes {lcp} to show the main content" if lcp else ""))
    # most persuasive first: things an owner instantly understands
    priority = ["Google title", "online booking", "Footer still says", "hidden from Google", "Not set up for phones",
                "reviews or testimonials", "tap-to-call", "contact form", "Homepage is thin", "Not secure",
                "Google description", "free email", "No map", "structured business", "sitemap", "images have no",
                "main headings", "social media", "Google Analytics", "Pixel", "newsletter"]

    def rank(c):
        return next((i for i, k in enumerate(priority) if k.lower() in c["text"].lower()), len(priority))
    for c in sorted([c for c in a.get("checks", []) if not c["ok"]], key=rank):
        out.append(c["text"])
    return out[:limit]


# ---------------------------------------------------------------------------
# Report (HTML, print to PDF from the browser)
# ---------------------------------------------------------------------------
def _ring(score, label):
    if score is None:
        return ""
    col = "#1F9D55" if score >= 90 else "#F08C2E" if score >= 50 else "#E8222B"
    return (f'<div class="ring"><svg viewBox="0 0 36 36"><path d="M18 2a16 16 0 1 1 0 32a16 16 0 1 1 0-32" '
            f'fill="none" stroke="#E9EEF3" stroke-width="3.5"/><path d="M18 2a16 16 0 1 1 0 32a16 16 0 1 1 0-32" '
            f'fill="none" stroke="{col}" stroke-width="3.5" stroke-dasharray="{score},100" stroke-linecap="round"/>'
            f'<text x="18" y="21" text-anchor="middle">{score}</text></svg><span>{html.escape(label)}</span></div>')


def write_report(lead: dict, a: dict, s: dict | None = None) -> str:
    import outreach as O
    s = s or O.DEFAULTS
    name = lead.get("name") or lead.get("site_name") or lead["domain"]
    logo = os.path.join(W.BUNDLED, "assets", "logo_login.png")
    logo_b64 = base64.b64encode(open(logo, "rb").read()).decode() if os.path.exists(logo) else ""
    shot = ""
    if a.get("screenshot") and os.path.exists(a["screenshot"]):
        shot = base64.b64encode(open(a["screenshot"], "rb").read()).decode()
    sc = a.get("psi", {}).get("scores", {})
    rings = "".join(_ring(sc.get(c), l) for c, l in CATEGORIES)
    groups = {"design": "Design & experience", "seo": "Google / SEO", "business": "Business & marketing"}
    sections = ""
    for g, title in groups.items():
        items = [c for c in a.get("checks", []) if c["group"] == g]
        if not items:
            continue
        lis = "".join(f'<li class="{"ok" if c["ok"] else "bad"}">{html.escape(c["text"])}</li>'
                      for c in sorted(items, key=lambda c: c["ok"]))
        sections += f"<h3>{title}</h3><ul>{lis}</ul>"
    fails = ""
    for cid, label in CATEGORIES:
        f = a.get("psi", {}).get("failing", {}).get(cid) or []
        if f:
            fails += f"<p><b>{label}:</b> " + "; ".join(html.escape(x) for x in f[:4]) + "</p>"
    metrics = " · ".join(f"{html.escape(k)} {html.escape(v)}" for k, v in a.get("psi", {}).get("metrics", {}).items())
    page = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Website audit - {html.escape(name)}</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;color:#16212D;max-width:900px;margin:30px auto;padding:0 24px}}
header{{display:flex;justify-content:space-between;align-items:center;border-bottom:4px solid #1E91A8;padding-bottom:12px}}
header img{{height:54px}} h1{{font-size:26px;margin:22px 0 2px}} .sub{{color:#6B7785}}
.top{{display:flex;gap:28px;align-items:flex-start;margin-top:18px}} .shot img{{width:230px;border:1px solid #E2E7EE;border-radius:10px}}
.rings{{display:flex;flex-wrap:wrap;gap:14px}} .ring{{width:110px;text-align:center}} .ring svg{{width:84px}}
.ring text{{font-size:10px;font-weight:700;fill:#16212D}} .ring span{{display:block;font-size:12px;color:#6B7785}}
.overall{{font-size:15px;margin:10px 0}} h3{{margin:22px 0 6px;color:#167487}} ul{{list-style:none;padding:0;margin:0}}
li{{padding:6px 0 6px 26px;border-bottom:1px solid #EEF2F6;position:relative}}
li.bad:before{{content:"✗";color:#E8222B;position:absolute;left:4px;font-weight:700}}
li.ok:before{{content:"✓";color:#1F9D55;position:absolute;left:4px;font-weight:700}}
.cta{{margin-top:26px;background:#16212D;color:#fff;padding:18px 22px;border-radius:10px}} .cta a{{color:#7FD3E6}}
.small{{font-size:12px;color:#6B7785}} @media print{{.cta{{-webkit-print-color-adjust:exact}}}}</style></head><body>
<header>{'<img src="data:image/png;base64,' + logo_b64 + '">' if logo_b64 else '<b>NA Developers</b>'}
<div class="small">Website audit · {dt.date.today():%B %d, %Y}</div></header>
<h1>{html.escape(name)}</h1><div class="sub">{html.escape(a.get('url', ''))}</div>
<div class="top">{'<div class="shot"><img src="data:image/jpeg;base64,' + shot + '"><div class="small">How it looks on a phone</div></div>' if shot else ''}
<div><div class="overall">Overall score: <b>{a.get('overall', '?')}/100</b></div><div class="rings">{rings}</div>
<p class="small">{metrics}</p>{('<p class="small">PageSpeed: ' + html.escape(a['psi_error']) + '</p>') if a.get('psi_error') else ''}</div></div>
{sections}{('<h3>Technical details from Google</h3>' + fails) if fails else ''}
<div class="cta"><b>Want these fixed?</b> {html.escape(s.get('company', 'NA Developers'))} is a Wix Legend Partner studio.
Book a free 15-minute call: <a href="{html.escape(s.get('calendly', ''))}">{html.escape(s.get('calendly', ''))}</a></div>
<p class="small">Scores from Google PageSpeed Insights (mobile test) and NA Developers checks. Results can vary between runs.</p>
</body></html>"""
    path = os.path.join(audit_dir(), safe_name(lead["domain"]) + ".html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    return path


# ---------------------------------------------------------------------------
# Mockups you made in Gemini, and the one-page call brief
# ---------------------------------------------------------------------------
def mockup_dir() -> str:
    d = os.path.join(W.HERE, "output", "mockups")
    os.makedirs(d, exist_ok=True)
    return d


def mockup_file(domain: str) -> str | None:
    base = os.path.join(mockup_dir(), safe_name(domain))
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        if os.path.exists(base + ext):
            return base + ext
    return None


def save_mockup(domain: str, src: str) -> str:
    import shutil
    ext = os.path.splitext(src)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        raise RuntimeError("Use a PNG, JPG or WEBP image.")
    old = mockup_file(domain)
    if old:
        os.remove(old)
    dst = os.path.join(mockup_dir(), safe_name(domain) + ext)
    shutil.copyfile(src, dst)
    return dst


def call_brief(db: W.DB, cfg, lead: dict) -> str:
    """One page to read before the call: who they are, what's wrong, what to pitch."""
    import ai
    import outreach as O
    s = O.settings(cfg)
    a = get(db, lead["domain"]) or {}
    plan = ai.get_plan(db, lead["domain"]) or {}
    st = O.get_outreach(db, lead["domain"]) or {}
    msgs = O.messages(db, domain=lead["domain"])
    replies = db.q("SELECT kind, snippet, received_at FROM replies WHERE domain=? ORDER BY id DESC",
                   (lead["domain"],)) if db.q("SELECT name FROM sqlite_master WHERE name='replies'") else []
    name = lead.get("name") or lead.get("site_name") or lead["domain"]
    e = html.escape

    def lst(items):
        return "<ul>" + "".join(f"<li>{e(str(x))}</li>" for x in items if x) + "</ul>" if items else "<p>-</p>"
    mock = mockup_file(lead["domain"])
    mock_html = ""
    if mock:
        mime = "png" if mock.endswith(".png") else "jpeg"
        mock_html = (f'<h2>Your mockup</h2><img style="max-width:100%;border:1px solid #E2E7EE;border-radius:8px" '
                     f'src="data:image/{mime};base64,{base64.b64encode(open(mock, "rb").read()).decode()}">')
    sc = a.get("psi", {}).get("scores", {})
    page = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Call brief - {e(name)}</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;color:#16212D;max-width:860px;margin:28px auto;padding:0 22px}}
h1{{margin:0}} h2{{color:#167487;margin:22px 0 6px;font-size:18px}} .sub{{color:#6B7785}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}} .card{{border:1px solid #E2E7EE;border-radius:10px;padding:12px 16px}}
li{{margin:4px 0}} .pill{{display:inline-block;background:#E3F2F5;color:#167487;border-radius:20px;padding:2px 10px;margin-right:6px;font-size:13px}}
blockquote{{border-left:3px solid #1E91A8;margin:6px 0;padding:4px 12px;color:#374151;white-space:pre-wrap}}</style></head><body>
<h1>{e(name)}</h1><div class="sub">{e(lead.get('final_url') or lead.get('website') or '')} ·
{e(', '.join(x for x in (W.city_from_address(lead.get('city') or ''), lead.get('region_name')) if x))}</div>
<p><span class="pill">{e(W.LEVELS[lead.get('level', 'normal')][0])} lead</span>
<span class="pill">{e(O.STATUS_LABELS.get(st.get('status', 'new'), ''))}</span>
<span class="pill">Audit {a.get('overall', '-')}/100</span>
{''.join(f'<span class="pill">{e(dict(CATEGORIES).get(k, k))} {v}</span>' for k, v in sc.items())}</p>
<div class="grid"><div class="card"><b>Contact</b><br>{e((lead.get('emails') or '').replace(';', ', '))}<br>
{e((lead.get('phones') or lead.get('listed_phone') or '').replace(';', ', '))}<br>{e(lead.get('address') or lead.get('street') or '')}</div>
<div class="card"><b>Pitch</b><br>{e(plan.get('angle', 'Run "Gemini plan" in the app for a tailored angle.'))}<br><br>
<b>Package:</b> {e(plan.get('package', 'Pick based on page count: 3-5 pages $350, 5-10 pages $600, store +30%.'))}</div></div>
<h2>Biggest problems to show on screen</h2>{lst(top_findings(a, 8) or [p for p, _ in O._issue_points(lead)])}
<h2>Talking points</h2>{lst(plan.get('talking_points', []))}
<h2>Likely objections</h2>{lst(plan.get('objections', []))}
<h2>What they said</h2>{''.join(f'<p><b>{e(ai.REPLY_KINDS.get(k, k))}</b> ({e((d or '')[:10])})</p><blockquote>{e(t[:800])}</blockquote>' for k, t, d in replies) or '<p>-</p>'}
<h2>Emails sent</h2>{lst([f"{(m['sent_at'] or m['created_at'] or '')[:10]} · {m['status']} · {m['subject']}" for m in msgs])}
<h2>After the call</h2><ul><li>Mark the lead in the app: Proposal sent / Won / Lost.</li>
<li>Booking link for a follow-up: {e(s['calendly'])}</li></ul>
{mock_html}
{('<p><a href="' + e('file:///' + a['report'].replace(os.sep, '/')) + '">Open the full audit report</a></p>') if a.get('report') else ''}
</body></html>"""
    path = os.path.join(audit_dir(), safe_name(lead["domain"]) + "-call-brief.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    return path
