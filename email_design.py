"""Branded HTML version of an email (NA Developers look).

The plain-text body stays as written; this builds a matching HTML version that
goes out alongside it. Email programs show the HTML; spam filters and older
programs still see the clean text. No remote images (they're often blocked):
the logo is drawn with text in your brand colours.
"""
from __future__ import annotations

import html
import re

NAVY, TEAL, RED = "#16212D", "#1E91A8", "#E8222B"
BULLET_RE = re.compile(r"^[•*✗-]\s*")
URL_RE = re.compile(r"(https?://[^\s<]+[^\s<.,;:!?)\]'\"])")


def _linkify(text: str) -> str:
    out = html.escape(text)
    return URL_RE.sub(lambda m: f'<a href="{m.group(1)}" style="color:{TEAL}">{m.group(1)}</a>', out)


def _split_signature(body: str, sender: str) -> tuple[str, str, str]:
    """(main text, signature, footer) - footer is the address/unsubscribe part."""
    footer = ""
    if "\n--\n" in body:
        body, footer = body.split("\n--\n", 1)
    lines = body.rstrip().split("\n")
    sig_start = len(lines)
    for i in range(len(lines) - 1, max(-1, len(lines) - 6), -1):
        if lines[i].strip().startswith(sender.split()[0]):
            sig_start = i
            break
    return "\n".join(lines[:sig_start]).rstrip(), "\n".join(lines[sig_start:]).strip(), footer.strip()


def to_html(body: str, s: dict, testimonial: tuple[str, str] | None = None) -> str:
    main, sig, footer = _split_signature(body, s.get("sender_name", "Awais"))
    cal = s.get("calendly", "")
    blocks = []
    for para in re.split(r"\n\s*\n", main.strip()):
        lines = [ln for ln in para.split("\n") if ln.strip()]
        if lines and all(ln.lstrip().startswith(("•", "-", "*", "✗")) for ln in lines):
            texts = [_linkify(BULLET_RE.sub("", ln.strip())) for ln in lines]
            items = "".join(
                f'<tr><td style="width:22px;vertical-align:top;color:{RED};font-weight:700">✗</td>'
                f'<td style="padding:0 0 8px 0">{t}</td></tr>' for t in texts)
            blocks.append(f'<table role="presentation" cellpadding="0" cellspacing="0" '
                          f'style="margin:4px 0 14px 0;font-size:15px;line-height:1.5">{items}</table>')
        else:
            para_html = _linkify("\n".join(lines)).replace("\n", "<br>")
            blocks.append(f'<p style="margin:0 0 14px 0">{para_html}</p>')
    button = (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:8px 0 22px 0"><tr>'
              f'<td style="background:{RED};border-radius:6px"><a href="{html.escape(cal)}" '
              f'style="display:inline-block;padding:12px 22px;color:#ffffff;font-weight:700;'
              f'text-decoration:none;font-size:15px">Book a free 15-minute call</a></td></tr></table>') if cal else ""
    quote = ""
    if testimonial:
        quote = (f'<div style="border-left:3px solid {TEAL};background:#F3F8FA;padding:12px 16px;margin:0 0 20px 0;'
                 f'font-size:14px;color:#374151"><div>“{html.escape(testimonial[0])}”</div>'
                 f'<div style="margin-top:6px;color:#6B7785;font-size:13px">★★★★★ {html.escape(testimonial[1])}</div></div>')
    proof = html.escape(s.get("proof_line", "Wix Legend Partner · About 2,000 projects in 8 years · 24/7 support"))
    sig_html = _linkify(sig).replace("\n", "<br>") if sig else html.escape(s.get("sender_name", ""))
    foot_html = _linkify(footer).replace("\n", "<br>")
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head><body style="margin:0;padding:0;background:#F3F5F8">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F3F5F8;padding:24px 0">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:10px;overflow:hidden;font-family:Segoe UI,Helvetica,Arial,sans-serif;color:{NAVY}">
<tr><td style="background:{NAVY};padding:16px 28px">
<span style="font:700 20px Consolas,Menlo,monospace;color:{TEAL}">&lt;</span><span style="font:700 20px Consolas,Menlo,monospace;color:#ffffff">/</span><span style="font:700 20px Consolas,Menlo,monospace;color:{RED}">&gt;</span>
<span style="font-weight:800;font-size:17px;color:#ffffff;letter-spacing:.5px;margin-left:8px">{html.escape(s.get('company', 'NA Developers').upper())}</span>
</td></tr>
<tr><td style="height:4px;background:{TEAL}"></td></tr>
<tr><td style="padding:28px 28px 8px 28px;font-size:15px;line-height:1.6">
{''.join(blocks)}{button}{quote}
<div style="font-size:15px;line-height:1.5">{sig_html}</div>
</td></tr>
<tr><td style="padding:14px 28px;background:#F7F9FB;border-top:1px solid #E2E7EE;font-size:12px;color:#6B7785">
<b style="color:{NAVY}">{proof}</b><br>{foot_html}</td></tr>
</table></td></tr></table></body></html>"""
