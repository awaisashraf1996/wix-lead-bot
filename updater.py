"""Self-update from GitHub Releases.

The app asks GitHub for the newest release. If it is newer than this version,
it downloads WixLeadBot.exe, checks its SHA-256 fingerprint against the
WixLeadBot.exe.sha256 file published with it, swaps the files and restarts.
Your data (wixbot.sqlite, config.json, output) is never touched.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys

import requests

import wixbot as W

ASSET = "WixLeadBot.exe"


def _ver(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


def enabled() -> bool:
    return bool(W.UPDATE_REPO) and "/" in W.UPDATE_REPO


def check() -> dict | None:
    """Returns {"version", "notes", "url", "sha_url", "size"} if an update exists."""
    if not enabled():
        return None
    r = requests.get(f"https://api.github.com/repos/{W.UPDATE_REPO}/releases/latest",
                     headers={"Accept": "application/vnd.github+json",
                              "User-Agent": W.USER_AGENT}, timeout=15)
    if r.status_code != 200:
        return None
    rel = r.json()
    tag = rel.get("tag_name", "")
    if _ver(tag) <= _ver(W.VERSION):
        return None
    assets = {a["name"]: a for a in rel.get("assets", [])}
    if ASSET not in assets:
        return None
    return {"version": tag.lstrip("v"), "notes": (rel.get("body") or "").strip(),
            "url": assets[ASSET]["browser_download_url"], "size": assets[ASSET].get("size", 0),
            "sha_url": assets.get(ASSET + ".sha256", {}).get("browser_download_url")}


def can_self_update() -> bool:
    return getattr(sys, "frozen", False) and sys.platform.startswith("win")


def download_and_restart(info: dict, progress=None) -> None:
    """Download the new exe next to the current one, verify it, then hand over to
    a tiny batch file that swaps the files after this app closes."""
    exe = sys.executable
    folder = os.path.dirname(exe)
    new = os.path.join(folder, "WixLeadBot.new.exe")
    h = hashlib.sha256()
    with requests.get(info["url"], stream=True, timeout=60,
                      headers={"User-Agent": W.USER_AGENT}) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or info.get("size") or 0)
        done = 0
        with open(new, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    if info.get("sha_url"):
        want = requests.get(info["sha_url"], timeout=30,
                            headers={"User-Agent": W.USER_AGENT}).text.split()[0].lower()
        if want != h.hexdigest():
            os.remove(new)
            raise RuntimeError("The download was damaged (fingerprint didn't match). Try again.")
    bat = os.path.join(folder, "_update.bat")
    with open(bat, "w", encoding="utf-8") as f:
        f.write(
            "@echo off\r\n"
            f"set PID={os.getpid()}\r\n"
            ":wait\r\n"
            'tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul && (timeout /t 1 /nobreak >nul & goto wait)\r\n'
            f'move /y "{exe}" "{exe}.old" >nul\r\n'
            f'move /y "{new}" "{exe}" >nul\r\n'
            f'start "" "{exe}"\r\n'
            f'del /q "{exe}.old" >nul 2>nul\r\n'
            '(goto) 2>nul & del "%~f0"\r\n')
    subprocess.Popen(["cmd", "/c", bat], cwd=folder,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
