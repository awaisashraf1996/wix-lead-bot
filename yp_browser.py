"""Yellow Pages window inside the app.

Opens yellowpages.com / yellowpages.ca in a normal browser window (Microsoft
Edge WebView2, built into Windows 10/11). YOU browse it: solve any "are you
human" check yourself and click "Next" to go to more pages. Every page you
look at is read automatically and the businesses' websites are sent to the
main app, which checks them for Wix.

Runs as a separate process:  WixLeadBot.exe --yp-browser <url>
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

EXIT_NO_WEBVIEW = 3

BADGE_JS = """
(function(n, t){
  var b = document.getElementById('na-capture-badge');
  if (!b) { b = document.createElement('div'); b.id = 'na-capture-badge';
    b.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:2147483647;' +
      'background:#16212D;color:#fff;font:600 13px Segoe UI,Arial;padding:10px 14px;' +
      'border-radius:10px;box-shadow:0 4px 16px rgba(0,0,0,.3);border-left:4px solid #1E91A8';
    document.body.appendChild(b); }
  b.textContent = '</> NA Developers: ' + n + ' websites on this page · ' + t + ' captured';
})(%d, %d);
"""


def _extract_js(bundled_dir: str) -> str:
    path = os.path.join(bundled_dir, "chrome-extension", "extract.js")
    with open(path, encoding="utf-8") as f:
        return f.read()


def _post(port: int, token: str, items: list) -> int:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/capture",
        data=json.dumps({"items": items}).encode(),
        headers={"Content-Type": "application/json", "X-NA-Token": token}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read()).get("new", 0)


def run(url: str, bundled_dir: str, data_dir: str) -> int:
    try:
        import webview  # pywebview
    except Exception:
        return EXIT_NO_WEBVIEW
    port = int(os.environ.get("NA_INBOX_PORT", "8765"))
    token = os.environ.get("NA_INBOX_TOKEN", "")
    script = "(function(){" + _extract_js(bundled_dir) + "\nreturn naExtract();})()"
    state = {"closed": False, "seen": set(), "total": 0}

    win = webview.create_window("Yellow Pages · NA Developers Lead Capture", url,
                                width=1280, height=880, text_select=True)

    def on_closed():
        state["closed"] = True

    win.events.closed += on_closed

    def worker():
        last_sig = None
        while not state["closed"]:
            time.sleep(2.5)
            try:
                res = win.evaluate_js(script)
            except Exception:
                continue
            if not isinstance(res, dict):
                continue
            items = res.get("items") or []
            fresh = [i for i in items if i.get("website") and i["website"] not in state["seen"]]
            sig = (win.get_current_url(), len(items))
            if fresh:
                try:
                    _post(port, token, fresh)
                    for i in fresh:
                        state["seen"].add(i["website"])
                    state["total"] += len(fresh)
                except Exception:
                    pass
            if sig != last_sig or fresh:
                last_sig = sig
                try:
                    win.evaluate_js(BADGE_JS % (len(items), state["total"]))
                except Exception:
                    pass

    try:
        webview.start(worker, private_mode=False,
                      storage_path=os.path.join(data_dir, "yp_browser_data"))
    except Exception:
        return EXIT_NO_WEBVIEW
    return 0


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else "https://www.yellowpages.com",
                 here, here))
