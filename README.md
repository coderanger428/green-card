# Dev.to scraper + mail dashboard

Local pipeline that scrapes Dev.to users, enriches public GitHub emails, stores contacts in SQLite, and drip-sends plain-text outreach mail from a small web dashboard.

Three pieces share one SQLite database (`app.db` at the repo root, WAL mode):

| Piece | Role |
| --- | --- |
| **Scraper** (`scrapers/devto/`) | Walks Dev.to user IDs, maps location → country, looks up public GitHub email, saves users |
| **Dashboard** (`server/dashboard.py`) | FastAPI API + drip worker; also serves the built React UI |
| **UI** (`frontend/`) | Raw and Tracked users, scrape control, Gmail senders, templates, and the send queue |
| **Shared store** (`core/`) | SQLite (`db.py`) and country detection (`locations.py`), used by the scraper and the dashboard |
| **Mail** (`mail/`) | Templates and regions (`regions.py`), Tokyo drip pacing (`schedule.py`), SMTP (`send.py`) |

`launch.py` stays at the repo root. `start.bat` and `start.sh` call it, and it starts every scraper in `scrapers/` plus the dashboard. `exclude-regions.txt`, `templates/`, and `app.db` stay at the root. `launch.pids` sits next to `launch.py`.

`app.db` is one database for every platform. Contacts, the send queue, and Gmail accounts are shared. Each scraper’s own settings live in `scraper_parameter` as a JSON object keyed by platform id. Dev.to stores `{"last_id": ...}` there and resumes from that number, not from a user row. The dashboard’s user total is a count of `users`.

A saved profile URL is written onto `users.link` when the person is found. The Source column shows the platform’s display name (`devto` → dev.to). The link tooltip is the saved URL. Tracked mail results use `users.outcome`: Waiting, Replied, or Rejected.

Mail is **plain text** only. Templates live under `templates/` as `.txt` files.

```
Dev.to / GitHub  →  scraper  →  SQLite  ←  dashboard drip worker  →  Gmail SMTP
                                      ↑
                                 React UI (:8007)
```

## Initial setup

Do this once on a new machine. After that, daily use is `start.bat` (or `./start.sh`).

### 1. Install runtimes

- **Python 3.10+**
- **Node.js 18+** (the launcher uses `npm` to install and build the UI)
- A **Gmail** account with an [App Password](https://support.google.com/accounts/answer/185833)

### 2. Put the project on disk

Clone or copy the repo. Open a terminal in that folder (the one that contains `start.bat`).

### 3. Create the project virtualenv

A local `.venv` is required. System Python is not used.

**Windows**

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**Linux / macOS**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

You do not need to `npm install` by hand. The first `start` run does that and builds `frontend/dist`.

### 4. Settings

The GitHub token and sender names are saved on the **Settings** page after launch, in `app.db`. The token row shows the expiration GitHub reports, and marks the token expired when that date has passed or GitHub rejects it. Each sender address has its own name, which fills `[Your Name]` for the sender you pick. No app password is stored.

### 5. First launch

**Windows:** double-click `start.bat` (or run it from the project folder).

**Linux / macOS:** `./start.sh`

The launcher installs Python deps if needed, stops any previous instance from this project, builds the UI if it is missing or stale, then starts the scraper and dashboard in the same window.

Open **http://127.0.0.1:8007**

| What you want | Windows | Linux / macOS | URL |
| --- | --- | --- | --- |
| **Run the app** | `start.bat` | `./start.sh` | http://127.0.0.1:8007 |
| Edit the React UI with live reload | `start-watch.bat` or `start.bat watch` | `./start-watch.sh` | http://127.0.0.1:5173 |
| Stop everything | Ctrl+C, or `stop.bat` | Ctrl+C, or `./stop.sh` | — |

After code or template changes, run `start` again. It shuts the old processes down first.

### 6. Optional: start 5 minutes after sign-in

From the project folder:

```bat
register-login.bat
```

That writes a script into this Windows user’s Startup folder. Five minutes after sign-in, it runs this copy’s `start.bat`. Sign-in is the session Windows opens after power-on. No admin rights. Undo with `register-login.bat remove`. Takes effect on the **next** sign-in.

### 7. Add a Gmail sender

1. In the UI, open **Settings**
2. **Add account**
3. Gmail address + [App password](https://support.google.com/accounts/answer/185833) (not your normal login password)
4. Save

Accounts live in SQLite with per-account daily caps that ramp by **Tokyo calendar age** (tiers change at Tokyo midnight). The drip worker only uses **active** accounts that still have remaining daily capacity.

## Email templates

Plain-text files in `templates/`. Manage them on the **Templates** page, or edit the files directly.

- Filename: `{slug} (n).txt` — for example `apac (1).txt`, `japan (1).txt`, `usa (1).txt`
- Line 1: `Subject: ...`
- Rest: body
- Placeholders: `[Name]` (display name; missing → `there`), `[Your Name]` (the name saved for the selected sender), `[Link]`

**Named regions** (one file covers many countries): `eu`, `emea`, `apac`, `latam`, `etc` (Other).

**Countries** use the country name: `japan`, `usa`, `india`, `germany`. Typing `ja` / `jp` or `us` is treated as `japan` / `usa`.

At send time the drip worker picks the first match that has files: country file → named region → Other. Add APAC once and Asian/Pacific countries use it unless a country file exists.

The dashboard reloads templates from disk after you save in the UI.

## Exclude countries

`exclude-regions.txt` is a hand-edited skip list (one country slug per line). The scraper will not save those countries, the dashboard hides them, and matching users are deleted from SQLite (including queue rows).

Tiny countries that already had **fewer than 10** users were seeded here once. New small countries are **not** auto-added — otherwise they could never grow. Add a slug in the file (`iceland`, or a named region such as `eu` to drop every EU country), or click **−** next to a country in the Users sidebar. `#` starts a comment. `noloc` is not a country; do not list it.

Edits are picked up while scrape/dashboard are running.

## How to send mail

1. **Scrape** — keep the app running so users accumulate. Dev.to resumes from its `last_id` parameter. Pause or change the daily located-save cap on the **Scraper** page.
2. **Settings** — at least one active Gmail account.
3. **Settings** — set the name on each sender address. That name fills `[Your Name]`.
4. **Raw** — contacts not yet sent. Country sidebar, or All countries, search, edit the greeting, select rows. **Suppress** hides a person from the pools and keeps the email so a later scrape cannot add them again.
5. **Enqueue** — add selected Raw users. Blocked company domains are skipped.
6. **Drip** runs while the dashboard is up (unless paused):
   - Queue is FIFO (oldest queued first)
   - **Tokyo midnight** starts a new mail day (caps + sent-today reset)
   - Remaining daily cap is **spread until Tokyo midnight** (a 50/day cap is ~29 minutes between sends at the start of the day; leftover cap after downtime is sent faster so it still finishes before midnight)
   - Overflow waits for the next Tokyo day
   - Template match as above; plain-text SMTP
7. **Pause / resume** drip in the UI without stopping the server.
8. **Tracked** — people already sent. Set outcome to Waiting, Replied, or Rejected. The greeting is fixed after send.
9. **Monitor** queue, sent/failed, and “sent today” on the dashboard.

The queue is in SQLite. If the PC is off for a few hours, nobody is dropped; on restart, leftover cap is paced over the rest of that Tokyo day. Unused cap does not carry past midnight.

Failed sends keep an error on the queue item. SMTP DNS outages pause drip and requeue the current message until `smtp.gmail.com` resolves again.

### Scrape throttle

The scraper stays running but **idles** when today’s **located** saves (country ≠ `noloc`) reach the daily scrape cap. Default cap:

`floor(1.5 × sum of active Gmail daily caps)`

Set an absolute cap (or pause scraping) from the **Scraper** page. Saves tagged `noloc` still happen but **do not** count toward the budget. Mail keeps sending while scrape sleeps until the next Tokyo midnight, or until you raise the cap. Override the auto ratio with `SCRAPE_MAIL_CAP_RATIO` (default `1.5`) when cap mode is Auto.

### Optional env knobs

| Variable | Default | Meaning |
| --- | --- | --- |
| `MAIL_DAILY_LIMIT` | `20` | Fallback daily cap if no account caps apply |
| `MAIL_DRIP_DELAY_MIN` | `30` | Floor between sends when the Tokyo day still has room (seconds). The gap grows so leftover cap lasts until midnight. |
| `MAIL_DNS_RETRY_DELAY` | `30` | Wait between SMTP DNS retries when paused |
| `SCRAPE_MAIL_CAP_RATIO` | `1.5` | Auto scrape cap = ratio × active mail caps (dashboard can override with a manual daily cap) |
