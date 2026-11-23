"""Gemini (Google AI Studio API key, free tier is enough for text):
- an approach plan + custom first email for each business
- sorting replies and drafting an answer
Also: a ready-to-paste mockup prompt for the Gemini app (no API needed).
Nothing here sends anything; drafts still wait for your approval.
"""
from __future__ import annotations

import json
import re
import time

import requests

import wixbot as W

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MODELS = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-2.0-flash"]
GEMINI_APP = "https://gemini.google.com/app"
SCHEMA = """
CREATE TABLE IF NOT EXISTS ai_plans (domain TEXT PRIMARY KEY, data TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT, domain TEXT, from_addr TEXT, subject TEXT,
    snippet TEXT, kind TEXT, received_at TEXT, handled INTEGER DEFAULT 0,
    UNIQUE(domain, subject, snippet)
);
"""
REPLY_KINDS = {"interested": "Interested", "question": "Question / price", "later": "Not now",
               "no": "Not interested", "unsubscribe": "Unsubscribe", "other": "Other"}
_last_call = [0.0]


def init(db: W.DB) -> None:
    with db.lock:
        db.conn.executescript(SCHEMA)
        db.conn.commit()


def _key(cfg) -> str:
    import security
    return security.get_secret(cfg, "gemini_key")


def enabled(cfg) -> bool:
    return bool(_key(cfg))


def ask(cfg, prompt: str, want_json: bool = True, temperature: float = 0.6) -> dict | str:
    """Call Gemini. Paces itself (free tier allows ~10 requests a minute)."""
    key = _key(cfg)
    if not key:
        raise RuntimeError("Add your Gemini API key in Settings > AI & audit first.")
    wait = 6.5 - (time.time() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature}}
    if want_json:
        body["generationConfig"]["responseMimeType"] = "application/json"
    model = (cfg.get("ai", {}) or {}).get("model") or ""
    last = ""
    for m in ([model] if model else []) + MODELS:
        for attempt in range(3):
            _last_call[0] = time.time()
            try:
                r = requests.post(API.format(model=m), params={"key": key}, json=body, timeout=90)
            except requests.RequestException as e:
                last = str(e)
                time.sleep(5)
                continue
            if r.status_code == 200:
                try:
                    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError, ValueError):
                    last = "empty answer"
                    break
                if not want_json:
                    return text.strip()
                try:
                    return json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip()).strip())
                except ValueError:
                    last = "answer wasn't valid JSON"
                    continue
            if r.status_code == 404:
                last = f"model {m} not available"
                break                      # try the next model name
            if r.status_code in (429, 503):
                last = "Gemini is busy or the free limit was reached"
                time.sleep(20 * (attempt + 1))
                continue
            if r.status_code in (400, 401, 403):
                try:
                    msg = r.json().get("error", {}).get("message", "")
                except ValueError:
                    msg = r.text[:200]
                raise RuntimeError(f"Gemini refused the request: {msg}")
            last = f"HTTP {r.status_code}"
    raise RuntimeError(f"Gemini didn't answer ({last}).")


# ---------------------------------------------------------------------------
# Per-business plan + custom email
# ---------------------------------------------------------------------------
def _lead_facts(lead: dict, audit_data: dict | None) -> str:
    import audit as A
    import outreach as O
    cat = W.load_categories().get(lead.get("category") or "", {}).get("label", lead.get("category"))
    findings = A.top_findings(audit_data, 8) or [p for p, _ in O._issue_points(lead)]
    sc = (audit_data or {}).get("psi", {}).get("scores", {})
    return "\n".join([
        f"Business name: {lead.get('name') or lead.get('site_name') or 'unknown'}",
        f"Type of business: {cat}",
        f"Location: {', '.join(x for x in (lead.get('city'), lead.get('region_name')) if x) or 'USA/Canada'}",
        f"Website: {lead.get('final_url') or lead.get('website')}",
        "Website built with: Wix",
        f"Homepage title: {lead.get('title') or ''}",
        f"Description on site: {(lead.get('meta_desc') or '')[:300]}",
        f"Google mobile scores: {json.dumps(sc) if sc else 'not tested'}",
        "Problems found:\n- " + "\n- ".join(findings),
    ])


def make_plan(db: W.DB, cfg, lead: dict, audit_data: dict | None = None) -> dict:
    """Ask Gemini for an approach plan + first email. Saves and returns it."""
    import outreach as O
    init(db)
    s = O.settings(cfg)
    prompt = f"""You help {s['sender_name']} from {s['company']}, a Wix Legend Partner web design studio,
win local businesses in the USA and Canada as website redesign clients. He only takes meetings
booked through {s['calendly']}. Prices: 3-5 pages $350, 5-10 pages $600, online store +30%.
Proof you may use (true): Wix Legend Partner, about 2,000 websites built over 8 years, 24/7 support,
fixed written quote before work starts, free support after launch. Portfolio: {s.get('portfolio_url', '')}

Business facts:
{_lead_facts(lead, audit_data)}

Write JSON with these keys:
"angle": one sentence, the single strongest reason THIS business should care (money, customers, trust),
"package": which package fits and why (one sentence),
"talking_points": 3-5 short bullet strings for the sales call,
"objections": 2-3 likely objections with a one-line answer each, as strings,
"followup_ideas": 3 strings, one fresh idea for each follow-up email (day 3, 7, 14),
"subject": a cold email subject line, under 7 words, specific to them (e.g. "<Business>: 3 quick website fixes"), no clickbait, no emojis, no ALL CAPS,
"email": the cold email body. Rules: 70-120 words, plain text, friendly and specific to this
business, mention 2-3 real problems from the facts in plain English as short bullet lines starting
with "• " (no jargon like "meta" or "LCP"), one sentence of proof, no prices, no attachments
mentioned, one clear call to action: a free 15-minute call at {s['calendly']} or reply "yes" for a
short written plan. Sound like a helpful person, not a marketer. Start with "Hi {{greeting}}," and end with:
{s['sender_name']}
{s['company']} · Wix Legend Partner
{s['website']}
Do not add an unsubscribe line or address (added automatically). Do not invent facts."""
    data = ask(cfg, prompt)
    if not isinstance(data, dict) or not data.get("email"):
        raise RuntimeError("Gemini's answer was missing the email.")
    db.x("INSERT OR REPLACE INTO ai_plans VALUES (?,?,?)",
         (lead["domain"], json.dumps(data), W.now()))
    return data


def get_plan(db: W.DB, domain: str) -> dict | None:
    init(db)
    r = db.q("SELECT data FROM ai_plans WHERE domain=?", (domain,))
    return json.loads(r[0][0]) if r else None


# ---------------------------------------------------------------------------
# Replies
# ---------------------------------------------------------------------------
KEYWORDS = [("unsubscribe", r"\bunsubscribe\b|\bremove me\b|\bstop (emailing|contacting)\b|\btake me off\b"),
            ("no", r"\bnot interested\b|\bno thanks?\b|\bwe'?re (good|all set)\b|\bhappy with\b"),
            ("later", r"\bnot (right )?now\b|\bmaybe later\b|\bnext (month|year|quarter)\b|\bbusy\b"),
            ("question", r"\bhow much\b|\bprice\b|\bcost\b|\bquote\b|\?"),
            ("interested", r"\binterested\b|\bsounds good\b|\blet'?s (talk|chat)\b|\bsure\b|\byes\b|\bcall me\b")]


def classify(cfg, text: str) -> str:
    """Sort a reply. Uses Gemini if set up, otherwise keywords."""
    if enabled(cfg):
        try:
            out = ask(cfg, "Classify this reply to a cold sales email from a web designer. Answer JSON "
                      '{"kind": one of "interested","question","later","no","unsubscribe","other"}.\n\n'
                      f"Reply:\n{text[:2500]}", temperature=0)
            if isinstance(out, dict) and out.get("kind") in REPLY_KINDS:
                return out["kind"]
        except RuntimeError:
            pass
    for kind, pat in KEYWORDS:
        if re.search(pat, text, re.I):
            return kind
    return "other"


def draft_reply(cfg, lead: dict, reply_text: str, kind: str) -> str:
    import outreach as O
    s = O.settings(cfg)
    if not enabled(cfg):
        base = {"interested": "Great to hear! The easiest next step is a free 15-minute call where I "
                              f"walk you through what I found and what I'd change. Pick any time here: {s['calendly']}",
                "question": "Happy to answer. Our Wix redesigns start at $350 for 3-5 pages and $600 for "
                            "5-10 pages. The quickest way to get an exact quote is a free 15-minute call: "
                            f"{s['calendly']}",
                "later": "No problem at all. I'll check back in a couple of months. If anything changes "
                         f"sooner, you can book a quick call any time: {s['calendly']}"}
        return f"Hi,\n\n{base.get(kind, 'Thanks for getting back to me.')}\n\n{s['sender_name']}\n{s['company']}"
    return ask(cfg, f"""Write a short, warm reply (under 90 words, plain text) from {s['sender_name']} at
{s['company']} (Wix Legend Partner web design studio) to this reply from a business owner.
Reply type: {REPLY_KINDS.get(kind, kind)}. Prices if asked: 3-5 pages $350, 5-10 pages $600,
online store +30%. Always steer to a free 15-minute call at {s['calendly']}. If they said not now,
be gracious and say you'll check back later. Never push. Sign as {s['sender_name']}, {s['company']}.

Business: {lead.get('name') or lead.get('domain')}
Their reply:
{reply_text[:2500]}""", want_json=False)


# ---------------------------------------------------------------------------
# Mockup prompt for the Gemini app (paste it yourself, no API)
# ---------------------------------------------------------------------------
def mockup_prompt(lead: dict, audit_data: dict | None = None, plan: dict | None = None) -> str:
    import audit as A
    c = W.load_categories().get(lead.get("category") or "", {})
    cat = (c.get("short") or c.get("label") or (lead.get("category") or "local business").replace("_", " ")).split(" (")[0]
    name = lead.get("name") or lead.get("site_name") or lead.get("domain")
    city = ", ".join(x for x in (W.city_from_address(lead.get("city") or ""), lead.get("region_name")) if x)
    fixes = A.top_findings(audit_data, 6)
    phone = (lead.get("phones") or lead.get("listed_phone") or "").split(";")[0].strip()
    lines = [
        f"Create a modern, high-converting homepage mockup for \"{name}\" (category: {cat.lower()})"
        f"{(', located in ' + city) if city else ''}. Current website: {lead.get('final_url') or lead.get('website')}",
        "",
        "Show it as a realistic desktop website screenshot (16:10), plus a small phone version beside it.",
        "",
        "Layout, top to bottom:",
        f"1. Clean header with the business name \"{name}\", simple menu (Home, Services, About, Reviews, Contact) "
        f"and a bold \"Book now\" button{(' and the phone number ' + phone) if phone else ''}.",
        f"2. Hero section: large real-looking photo that fits this kind of business ({cat.lower()}), a clear headline saying what they do "
        f"and where{(' (' + city + ')') if city else ''}, a one-line benefit, and two buttons: \"Book an appointment\" "
        "and \"Call now\".",
        "3. Trust bar: Google star rating, years in business, a few short badges.",
        "4. Services: 3-6 cards with icons and one line each.",
        "5. Reviews: 3 customer testimonial cards with stars.",
        "6. About / team section with a friendly photo.",
        "7. Location: map, hours, address, phone, and a short contact form.",
        "8. Footer with social icons and the current year.",
        "",
        "Style: professional, warm and trustworthy; generous white space; modern sans-serif font; "
        "consistent brand colours that suit this business; real-looking photos (no cartoons); readable text "
        "with good contrast; clearly designed for mobile too.",
    ]
    if fixes:
        lines += ["", "The new design must visibly fix these problems with the current site:"]
        lines += [f"- {f}" for f in fixes]
    if plan and plan.get("angle"):
        lines += ["", f"Main selling point to make obvious: {plan['angle']}"]
    lines += ["", "Keep all text in English, spelled correctly, and don't invent awards or fake claims."]
    return "\n".join(lines)
