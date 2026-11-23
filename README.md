# NA Developers – Wix Lead Bot v1.5

Finds local businesses in the USA and Canada whose websites are built on Wix,
shows each one as a lead profile, and runs your outreach (drafts, approval,
sending, follow-ups, replies) from one Windows app. Free: no paid tools or API keys.

## Install / update (Windows)

1. Unzip over your old folder (your leads in `wixbot.sqlite` are kept).
2. Double-click **`BUILD_EXE.bat`** (2–4 minutes).
3. Open **`WixLeadBot.exe`**. The first time, it asks you to **create a password**.

## The app, page by page

| Page | What it does |
|---|---|
| **Dashboard** | Totals, Super/Hot counts, today's emails, best leads not contacted yet. |
| **Find leads** | Pick states + categories, choose sources, press **Start**. Searches you already did show ✓ and are skipped (tick *Search again* to redo). |
| **Yellow Pages** | Type what + city, click **Open Yellow Pages**. You browse; every page you view is captured. Then click **Check captured websites**. |
| **Leads** | Every Wix site, colour-coded. Click one for its **profile**: contacts, where each email was found, problems found, mini audit, outreach history and notes. |
| **Outreach** | Draft emails for Super + Hot leads, read/edit, **Approve**, then **Send approved emails**. Follow-ups and inbox checks are here too. |
| **Pipeline** | Emailed → Replied → Call booked → Proposal → Won/Lost. |
| **Coverage** | Which states/categories are done, with business and Wix counts. |
| **Settings** | Email account, your details (postal address, booking link), templates, never-contact list, password. |

The dark bar at the bottom shows progress (%, sites done, time left) with
**Pause / Resume** and **Stop** for any job.

### New in v1.5: from lead to sale

| Step | In the app |
|---|---|
| Find | Also **Google Maps**: open one business on Maps, click the Chrome helper, **Check if Wix & save to app**. |
| Audit | Profile → **Run full audit**: Google PageSpeed (speed, SEO, design, best practices + phone screenshot) and 20 design / SEO / business checks. Branded report (Ctrl+P → PDF). |
| Personalise | Profile → **Make plan + email with Gemini** (free Gemini API key): angle, package, talking points, objections, custom email. **Mockup prompt** → Copy / Open Gemini; make the mockup yourself and **Attach mockup**. |
| Send | Outreach → **Gemini emails for Super + Hot** (audit + plan + draft, up to 25 at a time). Sends in each lead's **local business hours**, skips addresses that can't receive email and sites that say "no solicitation". Attach files to drafts. |
| Replies | **Check inbox** sorts replies (interested / question / not now / no / unsubscribe), detects **Calendly bookings** (→ Call booked) and bounces. Outreach → **Replies** → **Draft an answer**. "Not now" gets a check-back email after ~75 days. |
| Call | Profile or Pipeline → **Call brief**: everything for the meeting on one page. |
| After the sale | Mark **Won** → reminders for a Google review (7 days), care plan (30 days) and referral (45 days) on the Dashboard. |
| Results | Dashboard → **Results by category** (emailed, replied, calls, won). |
| Safety | Daily database backup in `backups/` (last 14 days). Settings → AI & audit → **Check my sending domain** (SPF, DKIM, DMARC). |

To copy the database yourself, close the app first (or copy `wixbot.sqlite` together with any `-wal`/`-shm` files next to it).

### Lead levels

| Level | Colour | Meaning |
|---|---|---|
| **Super** | Red | Score 40+ and an email address. Contact first. |
| **Hot** | Orange | Score 20+ and an email or phone. |
| **Normal** | Teal | Fewer problems found. |

### Sources

- **OpenStreetMap**: fast, free, but only part of all businesses.
- **Overture Maps (deep)**: free open data with tens of millions of places. Reads only
  the part of the map for the state you pick (a few minutes per state). Needs the
  `duckdb` part to install during the build.
- **wixsite.com hunt**: finds sites still on a free Wix address from the free Common
  Crawl web archive, keeps the USA/Canada ones. Continues where it stopped.
- **Yellow Pages**: in-app window (uses Microsoft Edge WebView2, built into Windows 10/11)
  or the Chrome helper below.

### Email setup (Settings → Email account)

Pick your provider and paste an **app password** (not your normal password):
- Google Workspace/Gmail: myaccount.google.com → Security → 2-Step Verification → App passwords.
- Microsoft 365: your admin must turn on "Authenticated SMTP" for the mailbox.
- Zoho: Settings → Security → App passwords.

Then **Settings → Your details**: add a **postal address** (US law, CAN-SPAM, requires one
in every sales email). The app refuses to send without it. Defaults: 25 emails a day,
60–150 seconds apart, Mon–Fri 9am–5pm New York time, follow-ups on day 3, 7 and 14.
Unsubscribe replies, bounces and clients are never emailed again.

### Security

- Your app password is never saved, only a secure hash.
- Your email app password is encrypted with it.
- Forgot the password? Delete `config.json`. Your leads stay, but you set a new password
  and re-enter the email password.
- The leads database itself is not encrypted, so keep the folder on your own PC.

---

## Older notes (v1.2)

## 0. Easiest way: the Windows app (WixLeadBot.exe)

1. Install Python 3.10+ from https://www.python.org/downloads/
   (**tick "Add Python to PATH"**). You only need it once, to build the app.
2. Unzip this folder, e.g. to `C:\wixbot`.
3. Double-click **`BUILD_EXE.bat`** and wait 1–2 minutes.
4. Double-click **`WixLeadBot.exe`**. You can copy it anywhere, and results are
   saved in an `output` folder next to it.

In the app:
1. Choose **USA** or **Canada**, then pick states (hold Ctrl to pick several).
2. Tick categories, or click **Tier A**, **Tier B** or **Tier C**.
3. Press **Start**. Wix sites appear in green as they're found. Press **Stop**
   at any time; the next run carries on where it stopped.
4. Click **Open results folder** to get the CSV files.

### What's new in v1.2

- **Fast DNS check (on by default).** Before opening a website, the app checks
  where its domain points, using your own internet connection, for free. Only
  domains that point at Wix's servers are opened. In testing this found the 13 Wix
  dentists among 648 Texas dental websites in about a minute. A few Wix sites hidden
  behind other services can be missed; tick **Full check (slower)** to open every
  site instead.
- **Chrome helper for Yellow Pages.** Grab websites from Yellow Pages pages while
  you browse; see below.

### Install the Chrome helper (one time, free)

1. In Chrome, open `chrome://extensions`.
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked** and choose the `chrome-extension` folder from this zip.
4. Pin it: click the puzzle icon in Chrome's toolbar, then the pin next to
   "NA Developers Lead Capture".

### Use it with Yellow Pages

1. Open **WixLeadBot.exe**. The app shows "Chrome helper connected".
2. In Chrome, search Yellow Pages as usual, e.g. yellowpages.com → "dentists" in
   "Dallas, TX", or yellowpages.ca → "dentist" in "Toronto ON".
3. Click the helper icon, then **Capture websites on this page**. Every business
   website on the page goes to the app. The state/province and category come
   from the page.
4. Go to the next results page and click Capture again. Repeat as much as you like.
5. In the app, click **Check captured websites**. The Wix ones are saved to
   `output\captured_leads.csv`.

If the app isn't open, the helper keeps the websites in a saved list. Press
**Send to app** later, or **Download .txt** and load it with "Use my own list
of websites".

The helper only reads the page you're looking at, and only when you click.
It never browses Yellow Pages on its own. It also shows whether **any website you
have open is built on Wix**, which is handy while you browse Google Maps.

The steps below are only needed if you'd rather use the command line.

## 1. One-time setup (Windows)

1. Install Python 3.10 or newer from https://www.python.org/downloads/.
   **Tick "Add Python to PATH"** during install.
2. Put this folder somewhere easy, e.g. `C:\wixbot`.
3. Open **PowerShell** in that folder (Shift + right-click inside the folder →
   "Open PowerShell window here") and run:

```
pip install -r requirements.txt
```

## 2. Run it

See the state/province codes and categories:

```
python wixbot.py --list-regions
python wixbot.py --list-categories
```

One state, one category:

```
python wixbot.py --region US-TX --category dentist
```

Several categories at once:

```
python wixbot.py --region CA-ON --category dentist,lawyer,home_services
```

All of the best-fit (tier A) categories for a state:

```
python wixbot.py --region US-FL --category all --tier A
```

Check websites captured with the Chrome helper:

```
python wixbot.py --inbox      (leave running while you capture)
python wixbot.py --captured   (then check them)
```

The CSV is saved in the `output` folder, e.g. `output\US-TX_dentist.csv`,
sorted with the highest-scoring leads first.

### Check your own list of websites

If you collect websites yourself (from Google Maps, directories and so on), put
one per line in a text file, optionally followed by a comma and the business name:

```
https://brightsmiledental.com, Bright Smile Dental
acmeroofing.com, Acme Roofing
```

Then run:

```
python wixbot.py --urls-file my_sites.txt --region US-TX --category custom
```

### Run every state, one after another (PowerShell)

```
$states = "US-TX","US-FL","US-CA","US-NY","CA-ON","CA-BC","CA-AB"
foreach ($s in $states) { python wixbot.py --region $s --category all --tier A }
```

## 3. The CSV columns

| Column | Meaning |
|---|---|
| business_name, website | From OpenStreetMap or your file |
| free_wix_domain | `yes` = still on a `wixsite.com` address. These are the easiest pitch. |
| emails | Emails found on the site (Wix system emails are filtered out) |
| email_found_on | The exact page each email was found on. **Keep this as your proof for Canada.** |
| phones_on_site, phone_listed | Phones from the website and from the map listing |
| socials | Facebook, Instagram, LinkedIn and others, if linked |
| copyright_year | The year in the footer; old years mean the site hasn't been touched |
| opportunity_score | 0–100; higher means more to fix |
| issues | What to mention in your pitch (weak title, no description, thin homepage...) |

## 4. Settings you can change (top of `wixbot.py`)

- `DEFAULT_WORKERS` (8): how many sites are checked at once. Higher is faster
  but less polite; keep it between 4 and 10.
- `PER_HOST_DELAY` (1 s): the pause between two pages of the same website.
- `USER_AGENT`: identifies the bot with your website and email, so site owners
  know who is visiting.

To add a category, edit `categories.json`. Tag names come from the
OpenStreetMap wiki: https://wiki.openstreetmap.org/wiki/Map_features

## 5. Good to know

- **Coverage:** OpenStreetMap doesn't list every business, and many small
  businesses aren't on it. Big states give hundreds to thousands of businesses
  per category; rural areas give fewer. Use `--urls-file` to add sites you find
  yourself.
- **OpenStreetMap is a free, shared service.** The bot waits between queries
  and retries when the server is busy. If you see "OpenStreetMap is busy", just
  let it wait. Don't run several copies at once.
- **Being polite:** the bot obeys each site's `robots.txt`, waits between
  requests to the same site, and reads at most 4 pages per Wix site.
- **Credit:** map data © OpenStreetMap contributors (ODbL licence).

## 6. Before you email anyone

- **Canada (CASL):** only email addresses the business published itself on its
  own website, with no "no solicitations" note next to them, and keep the
  `email_found_on` column as proof. Every email must name your business, give
  your contact details and offer a clear unsubscribe.
- **USA (CAN-SPAM):** give an honest sender name and subject, your business
  address, and an opt-out that you honour.
- Send in small batches from a warmed-up inbox, and personalise each email
  using the `issues` column.
