"""Designed HTML emails in the NA Developers look.

Three layouts:
- "first":    light and personal - logo row, an audit snapshot card for their site,
              one button, a signature card. Looks like a real person wrote it.
- "followup": logo header, message, recent work cards, client review, offer banner,
              button, signature card.
- "reply":    logo header, message, button, signature card.

Every email also carries the plain-text version, so it works everywhere.
Buttons are real text (not images) and links show readable words, not raw URLs.
"""
from __future__ import annotations

import html
import re

NAVY, TEAL, RED, MUTED, LINE, SOFT = "#16212D", "#1E91A8", "#E8222B", "#6B7785", "#E3E8EF", "#F4F7FA"
ASSET = "https://raw.githubusercontent.com/awaisashraf1996/wix-lead-bot/main/assets/"
DEFAULT_LOGO_DARK = ASSET + "logo_login_dark.png"      # white text, for the navy header
DEFAULT_LOGO_LIGHT = ASSET + "logo_login_t.png"        # navy text, for white backgrounds
DEFAULT_MARK = ASSET + "mark64_t.png"
DEFAULT_WORK = [
    ["Cruise Cali", "Luxury travel", "https://nadevelopers.com/wp-content/uploads/2026/11/cruise-cali-cover-768x409.jpg"],
    ["Great Details Auto Care", "Auto repair", "https://nadevelopers.com/wp-content/uploads/2026/11/great-details-auto-care-cover-768x409.jpg"],
    ["Matador Roofing", "Roofing", "https://nadevelopers.com/wp-content/uploads/2026/11/matador-roofing-cover-768x409.jpg"],
]
BADGES = "https://nadevelopers.com/wp-content/themes/na-developers/assets/img/badges/"
DEFAULT_BRAND = {
    "legend_badge": BADGES + "wix.png",
    "partner_logos": [[BADGES + "wix.png", "Wix Legend Partner", 40], [BADGES + "google.png", "Google Partner", 34],
                      [BADGES + "shopify.png", "Shopify", 24], [BADGES + "wordpress.png", "WordPress", 22],
                      [BADGES + "designrush.png", "DesignRush", 20]],
    "socials": [["Facebook", "https://www.facebook.com/nadevelopersagency", "f", "#1877F2"],
                ["Instagram", "https://www.instagram.com/nadevelopers/", "ig", "#E4405F"],
                ["LinkedIn", "https://www.linkedin.com/company/nadevelopers/", "in", "#0A66C2"],
                ["X", "https://x.com/DevelopersNa", "X", "#111111"]],
    "contact_email": "info@nadevelopers.com",
    "whatsapp": "+92 315 5444281",
}
BULLET_RE = re.compile(r"^[•*✗-]\s*")
URL_RE = re.compile(r"(https?://[^\s<]+[^\s<.,;:!?)\]'\"]|www\.[^\s<]+[^\s<.,;:!?)\]'\"])")
FONT = "font-family:'Segoe UI',Helvetica,Arial,sans-serif"
SIGNOFFS = ("all the best", "best,", "thanks,", "cheers,", "regards,", "wishing you")


def _nice(url: str) -> str:
    u = re.sub(r"^https?://(www\.)?", "", url).rstrip("/")
    if "calendly.com" in u:
        return "book a call"
    return u


def _linkify(text: str) -> str:
    """Escape text and turn web addresses into short, readable links."""
    out, pos = [], 0
    for m in URL_RE.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        url = m.group(1)
        href = url if url.startswith("http") else "https://" + url
        out.append(f'<a href="{html.escape(href)}" style="color:{TEAL};text-decoration:none;font-weight:600">'
                   f'{html.escape(_nice(url))}</a>')
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


def _split(body: str, sender: str) -> tuple[str, list[str], str]:
    """(main text, signature lines incl. any sign-off, footer)."""
    footer = ""
    if "\n--\n" in body:
        body, footer = body.split("\n--\n", 1)
    lines = body.rstrip().split("\n")
    first = (sender or "Awais").split()[0]
    for i in range(len(lines) - 1, max(-1, len(lines) - 7), -1):
        ln = lines[i].strip()
        if ln.startswith(first):
            start = i
            if i > 0 and lines[i - 1].strip().lower().startswith(SIGNOFFS):
                start = i - 1
            return "\n".join(lines[:start]).rstrip(), [x.strip() for x in lines[start:] if x.strip()], footer.strip()
    return body.rstrip(), [], footer.strip()


def _paragraphs(main: str, s: dict, kind: str) -> str:
    blocks = []
    offer = (s.get("offer") or "").strip()
    for para in re.split(r"\n\s*\n", main.strip()):
        lines = [ln for ln in para.split("\n") if ln.strip()]
        if not lines:
            continue
        text = "\n".join(lines)
        if offer and text.strip() == offer:
            blocks.append(
                f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:4px 0 18px 0">'
                f'<tr><td style="background:#FFF4F4;border:1px solid #F7C9CB;border-radius:10px;padding:14px 16px;'
                f'font-size:14px;color:{NAVY}"><span style="display:inline-block;background:{RED};color:#fff;'
                f'font-size:11px;font-weight:700;letter-spacing:.6px;padding:3px 8px;border-radius:4px;'
                f'margin-right:8px">OFFER</span>{_linkify(offer)}</td></tr></table>')
            continue
        if all(ln.lstrip().startswith(("•", "-", "*", "✗")) for ln in lines):
            rows = ""
            for i, ln in enumerate(lines):
                sep = f"border-top:1px solid {LINE};" if i else ""
                rows += (f'<tr><td width="34" style="vertical-align:top;padding:12px 0 12px 14px;{sep}">'
                         f'<div style="width:20px;height:20px;border-radius:10px;background:#FDE8E9;color:{RED};'
                         f'font-size:11px;font-weight:700;text-align:center;line-height:20px">&#10005;</div></td>'
                         f'<td style="padding:12px 14px 12px 6px;font-size:14px;line-height:1.5;color:{NAVY};{sep}">'
                         f'{_linkify(BULLET_RE.sub("", ln.strip()))}</td></tr>')
            title = ""
            if s.get("_site"):
                speed = (f' &nbsp;·&nbsp; phone speed <b style="color:#FFB4B7">{s["_speed"]}/100</b>'
                         if s.get("_speed") is not None else "")
                title = (f'<tr><td colspan="2" style="background:{NAVY};color:#ffffff;padding:10px 14px;'
                         f'font-size:12px;letter-spacing:.4px;border-radius:9px 9px 0 0"><b>WHAT I NOTICED</b>'
                         f' &nbsp;·&nbsp; {html.escape(_nice(s["_site"]))}{speed}</td></tr>')
            blocks.append(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
                          f'style="margin:2px 0 18px 0;border:1px solid {LINE};border-radius:10px;'
                          f'background:#FFFFFF">{title}{rows}</table>')
            continue
        if s.get("calendly") and s["calendly"] in text and len(re.findall(r"https?://", text)) == 1:
            text = re.sub(r"\s*(My calendar|Here'?s my calendar|Book here)?:?\s*" + re.escape(s["calendly"]), "", text).rstrip(" :")
            if not text.strip():
                continue
            if not text.rstrip().endswith(("?", ".", "!")):
                text = text.rstrip() + "?"
        para_html = _linkify(text).replace("\n", "<br>")
        blocks.append(f'<p style="margin:0 0 16px 0">{para_html}</p>')
    return "".join(blocks)


def _button(s: dict, label: str = "Book a free 15-minute call") -> str:
    cal = s.get("calendly", "")
    if not cal:
        return ""
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:6px 0 8px 0"><tr>'
            f'<td style="background:{RED};border-radius:8px"><a href="{html.escape(cal)}" '
            f'style="display:inline-block;padding:13px 24px;color:#ffffff;font-weight:700;text-decoration:none;'
            f'font-size:15px;{FONT}">{html.escape(label)} &rarr;</a></td></tr></table>'
            f'<div style="font-size:12px;color:{MUTED};margin:0 0 24px 0">15 minutes on Zoom or phone '
            f'&nbsp;·&nbsp; no obligation &nbsp;·&nbsp; fixed written quote</div>')


def _b(s: dict, key: str):
    v = s.get(key)
    return DEFAULT_BRAND[key] if v in (None, "", []) else v


def _socials(s: dict, size: int = 26) -> str:
    cells = ""
    for name, url, label, col in _b(s, "socials"):
        if not url:
            continue
        cells += (f'<td style="padding-right:6px"><a href="{html.escape(url)}" title="{html.escape(name)}" '
                  f'style="display:inline-block;width:{size}px;height:{size}px;line-height:{size}px;border-radius:{size // 2}px;'
                  f'background:{col};color:#ffffff;text-align:center;font-size:12px;font-weight:700;'
                  f'text-decoration:none;{FONT}">{html.escape(label)}</a></td>')
    return f'<table role="presentation" cellpadding="0" cellspacing="0"><tr>{cells}</tr></table>' if cells else ""


def _signature(sig_lines: list[str], s: dict) -> str:
    name = s.get("sender_name", "Awais")
    company = s.get("company", "NA Developers")
    mark = s.get("mark_url") or DEFAULT_MARK
    site = s.get("website", "www.nadevelopers.com")
    site_href = site if site.startswith("http") else "https://" + site
    email = _b(s, "contact_email")
    wa = (s.get("whatsapp") if s.get("whatsapp") is not None else DEFAULT_BRAND["whatsapp"]).strip()
    wa_link = "https://wa.me/" + re.sub(r"\D", "", wa) if wa else ""
    sign_off = ""
    if sig_lines and sig_lines[0].lower().startswith(SIGNOFFS):
        sign_off = f'<div style="margin:0 0 12px 0">{html.escape(sig_lines[0])}</div>'
    a = f"color:{TEAL};text-decoration:none"
    lines = [f'<a href="{html.escape(site_href)}" style="{a}">{html.escape(_nice(site))}</a>']
    if email:
        lines.append(f'<a href="mailto:{html.escape(email)}" style="{a}">{html.escape(email)}</a>')
    contact2 = []
    if wa:
        contact2.append(f'WhatsApp <a href="{html.escape(wa_link)}" style="{a}">{html.escape(wa)}</a>')
    if s.get("calendly"):
        contact2.append(f'<a href="{html.escape(s["calendly"])}" style="{a};font-weight:600">Book a call</a>')
    badge = _b(s, "legend_badge")
    return (f'{sign_off}<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin:8px 0 10px 0;border-top:1px solid {LINE};padding-top:16px"><tr>'
            f'<td width="58" style="vertical-align:top;padding:16px 14px 0 0">'
            f'<img src="{html.escape(mark)}" width="52" height="52" alt="NA Developers" style="display:block;border:0"></td>'
            f'<td style="vertical-align:top;padding:16px 10px 0 14px;border-left:3px solid {TEAL};font-size:13px;'
            f'line-height:1.6;color:{MUTED}">'
            f'<div style="font-size:16px;font-weight:700;color:{NAVY}">{html.escape(name)}</div>'
            f'<div style="color:{NAVY}">{html.escape(s.get("job_title") or "Founder")}, {html.escape(company)}</div>'
            f'<div>{" &nbsp;·&nbsp; ".join(lines)}</div>'
            + (f'<div>{" &nbsp;·&nbsp; ".join(contact2)}</div>' if contact2 else "")
            + f'<div style="padding-top:8px">{_socials(s)}</div></td>'
            + (f'<td width="74" style="vertical-align:top;padding:16px 0 0 0;text-align:right">'
               f'<img src="{html.escape(badge)}" width="70" height="70" alt="Wix Legend Partner" '
               f'style="display:inline-block;border:0"></td>' if badge else "")
            + '</tr></table>')


def _partners(s: dict) -> str:
    cells = "".join(
        f'<td style="padding:0 10px;vertical-align:middle"><img src="{html.escape(u)}" height="{h}" alt="{html.escape(alt)}" '
        f'style="display:block;border:0;height:{h}px;width:auto"></td>'
        for u, alt, h in _b(s, "partner_logos") if u)
    if not cells:
        return ""
    return (f'<tr><td style="padding:16px 30px 6px 30px;border-top:1px solid {LINE}" align="center">'
            f'<div style="font-size:11px;letter-spacing:.8px;color:{MUTED};font-weight:700;margin-bottom:10px">'
            f'TRUSTED PARTNER &nbsp;·&nbsp; PLATFORMS WE BUILD ON</div>'
            f'<table role="presentation" cellpadding="0" cellspacing="0" align="center"><tr>{cells}</tr></table>'
            f'</td></tr>')


def _work(s: dict) -> str:
    items = [w for w in (s.get("work") or DEFAULT_WORK) if w and w[0]][:3]
    if not items:
        return ""
    port = s.get("portfolio_url", "")
    cells = ""
    for w in items:
        title, cat, img = (list(w) + ["", "", ""])[:3]
        pic = (f'<img src="{html.escape(img)}" width="170" alt="{html.escape(title)} website" '
               f'style="display:block;width:100%;height:auto;border-radius:8px 8px 0 0;border:0">' if img else "")
        cells += (f'<td width="33%" style="vertical-align:top;padding:0 5px">'
                  f'<a href="{html.escape(port)}" style="text-decoration:none;color:{NAVY}">'
                  f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
                  f'style="border:1px solid {LINE};border-radius:8px;background:#ffffff"><tr><td>{pic}'
                  f'<div style="padding:8px 10px 2px 10px;font-size:13px;font-weight:700;color:{NAVY}">'
                  f'{html.escape(title)}</div><div style="padding:0 10px 10px 10px;font-size:12px;color:{MUTED}">'
                  f'{html.escape(cat)}</div></td></tr></table></a></td>')
    more = (f'<div style="font-size:13px;margin:4px 0 22px 0"><a href="{html.escape(port)}" style="color:{TEAL};'
            f'text-decoration:none;font-weight:600">See the full portfolio &rarr;</a></div>') if port else ""
    return (f'<div style="font-size:12px;font-weight:700;letter-spacing:.6px;color:{MUTED};margin:2px 0 10px 0">'
            f'RECENT WORK</div><table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            f'<tr>{cells}</tr></table>{more}')


def _quote(t) -> str:
    if not t:
        return ""
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 24px 0">'
            f'<tr><td style="background:{SOFT};border-radius:10px;padding:16px 18px">'
            f'<div style="color:#F5A623;font-size:14px;letter-spacing:2px">★★★★★</div>'
            f'<div style="font-size:15px;line-height:1.55;color:{NAVY};margin:6px 0">“{html.escape(t[0])}”</div>'
            f'<div style="font-size:12px;color:{MUTED}">{html.escape(t[1])}</div></td></tr></table>')


def to_html(body: str, s: dict, testimonial=None, kind: str = "followup") -> str:
    main, sig, footer = _split(body, s.get("sender_name", "Awais"))
    content = _paragraphs(main, s, kind)
    proof = html.escape(s.get("proof_line", "Wix Legend Partner · About 2,000 projects in 8 years · 24/7 support"))
    foot = _linkify(footer).replace("\n", "<br>")
    partners = _partners(s) if kind != "first" else ""
    if kind == "first":
        top = (f'<tr><td style="padding:24px 30px 4px 30px"><img src="{html.escape(s.get("logo_light_url") or DEFAULT_LOGO_LIGHT)}" '
               f'width="150" alt="NA Developers" style="display:block;border:0;height:auto"></td></tr>')
        extra = _button(s)
    else:
        top = (f'<tr><td style="background:{NAVY};padding:18px 30px;border-radius:12px 12px 0 0">'
               f'<img src="{html.escape(s.get("logo_dark_url") or DEFAULT_LOGO_DARK)}" width="140" '
               f'alt="NA Developers" style="display:block;border:0;height:auto"></td></tr>'
               f'<tr><td style="height:4px;background:{TEAL};line-height:4px;font-size:0">&nbsp;</td></tr>')
        extra = _button(s) + ((_work(s) + _quote(testimonial)) if kind == "followup" else "")
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<meta name="color-scheme" content="light only"></head><body style="margin:0;padding:0;background:#EEF2F6">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#EEF2F6;padding:28px 10px">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:12px;border:1px solid {LINE};{FONT};color:{NAVY}">
{top}
<tr><td style="padding:22px 30px 10px 30px;font-size:15px;line-height:1.65;color:{NAVY}">
{content}{extra}{_signature(sig, s)}
</td></tr>
{partners}
<tr><td style="padding:16px 30px;background:#F7F9FB;border-top:1px solid {LINE};border-radius:0 0 12px 12px;font-size:12px;line-height:1.6;color:{MUTED}">
<b style="color:{NAVY}">{proof}</b><br>{foot}</td></tr>
</table></td></tr></table></body></html>"""
