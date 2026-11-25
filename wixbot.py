#!/usr/bin/env python3
"""
NA Developers - Wix Lead Bot
============================

Finds local businesses in a US state or Canadian province, checks which ones
run their website on Wix, and saves contact details plus a "needs work" score
to a CSV file.

How it works
  1. Discovery: asks OpenStreetMap (free public map data, via the Overpass API)
     for businesses of a category in a state/province that list a website.
     You can also feed it your own list of URLs with --urls-file.
     Or: websites you capture from Yellow Pages with the Chrome helper.
  2. Fast DNS check (free, uses your own internet connection): looks up where
     each domain points. Only domains pointing at Wix servers are opened.
  3. Wix check: opens each homepage and looks for Wix fingerprints, mainly
     "static.wixstatic.com" in the page source, plus Wix-only headers.
  4. Contacts: on Wix sites only, reads the homepage and up to 3 contact/about
     pages for emails, phones and social links. It records the exact page each
     email was found on (keep this - Canada's CASL requires proof).
  5. Score: flags things you can pitch (free wixsite.com address, old
     copyright year, missing SEO title/description, very thin homepage...).

Everything is cached in a local SQLite database, so you can stop and re-run
at any time without re-checking sites.

Examples
  python wixbot.py --list-regions
  python wixbot.py --list-categories
  python wixbot.py --region US-TX --category dentist
  python wixbot.py --region CA-ON --category dentist,lawyer,home_services
  python wixbot.py --region US-FL --category all --tier A
  python wixbot.py --urls-file my_sites.txt --region US-NY --category custom
  python wixbot.py --region US-TX --category dentist --full   (no DNS shortcut)

Data from OpenStreetMap is (c) OpenStreetMap contributors, ODbL licence.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import ipaddress
import json
import os
import random
import re
import socket
import sqlite3
import sys
import threading
import time
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit("Missing package. Run:  pip install requests")

if getattr(sys, "frozen", False):          # running as WixLeadBot.exe
    HERE = os.path.dirname(sys.executable)   # output + database next to the .exe
    BUNDLED = getattr(sys, "_MEIPASS", HERE)
else:
    HERE = os.path.dirname(os.path.abspath(__file__))
    BUNDLED = HERE
VERSION = "1.7.8"
# GitHub "owner/repo" whose Releases hold new versions of WixLeadBot.exe
UPDATE_REPO = "awaisashraf1996/wix-lead-bot"

# The window app sets these to show progress and to stop a run.
LOG_HOOK = None
PROGRESS_HOOK = None          # gets dicts like {"phase","done","total","label"}
STOP = threading.Event()
PAUSE = threading.Event()     # set = paused


# Side tasks (run while a search is going) must not move the main progress bar
# or be held by its Pause button.
SIDE = threading.local()


def wait_if_paused() -> None:
    """Workers call this between steps; it blocks while Pause is on."""
    if getattr(SIDE, "on", False):
        return
    while PAUSE.is_set() and not STOP.is_set():
        time.sleep(0.3)


SEND_STOP = threading.Event()   # stops background sending without stopping a search


def send_stopped() -> bool:
    return STOP.is_set() or SEND_STOP.is_set()


def stopping() -> bool:
    return STOP.is_set() and not getattr(SIDE, "on", False)


def progress(**kw) -> None:
    if getattr(SIDE, "on", False):
        return
    if PROGRESS_HOOK:
        try:
            PROGRESS_HOOK(kw)
        except Exception:
            pass

# --------------------------------------------------------------------------
# Settings you may want to change
# --------------------------------------------------------------------------
USER_AGENT = (
    f"NADevelopersLeadBot/{VERSION} (+https://www.nadevelopers.com; "
    "contact: info@nadevelopers.com)"
)
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
REQUEST_TIMEOUT = 15          # seconds per web page
DEFAULT_WORKERS = 8           # websites checked at the same time
PER_HOST_DELAY = 1.0          # seconds between two requests to the same site
MAX_CONTACT_PAGES = 5         # extra pages read per Wix site (contact/about/booking)
MAX_HTML_BYTES = 3_000_000    # ignore anything bigger than this

# --------------------------------------------------------------------------
# Regions: US states + DC, Canadian provinces/territories (ISO 3166-2 codes)
# --------------------------------------------------------------------------
REGIONS = {
    "US-AL": "Alabama", "US-AK": "Alaska", "US-AZ": "Arizona", "US-AR": "Arkansas",
    "US-CA": "California", "US-CO": "Colorado", "US-CT": "Connecticut",
    "US-DE": "Delaware", "US-DC": "District of Columbia", "US-FL": "Florida",
    "US-GA": "Georgia", "US-HI": "Hawaii", "US-ID": "Idaho", "US-IL": "Illinois",
    "US-IN": "Indiana", "US-IA": "Iowa", "US-KS": "Kansas", "US-KY": "Kentucky",
    "US-LA": "Louisiana", "US-ME": "Maine", "US-MD": "Maryland",
    "US-MA": "Massachusetts", "US-MI": "Michigan", "US-MN": "Minnesota",
    "US-MS": "Mississippi", "US-MO": "Missouri", "US-MT": "Montana",
    "US-NE": "Nebraska", "US-NV": "Nevada", "US-NH": "New Hampshire",
    "US-NJ": "New Jersey", "US-NM": "New Mexico", "US-NY": "New York",
    "US-NC": "North Carolina", "US-ND": "North Dakota", "US-OH": "Ohio",
    "US-OK": "Oklahoma", "US-OR": "Oregon", "US-PA": "Pennsylvania",
    "US-RI": "Rhode Island", "US-SC": "South Carolina", "US-SD": "South Dakota",
    "US-TN": "Tennessee", "US-TX": "Texas", "US-UT": "Utah", "US-VT": "Vermont",
    "US-VA": "Virginia", "US-WA": "Washington", "US-WV": "West Virginia",
    "US-WI": "Wisconsin", "US-WY": "Wyoming",
    "CA-AB": "Alberta", "CA-BC": "British Columbia", "CA-MB": "Manitoba",
    "CA-NB": "New Brunswick", "CA-NL": "Newfoundland and Labrador",
    "CA-NS": "Nova Scotia", "CA-ON": "Ontario", "CA-PE": "Prince Edward Island",
    "CA-QC": "Quebec", "CA-SK": "Saskatchewan", "CA-NT": "Northwest Territories",
    "CA-NU": "Nunavut", "CA-YT": "Yukon",
}

# --------------------------------------------------------------------------
# Wix detection
# --------------------------------------------------------------------------
# Strong signals: any one of these means the site is on Wix.
WIX_HTML_MARKERS = {
    "wixstatic": "static.wixstatic.com",
    "parastorage": "static.parastorage.com",
    "wix_generator": 'content="Wix.com Website Builder"',
    "wix_viewer_model": "wix-viewer-model",
    "wix_essential_viewer": "wix-essential-viewer-model",
    "wixapps": "wixapps.net",
}
WIX_HEADER_MARKERS = {
    "x-wix-request-id": "header_x_wix_request_id",
    "x-wix-renderer-server": "header_x_wix_renderer",
}

# Fast DNS pre-check: Wix custom domains point at Wix's servers.
WIX_DNS_HINTS = ("wixdns.net", "wixsite.com", "wixstudio", "wix.com")
WIX_IP_NETS = [ipaddress.ip_network("185.230.60.0/22")]
DNS_TIMEOUT = 5.0

# --------------------------------------------------------------------------
# Contact extraction
# --------------------------------------------------------------------------
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}")
MAILTO_RE = re.compile(r'mailto:([^"\'?<>\s]+)', re.I)
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?1[\s.\-]?)?\(?([2-9]\d{2})\)?[\s.\-]?([2-9]\d{2})[\s.\-]?(\d{4})(?!\d)"
)
TEL_RE = re.compile(r'href="tel:([^"]+)"', re.I)
SOCIAL_PATTERNS = {
    "facebook": re.compile(r"https?://(?:www\.)?facebook\.com/[A-Za-z0-9._\-/?=]+", re.I),
    "instagram": re.compile(r"https?://(?:www\.)?instagram\.com/[A-Za-z0-9._\-]+", re.I),
    "linkedin": re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/(?:company|in)/[A-Za-z0-9._\-]+", re.I),
    "youtube": re.compile(r"https?://(?:www\.)?youtube\.com/[A-Za-z0-9@._\-/]+", re.I),
    "tiktok": re.compile(r"https?://(?:www\.)?tiktok\.com/@[A-Za-z0-9._\-]+", re.I),
    "x_twitter": re.compile(r"https?://(?:www\.)?(?:twitter|x)\.com/[A-Za-z0-9_]+", re.I),
}
JUNK_EMAIL_DOMAINS = (
    "wix.com", "wixpress.com", "wixsite.com", "sentry.io", "sentry-next.wixpress.com",
    "example.com", "domain.com", "email.com", "yourdomain.com", "mysite.com",
    "parastorage.com", "wixstatic.com", "godaddy.com", "sentry.wixpress.com",
)
JUNK_EMAIL_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js")
SOCIAL_JUNK = ("/wix", "/sharer", "/share", "/plugins", "/tr?", "/dialog", "/intent")

CONTACT_HINTS = ("contact", "about", "get-in-touch", "reach-us", "location", "book",
                 "team", "visit", "hours", "appointment")

TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_STYLE_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.I | re.S)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
META_DESC_RE = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]*content=["\']([^"\']*)', re.I
)
META_DESC_RE2 = re.compile(
    r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*name=["\']description["\']', re.I
)
H1_RE = re.compile(r"<h1[\s>]", re.I)
COPYRIGHT_RE = re.compile(r"(?:©|&copy;|copyright)\s*(?:\d{4}\s*[-–]\s*)?((?:19|20)\d{2})", re.I)
HREF_RE = re.compile(r'href="([^"#]+)"', re.I)

_print_lock = threading.Lock()


def log(msg: str) -> None:
    if LOG_HOOK:
        LOG_HOOK(msg)
        return
    with _print_lock:
        print(msg, flush=True)


# --------------------------------------------------------------------------
# Database (cache + results)
# --------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS businesses (
    key TEXT PRIMARY KEY,           -- osm id or url
    region TEXT, category TEXT, name TEXT, website TEXT,
    phone TEXT, street TEXT, city TEXT, postcode TEXT,
    source TEXT, added_at TEXT
);
CREATE TABLE IF NOT EXISTS sites (
    domain TEXT PRIMARY KEY,
    final_url TEXT, status TEXT, is_wix INTEGER, wix_signals TEXT,
    emails TEXT, email_sources TEXT, phones TEXT, socials TEXT,
    title TEXT, has_meta_desc INTEGER, has_h1 INTEGER, word_count INTEGER,
    copyright_year INTEGER, free_domain INTEGER, score INTEGER, issues TEXT,
    checked_at TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
    region TEXT, category TEXT, source TEXT,
    status TEXT, started_at TEXT, finished_at TEXT,
    businesses INTEGER, wix INTEGER,
    PRIMARY KEY (region, category, source)
);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
"""
# Columns added after v1.2 (added automatically to old databases)
EXTRA_COLUMNS = {
    "businesses": {"domain": "TEXT", "email": "TEXT", "extra": "TEXT"},
    "sites": {"site_name": "TEXT", "meta_desc": "TEXT", "og_image": "TEXT",
              "address": "TEXT", "geo_region": "TEXT", "has_booking": "INTEGER",
              "no_solicit": "INTEGER", "marketing": "TEXT"},
}
SITE_COLS = ["domain", "final_url", "status", "is_wix", "wix_signals", "emails",
             "email_sources", "phones", "socials", "title", "has_meta_desc",
             "has_h1", "word_count", "copyright_year", "free_domain", "score",
             "issues", "checked_at", "site_name", "meta_desc", "og_image",
             "address", "geo_region", "has_booking", "no_solicit", "marketing"]

# Marketing the business already pays for. A business that runs ads has a budget,
# and every ad click lands on the weak website we want to fix.
MARKETING_RE = [
    ("Google Ads", re.compile(r"googleadservices\.com|['\"=]AW-\d{6,}|googleAdsConversion|google_conversion_id", re.I)),
    ("Meta Pixel", re.compile(r"connect\.facebook\.net/[^\"']*/fbevents\.js|fbq\(['\"]init|facebook\.com/tr\?|\"facebookPixel(Id)?\"\s*:\s*\"\d", re.I)),
    ("TikTok Pixel", re.compile(r"analytics\.tiktok\.com|ttq\.load\(", re.I)),
    ("Google Analytics", re.compile(r"gtag/js\?id=(G|UA)-|['\"]G-[A-Z0-9]{8,}['\"]|['\"]UA-\d{4,}-\d+|google-analytics\.com/(analytics|ga)\.js|\"googleAnalytics(Id)?\"\s*:\s*\"[GU]", re.I)),
    ("Tag Manager", re.compile(r"googletagmanager\.com/gtm\.js|['\"]GTM-[A-Z0-9]{4,}", re.I)),
    ("Live chat", re.compile(r"tawk\.to|intercom(cdn)?\.|livechatinc\.com|crisp\.chat|wix-chat|wixChat|drift\.com|tidio", re.I)),
]
ADS_LABELS = ("Google Ads", "Meta Pixel", "TikTok Pixel")


def detect_marketing(html: str) -> list[str]:
    return [name for name, rx in MARKETING_RE if rx.search(html or "")]

# Lead levels (colours are used by the app)
LEVELS = {"super": ("Super", "#E8222B"), "hot": ("Hot", "#F08C2E"),
          "normal": ("Normal", "#1E91A8")}
SUPER_SCORE = 40
HOT_SCORE = 20


def lead_level(score, has_email: bool, has_phone: bool = False) -> str:
    """Super = lots to fix + an email to write to. Hot = clear problems and a way
    to reach them. Everything else is Normal."""
    score = score or 0
    if score >= SUPER_SCORE and has_email:
        return "super"
    if score >= HOT_SCORE and (has_email or has_phone):
        return "hot"
    return "normal"


class DB:
    def __init__(self, path: str):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.executescript(SCHEMA)
        self.lock = threading.RLock()
        self._migrate()

    def _migrate(self) -> None:
        for table, cols in EXTRA_COLUMNS.items():
            have = {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            for col, typ in cols.items():
                if col not in have:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
        rows = self.conn.execute(
            "SELECT key, website FROM businesses WHERE domain IS NULL").fetchall()
        for key, website in rows:
            self.conn.execute("UPDATE businesses SET domain=? WHERE key=?",
                              (domain_of(website), key))
        # v1.4.1: free wixsite.com sites are keyed by account + site name
        rows = self.conn.execute("SELECT key, website, domain FROM businesses"
                                 " WHERE website LIKE '%.wixsite.com%'").fetchall()
        for key, website, old in rows:
            new = domain_of(website)
            if new == old:
                continue
            self.conn.execute("UPDATE businesses SET domain=? WHERE key=?", (new, key))
            if not self.conn.execute("SELECT 1 FROM sites WHERE domain=?", (new,)).fetchone():
                self.conn.execute("UPDATE OR IGNORE sites SET domain=? WHERE domain=?", (new, old))
                try:
                    self.conn.execute("UPDATE OR IGNORE outreach SET domain=? WHERE domain=?", (new, old))
                    self.conn.execute("UPDATE messages SET domain=? WHERE domain=?", (new, old))
                except sqlite3.OperationalError:
                    pass   # outreach tables not created yet
        self.conn.execute("CREATE INDEX IF NOT EXISTS ix_biz_domain ON businesses(domain)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS ix_biz_source ON businesses(source)")
        self.conn.commit()

    # ---- generic helpers
    def q(self, sql: str, args=()) -> list:
        with self.lock:
            return self.conn.execute(sql, args).fetchall()

    def x(self, sql: str, args=()) -> None:
        with self.lock:
            self.conn.execute(sql, args)
            self.conn.commit()

    def get_kv(self, key: str, default=None):
        r = self.q("SELECT value FROM kv WHERE key=?", (key,))
        return r[0][0] if r else default

    def set_kv(self, key: str, value) -> None:
        self.x("INSERT OR REPLACE INTO kv VALUES (?,?)", (key, str(value)))

    # ---- businesses / sites
    def add_business(self, b: dict) -> bool:
        with self.lock:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO businesses (key, region, category, name, website,"
                " phone, street, city, postcode, source, added_at, domain, email, extra)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (b["key"], b["region"], b["category"], b["name"], b["website"],
                 b.get("phone", ""), b.get("street", ""), b.get("city", ""),
                 b.get("postcode", ""), b["source"], now(), domain_of(b["website"]),
                 b.get("email", ""), json.dumps(b.get("extra") or {})),
            )
            self.conn.commit()
            return cur.rowcount > 0

    def site_checked(self, domain: str, full: bool = False) -> bool:
        row = self.q("SELECT status FROM sites WHERE domain=?", (domain,))
        if not row or (row[0][0] or "").startswith("error") or row[0][0] == "dns_failed":
            return False
        if full and row[0][0] == "dns_not_wix":   # only skipped by DNS before
            return False
        return True

    def businesses_by_source(self, source: str) -> list[dict]:
        rows = self.q("SELECT key, region, category, name, website FROM businesses"
                      " WHERE source=?", (source,))
        return [{"key": k, "region": r, "category": c, "name": n, "website": w}
                for k, r, c, n, w in rows]

    def save_site(self, r: dict) -> None:
        with self.lock:
            self.conn.execute(
                f"INSERT OR REPLACE INTO sites ({','.join(SITE_COLS)}) "
                f"VALUES ({','.join('?' * len(SITE_COLS))})",
                [r.get(c) for c in SITE_COLS],
            )
            if r.get("geo_region"):   # fill in unknown regions from the website
                self.conn.execute(
                    "UPDATE businesses SET region=? WHERE domain=? AND"
                    " (region IS NULL OR region='' OR region='UNKNOWN')",
                    (r["geo_region"], r["domain"]))
            self.conn.commit()

    def lead_records(self, where: str = "", args=()) -> list[dict]:
        """One record per Wix website, joined with its best business row."""
        sql = f"""
            SELECT s.*, b.key AS biz_key, b.region, b.category, b.name, b.website,
                   b.phone AS listed_phone, b.street, b.city, b.postcode, b.source,
                   b.email AS listed_email, b.added_at
            FROM sites s JOIN businesses b ON b.domain = s.domain
            WHERE s.is_wix = 1 {('AND ' + where) if where else ''}
            GROUP BY s.domain
            ORDER BY s.score DESC, b.name"""
        with self.lock:
            cur = self.conn.execute(sql, args)
            names = [d[0] for d in cur.description]
            rows = [dict(zip(names, r)) for r in cur.fetchall()]
        for r in rows:
            r["level"] = lead_level(r.get("score"), bool(r.get("emails")),
                                    bool(r.get("phones") or r.get("listed_phone")))
            r["region_name"] = REGIONS.get(r.get("region") or "", r.get("region") or "")
        return rows

    def leads(self, region: str | None, categories: list[str] | None,
              source: str | None = None):
        conds, args = [], []
        if region:
            conds.append("b.region=?"); args.append(region)
        if categories:
            conds.append(f"b.category IN ({','.join('?' * len(categories))})")
            args += categories
        if source:
            conds.append("b.source=?"); args.append(source)
        out = []
        for r in self.lead_records(" AND ".join(conds), args):
            out.append({
                "lead_level": LEVELS[r["level"]][0],
                "region": r["region"], "region_name": r["region_name"],
                "category": r["category"], "business_name": r["name"] or r.get("site_name"),
                "website": r["final_url"] or r["website"],
                "free_wix_domain": "yes" if r["free_domain"] else "no",
                "emails": r["emails"], "email_found_on": r["email_sources"],
                "phones_on_site": r["phones"], "phone_listed": r["listed_phone"],
                "street": r["street"] or r.get("address") or "", "city": r["city"],
                "postcode": r["postcode"], "socials": r["socials"],
                "page_title": r["title"], "copyright_year": r["copyright_year"] or "",
                "opportunity_score": r["score"], "issues": r["issues"],
                "wix_signals": r["wix_signals"], "source": r["source"],
                "source_id": r["biz_key"], "checked_at": r["checked_at"],
            })
        return out

    def stats(self):
        total = self.q("SELECT COUNT(*) FROM sites")[0][0]
        wix = self.q("SELECT COUNT(*) FROM sites WHERE is_wix=1")[0][0]
        return total, wix

    # ---- job history ("don't repeat a search")
    def job_done(self, region: str, category: str, source: str) -> bool:
        r = self.q("SELECT status FROM jobs WHERE region=? AND category=? AND source=?",
                   (region, category, source))
        return bool(r) and r[0][0] == "done"

    def job_start(self, region, category, source) -> None:
        self.x("INSERT OR REPLACE INTO jobs VALUES (?,?,?,?,?,?,?,?)",
               (region, category, source, "running", now(), None, 0, 0))

    def job_finish(self, region, category, source, status, businesses, wix) -> None:
        self.x("UPDATE jobs SET status=?, finished_at=?, businesses=?, wix=?"
               " WHERE region=? AND category=? AND source=?",
               (status, now(), businesses, wix, region, category, source))

    def job_table(self) -> list[dict]:
        with self.lock:
            cur = self.conn.execute("SELECT * FROM jobs ORDER BY region, category")
            names = [d[0] for d in cur.description]
            return [dict(zip(names, r)) for r in cur.fetchall()]

    def clear_jobs(self, region: str, category: str | None = None) -> None:
        if category:
            self.x("DELETE FROM jobs WHERE region=? AND category=?", (region, category))
        else:
            self.x("DELETE FROM jobs WHERE region=?", (region,))

    def wix_count(self, domains: list[str]) -> int:
        n = 0
        for i in range(0, len(domains), 500):
            chunk = domains[i:i + 500]
            n += self.q(f"SELECT COUNT(*) FROM sites WHERE is_wix=1 AND domain IN"
                        f" ({','.join('?' * len(chunk))})", chunk)[0][0]
        return n


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def domain_of(url: str) -> str:
    try:
        host = urlparse(normalise_url(url)).hostname or ""
    except ValueError:
        return ""
    host = host.lower()
    host = host[4:] if host.startswith("www.") else host
    if host.endswith(".wixsite.com"):
        # one Wix account can hold several free sites: user.wixsite.com/bakery,
        # user.wixsite.com/salon - keep them apart
        try:
            first = urlparse(normalise_url(url)).path.strip("/").split("/")[0].lower()
        except ValueError:
            first = ""
        return f"{host}/{first}" if first else host
    return host


def normalise_url(url: str) -> str:
    url = (url or "").strip().split()[0] if url and url.strip() else ""
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.I):
        url = "http://" + url
    return url


# --------------------------------------------------------------------------
# Discovery: OpenStreetMap / Overpass
# --------------------------------------------------------------------------
def build_overpass_query(region: str, tag_pairs: list[list[str]]) -> str:
    lines = []
    for key, value in tag_pairs:
        for site_key in ("website", "contact:website", "url"):
            lines.append(f'  nwr["{key}"="{value}"]["{site_key}"](area.r);')
    body = "\n".join(lines)
    return (
        "[out:json][timeout:300];\n"
        f'area["ISO3166-2"="{region}"]["admin_level"="4"]->.r;\n'
        f"(\n{body}\n);\n"
        "out center tags;"
    )


def overpass(query: str, session: requests.Session) -> dict:
    last_err = None
    for attempt in range(4):
        endpoint = OVERPASS_ENDPOINTS[attempt % len(OVERPASS_ENDPOINTS)]
        try:
            r = session.post(endpoint, data={"data": query}, timeout=360)
            if r.status_code == 200:
                return r.json()
            last_err = f"HTTP {r.status_code}"
            if r.status_code in (429, 503, 504):
                wait = 30 * (attempt + 1)
                log(f"  OpenStreetMap is busy ({last_err}); waiting {wait}s...")
                time.sleep(wait)
                continue
        except (requests.RequestException, ValueError) as e:
            last_err = str(e)
            time.sleep(10)
    raise RuntimeError(f"OpenStreetMap query failed: {last_err}")


def elements_to_businesses(data: dict, region: str, category: str) -> list[dict]:
    out, seen = [], set()
    for el in data.get("elements", []):
        t = el.get("tags", {})
        website = t.get("website") or t.get("contact:website") or t.get("url") or ""
        website = normalise_url(website.split(";")[0])
        if not website or domain_of(website) in seen:
            continue
        seen.add(domain_of(website))
        out.append({
            "key": f"osm:{el.get('type')}/{el.get('id')}",
            "region": region, "category": category,
            "name": t.get("name", ""),
            "website": website,
            "phone": t.get("phone") or t.get("contact:phone", ""),
            "street": " ".join(x for x in (t.get("addr:housenumber", ""), t.get("addr:street", "")) if x),
            "city": t.get("addr:city", ""),
            "postcode": t.get("addr:postcode", ""),
            "source": "openstreetmap",
        })
    return out


def discover(region: str, category: str, cat_cfg: dict, session, db: DB) -> list[dict]:
    log(f"\n[{region} / {category}] Asking OpenStreetMap for {cat_cfg['label']}...")
    data = overpass(build_overpass_query(region, cat_cfg["tags"]), session)
    found = elements_to_businesses(data, region, category)
    for b in found:
        db.add_business(b)
    log(f"  {len(found)} businesses with a website found.")
    return found


def load_url_file(path: str, region: str, category: str, db: DB) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            url = normalise_url(parts[0])
            if not url:
                continue
            b = {"key": f"url:{domain_of(url)}", "region": region, "category": category,
                 "name": parts[1] if len(parts) > 1 else "", "website": url,
                 "source": "url-file"}
            db.add_business(b)
            out.append(b)
    log(f"Loaded {len(out)} URLs from {path}")
    return out


# --------------------------------------------------------------------------
# Fetching (polite)
# --------------------------------------------------------------------------
class PoliteFetcher:
    def __init__(self):
        self.local = threading.local()
        self.host_last: dict[str, float] = {}
        self.host_lock = threading.Lock()
        self.robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def session(self) -> requests.Session:
        if not hasattr(self.local, "s"):
            s = requests.Session()
            s.headers.update({"User-Agent": USER_AGENT,
                              "Accept": "text/html,application/xhtml+xml",
                              "Accept-Language": "en-US,en;q=0.8"})
            self.local.s = s
        return self.local.s

    def _wait_for_host(self, host: str) -> None:
        with self.host_lock:
            last = self.host_last.get(host, 0)
            wait = PER_HOST_DELAY - (time.time() - last)
            self.host_last[host] = time.time() + max(wait, 0)
        if wait > 0:
            time.sleep(wait + random.uniform(0, 0.3))

    def allowed(self, url: str) -> bool:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self.robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.session().get(base + "/robots.txt", timeout=REQUEST_TIMEOUT)
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except requests.RequestException:
                rp.parse([])
            self.robots[base] = rp
        rp = self.robots[base]
        return rp.can_fetch(USER_AGENT, url) if rp else True

    def get(self, url: str):
        host = urlparse(url).netloc
        if not self.allowed(url):
            return None, "blocked_by_robots"
        self._wait_for_host(host)
        try:
            r = self.session().get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True,
                                   stream=True)
            ctype = r.headers.get("content-type", "")
            if "html" not in ctype.lower():
                r.close()
                return r, "not_html"
            content = r.raw.read(MAX_HTML_BYTES, decode_content=True)
            r._content = content
            return r, "ok"
        except requests.RequestException as e:
            return None, f"error: {type(e).__name__}"


# --------------------------------------------------------------------------
# Page analysis
# --------------------------------------------------------------------------
def detect_wix(html: str, headers) -> list[str]:
    signals = [name for name, marker in WIX_HTML_MARKERS.items() if marker in html]
    lower_headers = {k.lower(): v for k, v in (headers or {}).items()}
    for h, name in WIX_HEADER_MARKERS.items():
        if h in lower_headers:
            signals.append(name)
    if "pepyaka" in lower_headers.get("server", "").lower():
        signals.append("header_server_pepyaka")
    return signals


def clean_email(e: str) -> str | None:
    e = e.strip().strip(".").lower()
    e = re.sub(r"^(?:u003e|%20|20)", "", e)
    if e.endswith(JUNK_EMAIL_EXT):
        return None
    domain = e.split("@")[-1]
    if any(domain == d or domain.endswith("." + d) for d in JUNK_EMAIL_DOMAINS):
        return None
    if re.match(r"^[0-9a-f]{20,}@", e):  # hashed ids
        return None
    return e


OBFUSCATED_EMAIL_RE = re.compile(
    r"([A-Za-z0-9._%+\-]+)\s*(?:\[|\(|\{)?\s*(?:at|AT)\s*(?:\]|\)|\})?\s*"
    r"([A-Za-z0-9\-]+(?:\s*(?:\[|\(|\{)?\s*(?:dot|DOT)\s*(?:\]|\)|\})?\s*[A-Za-z0-9\-]+)+)")


def extract_emails(html: str) -> list[str]:
    found = []
    for m in MAILTO_RE.findall(html):
        found.append(requests.utils.unquote(m))
    found += EMAIL_RE.findall(html)
    # "name [at] domain [dot] com" written to dodge spam bots
    for user, rest in OBFUSCATED_EMAIL_RE.findall(visible_text(html)):
        if re.search(r"(?:dot|DOT)", rest):
            dom = re.sub(r"\s*(?:\[|\(|\{)?\s*(?:dot|DOT)\s*(?:\]|\)|\})?\s*", ".", rest)
            found.append(f"{user}@{dom}")
    out = []
    for e in found:
        c = clean_email(e)
        if c and c not in out and EMAIL_RE.fullmatch(c):
            out.append(c)
    return out


JSONLD_RE = re.compile(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.I | re.S)
OG_RE = re.compile(r'<meta[^>]+property=["\']og:(site_name|image|description)["\'][^>]*'
                   r'content=["\']([^"\']*)', re.I)


def extract_structured(html: str) -> dict:
    """Business details many Wix sites publish for Google (schema.org JSON-LD + og tags)."""
    info: dict = {}
    for prop, val in OG_RE.findall(html):
        info.setdefault("og_" + prop.lower(), val.strip())
    for block in JSONLD_RE.findall(html):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, list):
                stack.extend(d); continue
            if not isinstance(d, dict):
                continue
            if "@graph" in d:
                stack.extend(d["@graph"] if isinstance(d["@graph"], list) else [d["@graph"]])
            if d.get("email") and "email" not in info:
                info["email"] = str(d["email"]).replace("mailto:", "")
            if d.get("telephone") and "telephone" not in info:
                info["telephone"] = str(d["telephone"])
            if d.get("name") and "name" not in info and d.get("@type") not in ("WebSite", "WebPage"):
                info["name"] = str(d["name"])
            addr = d.get("address")
            if isinstance(addr, dict) and "address" not in info:
                parts = [addr.get(k) for k in ("streetAddress", "addressLocality",
                                               "addressRegion", "postalCode")]
                info["address"] = ", ".join(str(x) for x in parts if x)
                info["addressRegion"] = str(addr.get("addressRegion") or "")
                info["addressCountry"] = str(addr.get("addressCountry") or "")
    return info


# Canadian area codes (all other North American codes are treated as US)
CA_AREA_CODES = {
    "204", "226", "236", "249", "250", "257", "263", "289", "306", "343", "354", "365",
    "367", "368", "382", "403", "416", "418", "428", "431", "437", "438", "450", "468",
    "474", "506", "514", "519", "548", "579", "581", "584", "587", "604", "613", "639",
    "647", "672", "683", "705", "709", "742", "753", "778", "780", "782", "807", "819",
    "825", "867", "873", "879", "902", "905"}
STATE_NAMES = {v.lower(): k for k, v in REGIONS.items()}
ADDRESS_RE = re.compile(
    r"\b([A-Z][A-Za-z .'-]{2,30}),?\s+(" + "|".join(sorted({k[3:] for k in REGIONS})) +
    r")\.?\s+(\d{5}(?:-\d{4})?|[A-Z]\d[A-Z]\s?\d[A-Z]\d)\b")


def guess_site_region(html: str, structured: dict, phones: list[str]) -> str:
    """Work out the US state / Canadian province from what the website says."""
    reg = (structured.get("addressRegion") or "").strip()
    country = (structured.get("addressCountry") or "").upper()
    if reg:
        code = reg.upper().replace(".", "")
        pre = "CA-" if country in ("CA", "CAN", "CANADA") else "US-"
        if pre + code in REGIONS:
            return pre + code
        if "US-" + code in REGIONS:
            return "US-" + code
        if "CA-" + code in REGIONS:
            return "CA-" + code
        if reg.lower() in STATE_NAMES:
            return STATE_NAMES[reg.lower()]
    m = ADDRESS_RE.search(visible_text(html)[:200000])
    if m:
        code, post = m.group(2), m.group(3)
        if re.match(r"[A-Z]\d[A-Z]", post) and "CA-" + code in REGIONS:
            return "CA-" + code
        if post[0].isdigit() and "US-" + code in REGIONS:
            return "US-" + code
    if phones:
        ac = re.sub(r"\D", "", phones[0])[:3]
        return "CA-?" if ac in CA_AREA_CODES else "US-?"
    return ""


NO_SOLICIT_RE = re.compile(r"\bno (unsolicited|solicitation|soliciting|solicitors|sales (calls|emails))\b|"
                           r"\bdo not solicit\b|\bnot accept(ing)? (unsolicited|solicitation)", re.I)

# Main time zone of each state/province (for sending in their business hours)
REGION_TZ = {
    **{f"US-{c}": "America/New_York" for c in "CT DE DC FL GA IN KY ME MD MA MI NH NJ NY NC OH PA RI SC VT VA WV".split()},
    **{f"US-{c}": "America/Chicago" for c in "AL AR IL IA KS LA MN MS MO NE ND OK SD TN TX WI".split()},
    **{f"US-{c}": "America/Denver" for c in "CO ID MT NM UT WY".split()},
    "US-AZ": "America/Phoenix",
    **{f"US-{c}": "America/Los_Angeles" for c in "CA NV OR WA".split()},
    "US-AK": "America/Anchorage", "US-HI": "Pacific/Honolulu",
    "CA-BC": "America/Vancouver", "CA-YT": "America/Whitehorse", "CA-AB": "America/Edmonton",
    "CA-NT": "America/Yellowknife", "CA-SK": "America/Regina", "CA-MB": "America/Winnipeg",
    "CA-ON": "America/Toronto", "CA-QC": "America/Toronto", "CA-NU": "America/Iqaluit",
    "CA-NB": "America/Halifax", "CA-NS": "America/Halifax", "CA-PE": "America/Halifax",
    "CA-NL": "America/St_Johns",
}


BOOKING_RE = re.compile(r'href="[^"]*(book-online|booking|/book|schedule|appointment)', re.I)


def extract_phones(html: str) -> list[str]:
    raw = [t for t in TEL_RE.findall(html)]
    text = visible_text(html)
    raw += ["".join(m) for m in PHONE_RE.findall(text)]
    out = []
    for p in raw:
        digits = re.sub(r"\D", "", p)
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        if len(digits) != 10:
            continue
        fmt = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        if fmt not in out:
            out.append(fmt)
    return out[:3]


def extract_socials(html: str) -> dict[str, str]:
    out = {}
    for name, rx in SOCIAL_PATTERNS.items():
        for m in rx.findall(html):
            low = m.lower()
            if any(j in low for j in SOCIAL_JUNK):
                continue
            out[name] = m.rstrip("/\\\"'")
            break
    return out


def visible_text(html: str) -> str:
    text = SCRIPT_STYLE_RE.sub(" ", html)
    text = TAG_RE.sub(" ", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def find_contact_links(html: str, base_url: str) -> list[str]:
    base_host = urlparse(base_url).netloc
    links = []
    for href in HREF_RE.findall(html):
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        full = urljoin(base_url, href)
        p = urlparse(full)
        if p.netloc != base_host:
            continue
        path = p.path.lower()
        if any(h in path for h in CONTACT_HINTS) and full not in links:
            links.append(full.split("#")[0])
    # Wix sites usually use these paths even when not linked plainly
    for guess in ("/contact", "/contact-us", "/about"):
        g = urljoin(base_url, guess)
        if g not in links:
            links.append(g)
    return links[:MAX_CONTACT_PAGES]


def score_site(home_html: str, final_url: str, emails: list[str]) -> tuple[int, list[str], dict]:
    issues, score = [], 0
    host = urlparse(final_url).netloc.lower()
    free = host.endswith("wixsite.com") or host.endswith("wixstudio.io") or host.endswith("wixstudio.com")
    if free:
        score += 30
        issues.append("Free Wix address (no custom domain)")

    title_m = TITLE_RE.search(home_html)
    title = re.sub(r"\s+", " ", title_m.group(1)).strip() if title_m else ""
    generic_titles = {"home", "home | my site", "my site", "", "home page"}
    if title.lower() in generic_titles or title.lower().startswith(("home | my site", "my site")):
        score += 15
        issues.append("Generic or missing page title (weak SEO)")

    has_desc = bool(META_DESC_RE.search(home_html) or META_DESC_RE2.search(home_html))
    if not has_desc:
        score += 10
        issues.append("No meta description")

    has_h1 = bool(H1_RE.search(home_html))
    if not has_h1:
        score += 5
        issues.append("No H1 heading on homepage")

    words = len(visible_text(home_html).split())
    if words < 150:
        score += 10
        issues.append(f"Thin homepage ({words} words)")

    years = [int(y) for y in COPYRIGHT_RE.findall(home_html)]
    cyear = max(years) if years else None
    this_year = dt.date.today().year
    if cyear and cyear <= this_year - 2:
        score += 15
        issues.append(f"Copyright year {cyear} (site not updated)")

    if "my site" in title.lower() or "wix.com" in title.lower():
        score += 5

    if not emails:
        issues.append("No email found on site (use contact form or phone)")

    meta = {"title": title[:200], "has_meta_desc": int(has_desc), "has_h1": int(has_h1),
            "word_count": words, "copyright_year": cyear, "free_domain": int(free)}
    return min(score, 100), issues, meta


def dns_wix_hint(domain: str) -> str:
    """Free DNS lookup through the computer's own resolver.
    Returns 'wix', 'not_wix' or 'unknown' (domain didn't resolve)."""
    resolved = False
    for name in ("www." + domain, domain):
        try:
            canon, aliases, ips = socket.gethostbyname_ex(name)
        except (socket.gaierror, socket.herror, UnicodeError, OSError):
            continue
        resolved = True
        names = [canon] + list(aliases)
        if any(h in n.lower() for n in names for h in WIX_DNS_HINTS):
            return "wix"
        for ip in ips:
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if any(addr in net for net in WIX_IP_NETS):
                return "wix"
    return "not_wix" if resolved else "unknown"


def check_site(website: str, fetcher: PoliteFetcher) -> dict:
    domain = domain_of(website)
    result = {"domain": domain, "status": "error", "is_wix": 0, "checked_at": now()}
    url = normalise_url(website)
    resp, status = fetcher.get(url)
    if resp is None or status != "ok":
        # retry once on https if http failed
        if url.startswith("http://"):
            resp, status = fetcher.get("https://" + url[len("http://"):])
        if resp is None or status != "ok":
            result["status"] = status
            return result

    html = resp.text or ""
    final_url = resp.url
    signals = detect_wix(html, resp.headers)
    result.update({"final_url": final_url, "status": "ok", "wix_signals": ",".join(signals)})
    if not signals:
        result["is_wix"] = 0
        return result

    result["is_wix"] = 1
    emails = extract_emails(html)
    sources = {e: final_url for e in emails}
    phones = extract_phones(html)
    socials = extract_socials(html)
    structured = extract_structured(html)
    has_booking = bool(BOOKING_RE.search(html)) or "wix-bookings" in html

    for link in find_contact_links(html, final_url):
        r2, st2 = fetcher.get(link)
        if r2 is None or st2 != "ok" or r2.status_code >= 400:
            continue
        h2 = r2.text or ""
        if BOOKING_RE.search(h2):
            has_booking = True
        for k, v in extract_structured(h2).items():
            structured.setdefault(k, v)
        for e in extract_emails(h2):
            if e not in emails:
                emails.append(e)
                sources[e] = r2.url
        for p in extract_phones(h2):
            if p not in phones:
                phones.append(p)
        for k, v in extract_socials(h2).items():
            socials.setdefault(k, v)

    se = clean_email(structured.get("email", "")) if structured.get("email") else None
    if se and se not in emails:
        emails.append(se)
        sources[se] = final_url
    if structured.get("telephone"):
        for p in extract_phones(f'href="tel:{structured["telephone"]}"'):
            if p not in phones:
                phones.insert(0, p)
    score, issues, meta = score_site(html, final_url, emails)
    marketing = detect_marketing(html)
    if any(m in ADS_LABELS for m in marketing):
        score += 8      # paying for ads = has budget, and the ads land on this website
    if not has_booking:
        issues.append("No online booking button found")
    desc_m = META_DESC_RE.search(html) or META_DESC_RE2.search(html)
    result.update({
        "site_name": (structured.get("og_site_name") or structured.get("name") or "")[:150],
        "meta_desc": (desc_m.group(1) if desc_m else structured.get("og_description", ""))[:400],
        "og_image": structured.get("og_image", "")[:500],
        "address": structured.get("address", "")[:250],
        "geo_region": guess_site_region(html, structured, phones),
        "has_booking": int(has_booking),
        "no_solicit": int(bool(NO_SOLICIT_RE.search(visible_text(html)))),
        "marketing": "; ".join(marketing),
    })
    result.update({
        "emails": "; ".join(emails[:5]),
        "email_sources": "; ".join(f"{e} <- {sources[e]}" for e in emails[:5]),
        "phones": "; ".join(phones[:3]),
        "socials": "; ".join(f"{k}: {v}" for k, v in socials.items()),
        "score": score, "issues": "; ".join(issues), **meta,
    })
    return result


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def load_categories() -> dict:
    # An edited categories.json next to the program wins over the built-in one.
    path = os.path.join(HERE, "categories.json")
    if not os.path.exists(path):
        path = os.path.join(BUNDLED, "categories.json")
    with open(path, encoding="utf-8") as f:
        cats = json.load(f)
    cats.pop("_note", None)
    return cats


def export_csv(rows: list[dict], path: str) -> None:
    if not rows:
        log("No Wix leads to export yet.")
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    log(f"\nSaved {len(rows)} Wix leads to {path}")


def run_checks(businesses: list[dict], db: DB, workers: int, recheck: bool,
               full: bool = False, step_label: str = "") -> tuple[int, int]:
    """Check websites. Returns (checked, wix_found)."""
    fetcher = PoliteFetcher()
    todo, seen = [], set()
    for b in businesses:
        d = domain_of(b["website"])
        if not d or d in seen:
            continue
        seen.add(d)
        if recheck or not db.site_checked(d, full):
            todo.append(b)
    mode = "full check" if full else "fast DNS check first"
    log(f"Checking {len(todo)} websites, {mode} "
        f"({len(seen) - len(todo)} already checked before)...")
    done = wix = skipped = 0
    socket.setdefaulttimeout(DNS_TIMEOUT)
    progress(phase="check", done=0, total=len(todo), label=step_label)

    def guarded(website: str):
        wait_if_paused()
        if STOP.is_set():
            return None
        if not full:
            d = domain_of(website)
            if any(x in d for x in (".wixsite.com", "wixstudio.io", "wixstudio.com")):
                return check_site(website, fetcher)
            hint = dns_wix_hint(d)
            if hint == "not_wix":
                return {"domain": d, "status": "dns_not_wix", "is_wix": 0,
                        "checked_at": now()}
            if hint == "unknown":
                return {"domain": d, "status": "dns_failed", "is_wix": 0,
                        "checked_at": now()}
        return check_site(website, fetcher)

    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = {pool.submit(guarded, b["website"]): b for b in todo}
        for fut in as_completed(futures):
            b = futures[fut]
            try:
                r = fut.result()
            except Exception as e:  # keep going on any unexpected error
                r = {"domain": domain_of(b["website"]), "status": f"error: {e}",
                     "is_wix": 0, "checked_at": now()}
            if r is None:          # skipped because Stop was pressed
                continue
            db.save_site(r)
            done += 1
            if r.get("status") in ("dns_not_wix", "dns_failed"):
                skipped += 1
            if r.get("is_wix"):
                wix += 1
                log(f"  WIX  [{r.get('score', 0):>3}] {b['name'] or r['domain']}  "
                    f"{r.get('emails') or '-'}")
            progress(phase="check", done=done, total=len(todo), label=step_label, wix=wix)
            if STOP.is_set():
                break
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    log(f"{'Stopped' if STOP.is_set() else 'Done'}: {done} checked, {wix} on Wix"
        f"{f' ({skipped} skipped by the DNS check)' if skipped else ''}.")
    return done, wix


# --------------------------------------------------------------------------
# Deep source: Overture Maps Places (free open data, tens of millions of places)
# --------------------------------------------------------------------------
# Rough bounding boxes (west, south, east, north) used to read only the part of
# the dataset that covers a state/province.
REGION_BBOX = {
    "US-AL": (-88.5, 30.1, -84.9, 35.0), "US-AK": (-179.2, 51.2, -129.9, 71.4),
    "US-AZ": (-114.9, 31.3, -109.0, 37.0), "US-AR": (-94.7, 33.0, -89.6, 36.5),
    "US-CA": (-124.5, 32.5, -114.1, 42.0), "US-CO": (-109.1, 36.9, -102.0, 41.0),
    "US-CT": (-73.8, 40.9, -71.8, 42.1), "US-DE": (-75.8, 38.4, -75.0, 39.9),
    "US-DC": (-77.2, 38.8, -76.9, 39.0), "US-FL": (-87.7, 24.4, -80.0, 31.0),
    "US-GA": (-85.7, 30.3, -80.8, 35.0), "US-HI": (-160.3, 18.9, -154.8, 22.3),
    "US-ID": (-117.3, 41.9, -111.0, 49.0), "US-IL": (-91.6, 36.9, -87.0, 42.5),
    "US-IN": (-88.1, 37.7, -84.8, 41.8), "US-IA": (-96.7, 40.3, -90.1, 43.6),
    "US-KS": (-102.1, 36.9, -94.6, 40.0), "US-KY": (-89.6, 36.4, -81.9, 39.2),
    "US-LA": (-94.1, 28.9, -88.8, 33.1), "US-ME": (-71.1, 42.9, -66.9, 47.5),
    "US-MD": (-79.5, 37.9, -75.0, 39.8), "US-MA": (-73.6, 41.2, -69.9, 42.9),
    "US-MI": (-90.5, 41.6, -82.1, 48.3), "US-MN": (-97.3, 43.4, -89.4, 49.4),
    "US-MS": (-91.7, 30.1, -88.0, 35.0), "US-MO": (-95.8, 35.9, -89.1, 40.7),
    "US-MT": (-116.1, 44.3, -104.0, 49.0), "US-NE": (-104.1, 39.9, -95.3, 43.1),
    "US-NV": (-120.1, 35.0, -114.0, 42.0), "US-NH": (-72.6, 42.6, -70.6, 45.4),
    "US-NJ": (-75.6, 38.9, -73.8, 41.4), "US-NM": (-109.1, 31.3, -103.0, 37.0),
    "US-NY": (-79.8, 40.4, -71.8, 45.1), "US-NC": (-84.4, 33.8, -75.4, 36.6),
    "US-ND": (-104.1, 45.9, -96.5, 49.0), "US-OH": (-84.9, 38.4, -80.5, 42.0),
    "US-OK": (-103.1, 33.6, -94.4, 37.0), "US-OR": (-124.6, 41.9, -116.4, 46.3),
    "US-PA": (-80.6, 39.7, -74.7, 42.3), "US-RI": (-71.9, 41.1, -71.1, 42.1),
    "US-SC": (-83.4, 32.0, -78.5, 35.3), "US-SD": (-104.1, 42.4, -96.4, 45.95),
    "US-TN": (-90.4, 34.9, -81.6, 36.7), "US-TX": (-106.7, 25.8, -93.5, 36.5),
    "US-UT": (-114.1, 36.9, -109.0, 42.0), "US-VT": (-73.5, 42.7, -71.4, 45.1),
    "US-VA": (-83.7, 36.5, -75.2, 39.5), "US-WA": (-124.8, 45.5, -116.9, 49.0),
    "US-WV": (-82.7, 37.2, -77.7, 40.7), "US-WI": (-92.9, 42.4, -86.2, 47.1),
    "US-WY": (-111.1, 40.9, -104.0, 45.0),
    "CA-AB": (-120.0, 49.0, -110.0, 60.0), "CA-BC": (-139.1, 48.2, -114.0, 60.0),
    "CA-MB": (-102.1, 48.9, -88.9, 60.0), "CA-NB": (-69.1, 44.5, -63.7, 48.1),
    "CA-NL": (-67.9, 46.6, -52.6, 60.4), "CA-NS": (-66.4, 43.4, -59.6, 47.1),
    "CA-ON": (-95.2, 41.6, -74.3, 56.9), "CA-PE": (-64.5, 45.9, -61.9, 47.1),
    "CA-QC": (-79.8, 45.0, -57.1, 62.6), "CA-SK": (-110.0, 49.0, -101.3, 60.0),
    "CA-NT": (-136.5, 60.0, -102.0, 78.8), "CA-NU": (-120.7, 51.6, -61.2, 83.2),
    "CA-YT": (-141.0, 60.0, -123.8, 69.7),
}
OVERTURE_STAC = "https://stac.overturemaps.org/catalog.json"
OVERTURE_BASE = "s3://overturemaps-us-west-2/release/{release}/theme=places/type=place/*"


def overture_release(session) -> str:
    try:
        r = session.get(OVERTURE_STAC, timeout=30)
        rel = r.json().get("latest")
        if rel:
            return str(rel)
    except (requests.RequestException, ValueError):
        pass
    raise RuntimeError("could not find the latest Overture release (no internet?)")


def overture_files(session, release: str, bbox: tuple) -> list[str]:
    """Use Overture's STAC index to pick only the data files that cover the map
    box, instead of scanning all of them. Returns [] if the index can't be read."""
    from urllib.parse import urljoin
    base = f"https://stac.overturemaps.org/{release}/places/place/"
    w, so, e, n = bbox
    files = []
    try:
        col = session.get(base + "collection.json", timeout=30).json()
        for ln in col.get("links", []):
            if ln.get("rel") != "item":
                continue
            item = session.get(urljoin(base, ln["href"]), timeout=30).json()
            b = item.get("bbox")
            if b and len(b) >= 4 and (b[0] > e or b[2] < w or b[1] > n or b[3] < so):
                continue            # this file is somewhere else on the map
            hrefs = [a.get("href", "") for a in (item.get("assets") or {}).values()]
            hrefs = [h for h in hrefs if ".parquet" in h]
            if hrefs:
                files.append(next((h for h in hrefs if h.startswith("s3://")), hrefs[0]))
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return []
    return files


def _overture_connect():
    try:
        import duckdb  # noqa: WPS433
    except ImportError:
        raise RuntimeError("the 'duckdb' package is missing (pip install duckdb)")
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
    try:
        con.execute("SET s3_access_key_id=''; SET s3_secret_access_key='';")
    except Exception:
        pass
    return con


def discover_overture(region: str, categories: list[str], cats: dict, db: DB,
                      session) -> dict[str, list[dict]]:
    """One pass over Overture for a region, returns {category: [businesses]}."""
    if region not in REGION_BBOX:
        raise RuntimeError(f"no map box for {region}")
    pats = {c: "|".join(cats[c].get("overture", [])) for c in categories
            if cats[c].get("overture")}
    if not pats:
        return {}
    w, so, e, n = REGION_BBOX[region]
    w, so, e, n = w - 0.05, so - 0.05, e + 0.05, n + 0.05
    country = region[:2]
    code = region[3:]
    rel = overture_release(session)
    log(f"\n[{region}] Reading Overture Maps release {rel} (deep search, can take a few minutes)...")
    progress(phase="discover", done=0, total=0, label=f"{region}: Overture Maps (downloading the {region} map area)")
    files = overture_files(session, rel, (w, so, e, n))
    if files:
        log(f"  Overture: reading {len(files)} data file(s) that cover {REGIONS[region]}.")
        src = "[" + ", ".join("'" + f.replace("'", "") + "'" for f in files) + "]"
    else:
        src = "'" + OVERTURE_BASE.format(release=rel) + "'"
    con = _overture_connect()
    case = " ".join(f"WHEN regexp_matches(cat_text, '{p}') THEN '{c}'" for c, p in pats.items())

    def query(cat_expr: str, status_filter: bool) -> list:
        sql = f"""
        WITH p AS (
          SELECT id, names.primary AS name, websites, phones, emails, addresses,
                 lower(replace({cat_expr}, '_', ' ')) AS cat_text
                 {', operating_status' if status_filter else ''}
          FROM read_parquet({src}, hive_partitioning=1, union_by_name=1)
          WHERE bbox.xmin BETWEEN {w} AND {e} AND bbox.ymin BETWEEN {so} AND {n}
            AND websites IS NOT NULL AND len(websites) > 0
        )
        SELECT id, name, websites[1], phones[1], emails[1],
               addresses[1].freeform, addresses[1].locality, addresses[1].postcode,
               addresses[1].region, addresses[1].country,
               CASE {case} ELSE NULL END AS our_cat
        FROM p
        WHERE (addresses[1].country IS NULL OR upper(addresses[1].country) = '{country}')
          {"AND coalesce(CAST(operating_status AS VARCHAR), 'open') NOT ILIKE '%closed%'" if status_filter else ''}
          AND our_cat IS NOT NULL
        """
        return con.execute(sql).fetchall()

    new_cat = ("coalesce(array_to_string(taxonomy.hierarchy, ' '), '') || ' ' || "
               "coalesce(taxonomy.primary, '') || ' ' || coalesce(CAST(basic_category AS VARCHAR), '')")
    old_cat = ("coalesce(categories.primary, '') || ' ' || "
               "coalesce(array_to_string(categories.alternate, ' '), '')")
    rows, last_err = None, None
    for expr, st in ((new_cat, True), (new_cat, False), (old_cat, True), (old_cat, False)):
        if STOP.is_set():
            return {}
        try:
            rows = query(expr, st)
            break
        except Exception as ex:   # schema differs between releases: try the next shape
            last_err = ex
            if "Binder" not in str(ex) and "not found" not in str(ex).lower():
                raise RuntimeError(f"Overture read failed: {ex}")
    if rows is None:
        raise RuntimeError(f"Overture read failed: {last_err}")
    name_up = REGIONS[region].upper()
    out: dict[str, list[dict]] = {c: [] for c in categories}
    seen = set()
    for (pid, name, site, phone, email, street, city, post, reg, ctry, cat) in rows:
        reg_u = (reg or "").upper().replace(".", "")
        if reg_u and reg_u not in (code, name_up):
            continue          # inside the box but in a neighbouring state
        site = normalise_url(site or "")
        d = domain_of(site)
        if not d or d in seen or any(x in d for x in ("facebook.com", "instagram.com", "yelp.", "google.")):
            continue
        seen.add(d)
        b = {"key": f"overture:{pid}", "region": region, "category": cat,
             "name": name or "", "website": site, "phone": phone or "",
             "street": street or "", "city": city or "", "postcode": post or "",
             "email": email or "", "source": "overture"}
        db.add_business(b)
        out.setdefault(cat, []).append(b)
    log(f"  Overture: {sum(len(v) for v in out.values())} businesses with a website.")
    return out


# --------------------------------------------------------------------------
# Deep source: free-domain Wix sites (*.wixsite.com) from Common Crawl
# --------------------------------------------------------------------------
CC_INDEX = "https://index.commoncrawl.org/collinfo.json"
WIXSITE_SOURCE = "wixsite-hunt"


def _sleep_stoppable(seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end and not STOP.is_set():
        time.sleep(0.3)


def _cc_get(session, url, params=None, what: str = "data", tries: int = 4):
    """GET from Common Crawl. Shows every wait in the log, reacts to Stop within
    a second, and returns (status, text) - status None means it gave up."""
    for attempt in range(1, tries + 1):
        wait_if_paused()
        if STOP.is_set():
            return None, ""
        progress(phase="cc", done=0, total=0,
                 label=f"Waiting for Common Crawl ({what}, try {attempt}/{tries})")
        box: dict = {}

        def fetch():
            try:
                r = session.get(url, params=params, timeout=(15, 60))
                box["r"] = r
            except requests.RequestException as e:
                box["e"] = e

        th = threading.Thread(target=fetch, daemon=True)
        th.start()
        while th.is_alive():          # wait, but drop the request at once on Stop
            th.join(0.3)
            if STOP.is_set():
                return None, ""
        if "r" in box:
            r = box["r"]
            if r.status_code == 200:
                return 200, r.text
            if r.status_code in (400, 404):
                return r.status_code, r.text
            reason = f"busy ({r.status_code})"
        else:
            e = box.get("e")
            reason = "no answer" if "timed out" in str(e).lower() else type(e).__name__
        if attempt < tries:
            wait = 20 * attempt
            log(f"  Common Crawl {reason} for {what}. Trying again in {wait}s "
                f"(try {attempt}/{tries})...")
            _sleep_stoppable(wait)
    log(f"  Common Crawl isn't answering right now ({what}). Your place is saved; "
        "run the hunt again later.")
    return None, ""


def hunt_status(db: "DB") -> dict:
    """Where the wixsite.com hunt is up to, for the app's status line."""
    coll = db.get_kv("cc_collection")
    page = int(db.get_kv("cc_page", "0") or 0)
    found = db.q("SELECT COUNT(*) FROM businesses WHERE source=?", (WIXSITE_SOURCE,))[0][0]
    checked = db.q("SELECT COUNT(*) FROM businesses b JOIN sites s ON s.domain=b.domain"
                   " WHERE b.source=?", (WIXSITE_SOURCE,))[0][0]
    na = db.q("SELECT COUNT(*) FROM businesses b JOIN sites s ON s.domain=b.domain"
              " WHERE b.source=? AND s.is_wix=1 AND (b.region LIKE 'US-%' OR b.region LIKE 'CA-%')",
              (WIXSITE_SOURCE,))[0][0]
    return {"crawl": coll, "page": page, "found": found, "checked": checked, "na": na,
            "finished": db.get_kv("cc_finished") == "1"}


def run_wixsite_hunt(pages: int = 3, *, workers: int = DEFAULT_WORKERS,
                     db_path: str | None = None) -> int:
    """Pull *.wixsite.com websites from the free Common Crawl index, check them,
    keep the ones in the USA/Canada. Remembers where it stopped."""
    STOP.clear()
    db = DB(db_path or os.path.join(HERE, "wixbot.sqlite"))
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    log("\n===== wixsite.com hunt =====")
    st, text = _cc_get(s, CC_INDEX, what="list of crawls")
    if st != 200:
        return 0
    try:
        colls = json.loads(text)
    except ValueError:
        log("  Common Crawl sent an unexpected answer. Try again later.")
        return 0
    ids = [c["id"] for c in colls]
    coll = db.get_kv("cc_collection") or ids[0]
    if coll not in ids:
        coll = ids[0]
    page = int(db.get_kv("cc_page", "0"))
    params = {"url": "*.wixsite.com", "output": "json", "fl": "url,mime,status"}
    log(f"Crawl {coll}, starting at page {page + 1}. Each page can take 1-3 minutes.")
    roots: dict[str, str] = {}
    fetched = 0
    while fetched < pages:
        wait_if_paused()
        if STOP.is_set():
            break
        api = next(c["cdx-api"] for c in colls if c["id"] == coll)
        progress(phase="pages", done=fetched, total=pages, label=f"Common Crawl page {page + 1}")
        st, text = _cc_get(s, api, {**params, "page": str(page)}, what=f"page {page + 1}")
        if st is None:
            break                       # server down: keep the same page for next time
        if st in (400, 404):            # past the last page of this crawl
            i = ids.index(coll) + 1
            if i >= len(ids):
                log("All Common Crawl pages done.")
                db.set_kv("cc_finished", "1")
                break
            coll, page = ids[i], 0
            log(f"Moving on to the older crawl {coll}.")
            db.set_kv("cc_collection", coll); db.set_kv("cc_page", page)
            continue
        before = len(roots)
        for line in text.splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("status") != "200" or "html" not in rec.get("mime", ""):
                continue
            pu = urlparse(rec.get("url", ""))
            host = (pu.hostname or "").lower()
            if not host.endswith(".wixsite.com"):
                continue
            first = pu.path.strip("/").split("/")[0]
            roots.setdefault(f"{host}/{first}", f"https://{host}/{first}" if first else f"https://{host}")
        page += 1
        fetched += 1
        db.set_kv("cc_collection", coll); db.set_kv("cc_page", page)
        log(f"  Page {page}: {len(roots) - before} new sites ({len(roots)} so far).")
        progress(phase="pages", done=fetched, total=pages, label=f"Common Crawl page {page}")
        _sleep_stoppable(3)
    added = 0
    for key, url in roots.items():
        b = {"key": f"wixsite:{key}", "region": "UNKNOWN", "category": "wixsite",
             "name": "", "website": url, "source": WIXSITE_SOURCE}
        added += db.add_business(b)
    if STOP.is_set():
        log(f"Stopped. {added} new sites saved; they'll be checked on the next run.")
        return 0
    # also picks up sites saved by an earlier run that was stopped
    new = [b for b in db.businesses_by_source(WIXSITE_SOURCE)
           if not db.site_checked(domain_of(b["website"]))]
    if not new:
        log("No new wixsite.com sites to check this time.")
        return 0
    log(f"{added} new wixsite.com sites found. Checking {len(new)} sites...")
    checked, wix = run_checks(new, db, workers, False, True, step_label="wixsite.com sites")
    na = db.q("SELECT COUNT(*) FROM businesses b JOIN sites s ON s.domain=b.domain"
              " WHERE b.source=? AND (b.region LIKE 'US-%' OR b.region LIKE 'CA-%')",
              (WIXSITE_SOURCE,))[0][0]
    log(f"wixsite.com hunt: {na} sites in the USA/Canada so far (others are outside your market).")
    return wix


LAST_SUMMARY: list[str] = []      # filled by run_job, shown by the app at the end


def run_job(regions: list[str], categories: list[str], cats: dict, *,
            urls_file: str | None = None, workers: int = DEFAULT_WORKERS,
            recheck: bool = False, db_path: str | None = None,
            out_dir: str | None = None, export_only: bool = False,
            label: str | None = None, full: bool = False,
            sources: tuple = ("openstreetmap",), rerun: bool = False) -> list[str]:
    """Run discovery + checks for every region/category/source, export one CSV per
    region. Searches already finished are skipped unless rerun=True."""
    STOP.clear()
    LAST_SUMMARY.clear()
    db = DB(db_path or os.path.join(HERE, "wixbot.sqlite"))
    out_dir = out_dir or os.path.join(HERE, "output")
    written = []
    osm_session = requests.Session()
    osm_session.headers["User-Agent"] = USER_AGENT
    steps = [(r, c) for r in regions for c in categories]
    total_steps = len(steps) * (1 if urls_file else len(sources))
    step = 0
    for region in regions:
        if STOP.is_set():
            break
        log(f"\n===== {region} ({REGIONS.get(region, region)}) =====")
        if not export_only and urls_file:
            businesses = load_url_file(urls_file, region, categories[0], db)
            run_checks(businesses, db, workers, recheck, full, step_label="your list")
        elif not export_only:
            for source in sources:
                if STOP.is_set():
                    break
                todo = [c for c in categories if rerun or not db.job_done(region, c, source)]
                skipped = len(categories) - len(todo)
                if skipped:
                    LAST_SUMMARY.append(f"{REGIONS.get(region, region)} · {source}: {skipped} already searched before (skipped)")
                if skipped:
                    log(f"  {source}: {skipped} categor{'y' if skipped == 1 else 'ies'} already "
                        f"searched in {region} - skipped (tick 'Search again' to redo).")
                    step += skipped
                if not todo:
                    continue
                pre = {}
                if source == "overture":
                    for c in todo:
                        db.job_start(region, c, source)
                    try:
                        pre = discover_overture(region, todo, cats, db, osm_session)
                    except RuntimeError as e:
                        log(f"  Overture skipped: {e}")
                        LAST_SUMMARY.append(f"⚠ Overture didn't run for {REGIONS.get(region, region)}: {e}")
                        for c in todo:
                            db.job_finish(region, c, source, "failed", 0, 0)
                        step += len(todo)
                        continue
                for c in todo:
                    wait_if_paused()
                    if STOP.is_set():
                        break
                    step += 1
                    lbl = f"{REGIONS.get(region, region)} · {cats[c]['label']} · {source}"
                    progress(phase="step", done=step - 1, total=total_steps, label=lbl)
                    db.job_start(region, c, source)
                    if source == "overture":
                        businesses = pre.get(c, [])
                    else:
                        try:
                            businesses = discover(region, c, cats[c], osm_session, db)
                        except RuntimeError as e:
                            log(f"  Skipped {c}: {e}")
                            db.job_finish(region, c, source, "failed", 0, 0)
                            continue
                    run_checks(businesses, db, workers, recheck, full, step_label=lbl)
                    wix = db.wix_count([domain_of(b["website"]) for b in businesses])
                    LAST_SUMMARY.append(f"{REGIONS.get(region, region)} · {cats[c]['label'].split(' (')[0]} · "
                                        f"{'OpenStreetMap' if source == 'openstreetmap' else 'Overture'}: "
                                        f"{len(businesses)} businesses with a website, {wix} on Wix")
                    db.job_finish(region, c, source, "stopped" if STOP.is_set() else "done",
                                  len(businesses), wix)
                    progress(phase="step", done=step, total=total_steps, label=lbl)
                    if source == "openstreetmap" and not STOP.is_set():
                        time.sleep(5)  # be kind to the free OpenStreetMap servers
        rows = db.leads(region, categories)
        name = label or "_".join(categories)[:60]
        out = os.path.join(out_dir, f"{region}_{name}.csv")
        export_csv(rows, out)
        if rows:
            written.append(out)
    total, wix = db.stats()
    log(f"\nDatabase so far: {total} sites checked, {wix} on Wix.")
    return written


# --------------------------------------------------------------------------
# Inbox: receives websites from the Chrome helper / the in-app Yellow Pages window
# --------------------------------------------------------------------------
INBOX_PORT = 8765
INBOX_TOKEN = os.environ.get("NA_INBOX_TOKEN") or "%032x" % random.SystemRandom().getrandbits(128)
CAPTURE_SOURCE = "browser-capture"
US_STATES = {k[3:] for k in REGIONS if k.startswith("US-")}
CA_PROVINCES = {k[3:] for k in REGIONS if k.startswith("CA-")}


def guess_region(item: dict) -> str:
    """Use the region the extension sent, else read it from the address."""
    reg = (item.get("region") or "").upper()
    if reg in REGIONS:
        return reg
    addr = " ".join(str(item.get(k) or "") for k in ("city", "address"))
    m = re.search(r",\s*([A-Z]{2})\b(?:\s+[A-Z0-9]{3}\s?[A-Z0-9]{3}|\s+\d{5})?", addr)
    if m:
        code = m.group(1)
        if code in CA_PROVINCES and re.search(r"[A-Z]\d[A-Z]\s?\d[A-Z]\d", addr):
            return "CA-" + code
        if code in US_STATES:
            return "US-" + code
        if code in CA_PROVINCES:
            return "CA-" + code
    return "UNKNOWN"


def city_from_address(text: str) -> str:
    """'1200 Main St, Austin, TX 78701' -> 'Austin'."""
    m = re.search(r"([A-Za-z][A-Za-z .'-]{1,40}),\s*([A-Z]{2})\b\s*(?:\d{5}|[A-Z]\d[A-Z])?", text or "")
    return m.group(1).strip() if m else (text or "")


def add_captured(items: list[dict], db: "DB") -> int:
    """Store captured businesses. Returns how many were new."""
    added = 0
    for it in items:
        url = normalise_url(str(it.get("website") or ""))
        d = domain_of(url)
        if not d:
            continue
        key = f"capture:{d}"
        if db.q("SELECT 1 FROM businesses WHERE key=?", (key,)):
            continue
        db.add_business({
            "key": key, "region": guess_region(it),
            "category": re.sub(r"[^a-z0-9_]+", "_", str(it.get("category") or "captured").lower()).strip("_")[:40] or "captured",
            "name": str(it.get("name") or "")[:200], "website": url,
            "phone": str(it.get("phone") or "")[:40],
            "street": str(it.get("address") or "")[:200],
            "city": city_from_address(str(it.get("city") or ""))[:120],
            "source": CAPTURE_SOURCE,
            "extra": {"found_on": str(it.get("found_on") or "")[:300]},
        })
        added += 1
    return added


def start_inbox(db_path: str, on_added=None, port: int = INBOX_PORT):
    """Start a tiny local web server on 127.0.0.1 that the Chrome helper and the
    in-app Yellow Pages window send websites to. Only the Chrome extension or a
    caller with the secret token is accepted.
    Returns the server (call .shutdown() to stop) or None if the port is busy."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    db = DB(db_path)

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, code: int, body: dict):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _allowed(self) -> bool:
            if self.headers.get("X-NA-Token") == INBOX_TOKEN:
                return True
            return self.headers.get("Origin", "").startswith("chrome-extension://")

        def do_GET(self):
            if self.path == "/ping" and self._allowed():
                return self._reply(200, {"app": "WixLeadBot", "version": VERSION})
            self._reply(404, {"error": "not found"})

        def do_POST(self):
            if self.path == "/check" and self._allowed():
                return self._check()
            if self.path != "/capture" or not self._allowed():
                return self._reply(403, {"error": "forbidden"})
            try:
                length = min(int(self.headers.get("Content-Length", 0)), 2_000_000)
                payload = json.loads(self.rfile.read(length) or b"{}")
                items = payload.get("items", [])[:500]
                added = add_captured(items, db)
            except (ValueError, AttributeError) as e:
                return self._reply(400, {"error": str(e)})
            if on_added:
                on_added(added, len(items), items)
            self._reply(200, {"received": len(items), "new": added})

        def _check(self):
            """One business from Google Maps: save it and check its website now."""
            try:
                length = min(int(self.headers.get("Content-Length", 0)), 200_000)
                item = json.loads(self.rfile.read(length) or b"{}").get("item") or {}
            except (ValueError, AttributeError) as e:
                return self._reply(400, {"error": str(e)})
            url = normalise_url(str(item.get("website") or ""))
            d = domain_of(url)
            if not d:
                return self._reply(400, {"error": "no website"})
            item["category"] = item.get("category") or "google maps"
            added = add_captured([item], db)
            if not db.site_checked(d, True):
                db.save_site(check_site(url, PoliteFetcher()))
            r = db.q("SELECT is_wix, score, status, emails, phones FROM sites WHERE domain=?", (d,))
            is_wix, score, status, emails, phones = r[0] if r else (0, 0, "error", "", "")
            if on_added:
                on_added(added, 1, [item])
            return self._reply(200, {"is_wix": bool(is_wix), "score": score or 0, "status": status,
                                     "level": LEVELS[lead_level(score, bool(emails), bool(phones))][0]})

        def log_message(self, *args):  # keep the console quiet
            pass

    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        return None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def run_captured(*, workers: int = DEFAULT_WORKERS, recheck: bool = False,
                 db_path: str | None = None, out_dir: str | None = None,
                 full: bool = False) -> list[str]:
    """Check every captured website not checked yet, export one CSV."""
    STOP.clear()
    db = DB(db_path or os.path.join(HERE, "wixbot.sqlite"))
    businesses = db.businesses_by_source(CAPTURE_SOURCE)
    log(f"\n===== Captured websites ({len(businesses)} saved) =====")
    run_checks(businesses, db, workers, recheck, full, step_label="Yellow Pages websites")
    rows = db.leads(None, None, source=CAPTURE_SOURCE)
    out = os.path.join(out_dir or os.path.join(HERE, "output"), "captured_leads.csv")
    export_csv(rows, out)
    return [out] if rows else []


def main() -> None:
    ap = argparse.ArgumentParser(description="Find Wix-built business websites by state/province.")
    ap.add_argument("--region", help="e.g. US-TX or CA-ON (see --list-regions)")
    ap.add_argument("--category", help="category key(s), comma separated, or 'all'")
    ap.add_argument("--tier", help="with --category all: only tiers, e.g. A or AB")
    ap.add_argument("--urls-file", help="text/CSV file of websites to check (url[,name] per line)")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    ap.add_argument("--db", default=os.path.join(HERE, "wixbot.sqlite"))
    ap.add_argument("--out", help="folder for the CSV files (default: output)")
    ap.add_argument("--recheck", action="store_true", help="re-check sites already in the cache")
    ap.add_argument("--full", action="store_true",
                    help="open every website instead of using the fast DNS check first")
    ap.add_argument("--export-only", action="store_true", help="just export what's in the database")
    ap.add_argument("--inbox", action="store_true",
                    help="wait for websites sent by the Chrome Lead Capture helper")
    ap.add_argument("--captured", action="store_true",
                    help="check all websites captured with the Chrome helper")
    ap.add_argument("--deep", action="store_true",
                    help="also search Overture Maps (many more businesses, slower)")
    ap.add_argument("--again", action="store_true", help="redo searches already finished")
    ap.add_argument("--wixsite-hunt", type=int, metavar="PAGES",
                    help="find free *.wixsite.com sites from Common Crawl (pages per run)")
    ap.add_argument("--list-regions", action="store_true")
    ap.add_argument("--list-categories", action="store_true")
    a = ap.parse_args()

    cats = load_categories()
    if a.list_regions:
        for k, v in REGIONS.items():
            print(f"{k:6} {v}")
        return
    if a.list_categories:
        for k, v in cats.items():
            print(f"{k:22} tier {v['tier']}  {v['label']}")
        return
    if a.inbox:
        srv = start_inbox(a.db, lambda new, total, items: log(f"Received {total} websites ({new} new)."))
        if not srv:
            sys.exit(f"Port {INBOX_PORT} is busy - is the WixLeadBot app already open?")
        log(f"Waiting for websites from the Chrome helper on port {INBOX_PORT}. Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            srv.shutdown()
        return
    if a.wixsite_hunt:
        run_wixsite_hunt(a.wixsite_hunt, workers=a.workers, db_path=a.db)
        return
    if a.captured:
        run_captured(workers=a.workers, recheck=a.recheck, db_path=a.db,
                     out_dir=a.out, full=a.full)
        return
    if not a.region or a.region not in REGIONS:
        ap.error("--region is required, e.g. --region US-TX (see --list-regions)")
    if not a.category:
        ap.error("--category is required, e.g. --category dentist (see --list-categories)")

    if a.category == "all":
        chosen = [k for k, v in cats.items() if not a.tier or v["tier"] in a.tier.upper()]
    elif a.urls_file:
        chosen = [a.category]
    else:
        chosen = [c.strip() for c in a.category.split(",")]
        bad = [c for c in chosen if c not in cats]
        if bad:
            ap.error(f"Unknown category: {', '.join(bad)} (see --list-categories)")

    label = "all" if a.category == "all" else None
    run_job([a.region], chosen, cats, urls_file=a.urls_file, workers=a.workers,
            recheck=a.recheck, db_path=a.db, out_dir=a.out, export_only=a.export_only,
            label=label, full=a.full, rerun=a.again,
            sources=("openstreetmap", "overture") if a.deep else ("openstreetmap",))


if __name__ == "__main__":
    main()
