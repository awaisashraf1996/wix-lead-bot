"""Phone calls you make yourself, with help:
- a call script written for each lead (Gemini if you have a key, a good template if not)
- a call list: who to ring today and why
- log how the call went; the app updates the pipeline, sets reminders and can draft a follow-up email.
Nothing here dials automatically or uses an AI voice. You make every call.
"""
from __future__ import annotations

import datetime as dt
import json
import re

import wixbot as W

SCHEMA = """
CREATE TABLE IF NOT EXISTS call_scripts (domain TEXT PRIMARY KEY, data TEXT, source TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT, domain TEXT, phone TEXT, outcome TEXT, notes TEXT,
    called_at TEXT, callback_on TEXT
);
CREATE INDEX IF NOT EXISTS ix_calls_domain ON calls(domain);
"""

OUTCOMES = [
    ("no_answer", "No answer"),
    ("voicemail", "Left voicemail"),
    ("gatekeeper", "Spoke to staff"),
    ("call_back", "Call back later"),
    ("interested", "Interested"),
    ("booked", "Booked a meeting"),
    ("not_interested", "Not interested"),
    ("wrong_number", "Wrong number"),
    ("do_not_call", "Don't call again"),
]
OUTCOME_LABELS = dict(OUTCOMES)
# outcomes that leave the lead on the call list (try again later)
RETRY = {"no_answer": 2, "voicemail": 3, "gatekeeper": 2}
MAX_TRIES = 3


def init(db: W.DB) -> None:
    with db.lock:
        db.conn.executescript(SCHEMA)
        db.conn.commit()


# ---------------------------------------------------------------------------
# Phone numbers and local time
# ---------------------------------------------------------------------------
def phones(lead: dict) -> list[str]:
    raw = [p.strip() for p in (lead.get("phones") or "").split(";")] + [(lead.get("listed_phone") or "").strip()]
    out = []
    for p in raw:
        d = re.sub(r"\D", "", p)
        if len(d) == 11 and d.startswith("1"):
            d = d[1:]
        if len(d) == 10 and d not in out:
            out.append(d)
    return out


def pretty(d: str) -> str:
    return f"({d[:3]}) {d[3:6]}-{d[6:]}" if len(d) == 10 else d


def tel(d: str) -> str:
    return "tel:+1" + d


def local_time(lead: dict) -> dt.datetime | None:
    tz = W.REGION_TZ.get(lead.get("region") or "")
    if not tz:
        return None
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo(tz))
    except Exception:
        return None


def good_time(lead: dict) -> tuple[bool, str]:
    """(ok to call now?, 'Tue 10:42 AM their time')"""
    t = local_time(lead)
    if not t:
        return True, ""
    label = t.strftime("%a %I:%M %p").replace(" 0", " ") + " their time"
    ok = t.weekday() < 5 and (9 <= t.hour < 12 or 13 <= t.hour < 17)
    return ok, label


# ---------------------------------------------------------------------------
# Scripts
# ---------------------------------------------------------------------------
def clean_name(lead: dict) -> str:
    """'Delta Drama - www.deltadrama.com' -> 'Delta Drama'"""
    n = (lead.get("name") or "").strip()
    for sep in (" - ", " | ", " – ", " — ", ": "):
        if sep in n:
            head = n.split(sep)[0].strip()
            if len(head) >= 3:
                n = head
    n = re.sub(r"\s*\(?(https?://)?www\.\S+\)?", "", n).strip()
    return n or lead["domain"]


def _ctx(db, lead):
    import outreach as O
    import website as WS
    cat = W.load_categories().get(lead.get("category") or "", {}).get("label") or "business"
    pts = O._issue_points(lead)
    try:
        review = WS.audit_url(db, lead["domain"]) or ""
    except Exception:
        review = ""
    st = O.get_outreach(db, lead["domain"]) or {}
    emailed = st.get("status") not in (None, "new", "draft")
    viewed = bool(db.q("SELECT 1 FROM tasks WHERE domain=? AND kind='viewed'", (lead["domain"],)))
    ads = any(x in (lead.get("marketing") or "") for x in W.ADS_LABELS)
    return cat, pts, review, emailed, viewed, ads


def template_script(db: W.DB, cfg, lead: dict) -> dict:
    """A solid script without AI, built from what the bot found on their site."""
    import outreach as O
    s = O.settings(cfg)
    cat, pts, review, emailed, viewed, ads = _ctx(db, lead)
    name = clean_name(lead)
    me, co = s["sender_name"], s["company"]
    site = lead["domain"]
    problems = [p for p, _ in pts[:3]] or ["the homepage could do a better job of turning visitors into calls and bookings."]
    tips = [t for _, t in pts[:3]]
    reason = ("I sent you a short email with a free review of your website" if emailed else
              f"I was looking at {site} earlier")
    if viewed:
        reason = "you opened the free website review I sent over"
    return {
        "goal": "Book a free 15-minute call (or get permission to send the calendar link). Don't sell on this call.",
        "opener": f"Hi, is this the owner of {name}? … Great. This is {me} from {co}. "
                  f"I'll be quick: {reason}, and I noticed a couple of things that are probably costing you customers. "
                  "Have you got 30 seconds?",
        "gatekeeper": f"No problem. Who looks after the website for {name}? … Could you pass on that {me} from {co} "
                      f"called about a couple of quick fixes on {site}? What's the best time to catch them?",
        "problems": problems,
        "value": f"We're a Wix Legend Partner and have built about 2,000 websites. Most of what I found are quick fixes"
                 + (", and because you're paying for ads, fixing them makes every ad dollar work harder." if ads else
                    ", and they usually mean more calls and bookings from the same visitors."),
        "questions": [
            "Who looks after the website for you right now?",
            "Where do most of your new customers find you: Google, word of mouth, social media?",
            f"Is getting more {'bookings' if 'Book' in ' '.join(problems) else 'enquiries'} from the website something you'd want this year?",
        ],
        "objections": [
            ["We're happy with our website.", "That's great, it's a good base. These are small fixes, not a new site. "
             "Would it hurt to see the 3 changes in a 15-minute call?"],
            ["We don't have the budget.", "Totally fair. Some of these you can fix yourself, and I'll show you how for free. "
             "If you ever want help, our sites start at $350 with a fixed quote."],
            ["Just send me an email.", "Happy to. What's the best email? I'll send the review and my calendar, "
             "and you can pick a time if it's useful."],
            ["We already have someone.", "Good to hear. Feel free to pass the review to them, it's free. "
             "If they're ever busy, we're here."],
            ["How did you get my number?", f"It's listed on your website, {site}. I only call businesses about their "
             "own website. Want me to take you off my list?"],
        ],
        "close": "Would a free 15-minute call this week be worth it? I'll walk you through the fixes on screen. "
                 "What works better for you, tomorrow or later in the week? (Then send the Calendly link by email.)",
        "voicemail": f"Hi, this is {me} from {co}, a Wix design partner. I took a look at {site} and found "
                     f"{len(problems)} quick fixes that could bring you more customers. I've put them in a free review "
                     f"for you{' (link in my email)' if review or emailed else ''}. You can reach me at "
                     f"{s.get('email') or 'info@nadevelopers.com'}. Have a great day.",
        "tips": tips,
    }


def ai_script(db: W.DB, cfg, lead: dict) -> dict:
    import ai
    import audit as A
    import outreach as O
    s = O.settings(cfg)
    cat, pts, review, emailed, viewed, ads = _ctx(db, lead)
    plan = ai.get_plan(db, lead["domain"]) or {}
    base = template_script(db, cfg, lead)
    prompt = f"""You coach {s['sender_name']} from {s['company']} (Wix Legend Partner, about 2,000 websites built in
8 years, fixed quotes, sites from $350) who is about to phone a small business in North America himself.
He is polite, calm and short. The goal of the call is ONLY to book a free 15-minute call ({s['calendly']}) or get
permission to email the calendar link. Never pressure. If they ask not to be called, apologise and stop.

Business facts:
{ai._lead_facts(lead, A.get(db, lead['domain']))}
Already emailed them: {"yes" if emailed else "no"}. Opened their free website review: {"yes" if viewed else "no"}.
Earlier plan notes: {json.dumps({k: plan.get(k) for k in ('angle', 'talking_points', 'objections') if plan.get(k)})}

Write JSON with keys:
"goal": one sentence,
"opener": what to say in the first 15 seconds, with his name and company, why he is calling (specific to them), ends with a permission question,
"gatekeeper": what to say if a staff member answers,
"problems": 2-3 strings, the most convincing problems found, in plain spoken English, specific to this business,
"value": 1-2 sentences why fixing them matters to THIS business (customers, bookings, ad money),
"questions": 3 short discovery questions,
"objections": list of [objection, answer] pairs, 5 of them, likely for this type of business,
"close": how to ask for the 15-minute call,
"voicemail": a 20-second voicemail,
"tips": 2-3 short tips for this specific call.
Plain spoken English. No jargon. Do not invent facts."""
    data = ai.ask(cfg, prompt)
    if not isinstance(data, dict) or not data.get("opener"):
        raise RuntimeError("Gemini's answer was missing the script.")
    for k, v in base.items():
        data.setdefault(k, v)
    return data


def get_script(db: W.DB, cfg, lead: dict, refresh: bool = False, use_ai: bool = True) -> tuple[dict, str]:
    """(script, 'ai'|'template'). Saved, so each lead's script is written once."""
    import ai
    init(db)
    if not refresh:
        r = db.q("SELECT data, source FROM call_scripts WHERE domain=?", (lead["domain"],))
        if r:
            return json.loads(r[0][0]), r[0][1]
    src = "template"
    data = None
    if use_ai and ai.enabled(cfg):
        try:
            data, src = ai_script(db, cfg, lead), "ai"
        except Exception as e:
            W.log(f"  Gemini script failed ({e}); using the template.")
    if data is None:
        data = template_script(db, cfg, lead)
    db.x("INSERT OR REPLACE INTO call_scripts VALUES (?,?,?,?)", (lead["domain"], json.dumps(data), src, W.now()))
    return data, src


def script_text(sc: dict) -> list[tuple[str, str]]:
    """[(heading, text)] in call order, for display."""
    out = [("Goal", sc.get("goal", "")), ("1. Opener", sc.get("opener", "")),
           ("If staff answers", sc.get("gatekeeper", "")),
           ("2. Why I'm calling (what I found)", "\n".join("• " + p for p in sc.get("problems", []))),
           ("3. Why it matters", sc.get("value", "")),
           ("4. Ask", "\n".join("• " + q for q in sc.get("questions", []))),
           ("5. Close", sc.get("close", ""))]
    objs = sc.get("objections") or []
    lines = []
    for o in objs:
        if isinstance(o, (list, tuple)) and len(o) >= 2:
            lines.append(f"“{o[0]}”\n   → {o[1]}")
        elif isinstance(o, dict):
            lines.append(f"“{o.get('objection', '')}”\n   → {o.get('answer', '')}")
        else:
            lines.append(str(o))
    out.append(("If they say…", "\n".join(lines)))
    out.append(("Voicemail (20 seconds)", sc.get("voicemail", "")))
    if sc.get("tips"):
        out.append(("Tips", "\n".join("• " + t for t in sc["tips"])))
    return [(h, t) for h, t in out if t]


# ---------------------------------------------------------------------------
# Call list and logging
# ---------------------------------------------------------------------------
def history(db: W.DB, domain: str) -> list[dict]:
    init(db)
    rows = db.q("SELECT id, phone, outcome, notes, called_at, callback_on FROM calls WHERE domain=? "
                "ORDER BY id DESC", (domain,))
    return [dict(zip(("id", "phone", "outcome", "notes", "called_at", "callback_on"), r)) for r in rows]


def call_list(db: W.DB, limit: int = 300) -> list[dict]:
    """Who to ring, best first, with the reason."""
    import outreach as O
    init(db)
    today = dt.date.today().isoformat()
    last = {}
    for dom, outcome, at, cb, n in db.q(
            "SELECT domain, outcome, MAX(called_at), callback_on, COUNT(*) FROM calls GROUP BY domain"):
        last[dom] = (outcome, at or "", cb, n)
    viewed = {r[0] for r in db.q("SELECT domain FROM tasks WHERE kind='viewed'")}
    out = []
    for lead in db.lead_records():
        nums = phones(lead)
        if not nums or lead.get("no_solicit"):
            continue
        st = (O.get_outreach(db, lead["domain"]) or {}).get("status") or "new"
        if st in ("do_not_contact", "unsubscribed", "won", "lost", "call_booked", "proposal_sent"):
            continue
        prio, why = 0, ""
        if lead["domain"] in last:
            outcome, at, cb, n = last[lead["domain"]]
            if outcome in ("not_interested", "wrong_number", "do_not_call", "booked"):
                continue
            if outcome == "call_back":
                if cb and cb > today:
                    continue
                prio, why = 100, f"Asked you to call back ({cb or 'today'})"
            elif outcome == "interested":
                prio, why = 90, "Was interested: check they booked"
            else:
                days = RETRY.get(outcome, 2)
                if n >= MAX_TRIES or (at and at[:10] > (dt.date.today() - dt.timedelta(days=days)).isoformat()):
                    continue
                prio, why = 40, f"Try again ({OUTCOME_LABELS.get(outcome, outcome).lower()}, {n} call{'s' if n > 1 else ''})"
        else:
            if lead["domain"] in viewed:
                prio, why = 95, "🔥 Opened their free review"
            elif st == "replied":
                prio, why = 85, "Replied to your email"
            elif st in ("emailed", "no_reply"):
                prio, why = 60 + (10 if lead["level"] == "super" else 0), "Emailed, no reply yet"
            elif lead["level"] == "super":
                prio, why = 50, "Super lead"
            elif lead["level"] == "hot":
                prio, why = 30, "Hot lead"
            else:
                continue
        ok, when = good_time(lead)
        out.append({"domain": lead["domain"], "name": clean_name(lead), "phone": nums[0],
                    "level": lead["level"], "why": why, "prio": prio + (5 if ok else 0), "when": when,
                    "ok_now": ok, "region": lead.get("region") or ""})
    out.sort(key=lambda r: -r["prio"])
    return out[:limit]


FOLLOWUP = {
    "voicemail": ("Just left you a voicemail",
                  "Hi {greeting},\n\nI just tried to call and left you a quick voicemail. I'm {me} from {co}, "
                  "a Wix Legend Partner. I took a look at {site} and found a few quick fixes that could bring "
                  "you more customers.\n\nIf it's useful, grab a free 15-minute slot here and I'll walk you through "
                  "them: {calendly}\n\n{me}\n{co} · Wix Legend Partner\n{web}"),
    "no_answer": ("Tried to reach you today",
                  "Hi {greeting},\n\nI tried to give you a quick call today about {site}. I found a few simple "
                  "fixes that could help you get more customers from the website.\n\nIf you'd like to see them, "
                  "here's my calendar for a free 15-minute call: {calendly}\n\n{me}\n{co} · Wix Legend Partner\n{web}"),
    "interested": ("Great speaking with you",
                   "Hi {greeting},\n\nThanks for taking my call today. As promised, here's my calendar so you can "
                   "pick a time that suits you for the free 15-minute walkthrough of {site}: {calendly}\n\n"
                   "Speak soon,\n{me}\n{co} · Wix Legend Partner\n{web}"),
    "call_back": ("Thanks, I'll call back as agreed",
                  "Hi {greeting},\n\nThanks for picking up today. I'll call back as we agreed. If it's easier, you "
                  "can also pick a time here: {calendly}\n\n{me}\n{co} · Wix Legend Partner\n{web}"),
    "gatekeeper": ("For the owner of {name}",
                   "Hi {greeting},\n\nI called earlier and spoke with your team. I'm {me} from {co}, a Wix Legend "
                   "Partner. I found a few quick fixes on {site} that could bring you more customers.\n\nIf you'd "
                   "like a free 15-minute walkthrough, here's my calendar: {calendly}\n\n{me}\n{co} · Wix Legend "
                   "Partner\n{web}"),
}


def followup_draft(db: W.DB, cfg, lead: dict, outcome: str) -> int | None:
    import outreach as O
    if outcome not in FOLLOWUP:
        return None
    s = O.settings(cfg)
    subj, body = FOLLOWUP[outcome]
    v = {"me": s["sender_name"], "co": s["company"], "site": lead["domain"], "calendly": s["calendly"],
         "web": s.get("website", ""), "name": clean_name(lead), "greeting": "{greeting}"}
    return O.make_draft(db, cfg, lead, 0, subject=subj.format(**v), body=body.format(**v))


def log_call(db: W.DB, cfg, lead: dict, phone: str, outcome: str, notes: str = "",
             callback_on: str | None = None, draft_email: bool = True) -> dict:
    """Save the call and move the lead along. Returns what happened."""
    import outreach as O
    init(db)
    dom = lead["domain"]
    db.x("INSERT INTO calls (domain, phone, outcome, notes, called_at, callback_on) VALUES (?,?,?,?,?,?)",
         (dom, phone, outcome, notes.strip(), W.now(), callback_on))
    done = []
    st = (O.get_outreach(db, dom) or {}).get("status") or "new"
    note = f"[Call {dt.date.today().isoformat()}] {OUTCOME_LABELS.get(outcome, outcome)}" + (f": {notes.strip()}" if notes.strip() else "")
    old = (O.get_outreach(db, dom) or {}).get("notes") or ""
    fields = {"notes": (old + "\n" + note).strip()}
    if outcome == "booked":
        O.set_status(db, dom, "call_booked", **fields)
        done.append("Moved to Call booked")
    elif outcome == "interested":
        O.set_status(db, dom, "replied", **fields)
        done.append("Moved to Replied")
    elif outcome == "not_interested":
        O.set_status(db, dom, "lost", **fields)
        done.append("Moved to Lost; no more emails")
    elif outcome == "do_not_call":
        O.set_status(db, dom, "do_not_contact", **fields)
        done.append("Marked Do not contact (no calls or emails)")
    elif outcome == "call_back":
        O.set_status(db, dom, st if st not in ("new",) else "replied", **fields)
        if callback_on:
            db.x("INSERT OR REPLACE INTO tasks (domain, kind, due, done) VALUES (?,?,?,0)",
                 (dom, "call_back", callback_on))
            done.append(f"Reminder set for {callback_on}")
    else:
        O.set_status(db, dom, st, **fields)
    if outcome in ("not_interested", "do_not_call", "booked", "wrong_number"):
        # stop pending follow-ups
        db.x("UPDATE messages SET status='cancelled', error='stopped after phone call' "
             "WHERE domain=? AND status IN ('draft','approved') AND step BETWEEN 2 AND 4", (dom,))
    if draft_email and outcome in FOLLOWUP:
        try:
            if followup_draft(db, cfg, lead, outcome):
                done.append("Follow-up email drafted (Outreach → To approve)")
        except Exception as e:
            W.log(f"  Could not draft follow-up: {e}")
    return {"done": done}


def stats_today(db: W.DB) -> dict:
    init(db)
    today = dt.date.today().isoformat()
    rows = db.q("SELECT outcome, COUNT(*) FROM calls WHERE substr(called_at,1,10)=? GROUP BY outcome", (today,))
    d = dict(rows)
    return {"calls": sum(d.values()), "talked": sum(v for k, v in d.items() if k in
            ("call_back", "interested", "booked", "not_interested", "gatekeeper", "do_not_call")),
            "booked": d.get("booked", 0) + d.get("interested", 0)}
