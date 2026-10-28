# Dev.to scraper + mail dashboard

`start.bat` / `start.sh` call `launch.py`. That process starts the Dev.to scraper and the dashboard on port 8007. Both read and write one SQLite file, `app.db`.

```mermaid
flowchart TB
  scripts["start.bat / start.sh"] --> launch["launch.py"]
  launch --> scraper["scrapers/devto"]
  launch --> dashboard["server/dashboard.py :8007"]

  devto["Dev.to API"] --> scraper
  github["GitHub API"] --> scraper
  scraper --> locations["core/locations.py"]
  scraper --> enrich["core/github_enrich.py"]
  scraper --> db[("app.db")]
  enrich --> db

  dashboard --> db
  dashboard --> mail["mail/ + templates/"]
  dashboard --> ui["frontend/dist"]

  ui --> shell["Shell"]
  shell --> pool["Pool"]
  shell --> scraperview["Scraper"]
  shell --> templatesview["Templates"]
  shell --> settings["Settings"]
  pool --> modal["Contact modal"]
```

| Path | What it owns |
| --- | --- |
| `launch.py` | Starts `scrapers.devto` and uvicorn. Does not start a mail sender. |
| `scrapers/devto/` | Walks Dev.to user ids, normalizes location, stores a GitHub profile when the token allows it. |
| `core/db.py` | Users, contact status, sender addresses, scrape position, and the GitHub token. |
| `core/github_enrich.py` | Token lookup, profile fields, and which hosts are social links. |
| `core/locations.py` | Place formatting and excluded countries. |
| `server/dashboard.py` | HTTP API and the built UI. |
| `mail/` | Renders `[Name]`, `[Your Name]`, and `[Link]` from `templates/*.txt`. |
| `frontend/src/app/` | Dashboard state and HTTP calls. |
| `frontend/src/features/` | Pool, Scraper, Templates, and Settings. The email and social modals live under Pool. |
| `exclude-regions.txt` | Country slugs the scraper will not save. |

The GitHub token and each sender’s name are rows in `app.db`, edited on Settings. `app.db` stays on disk and is not part of the git history.

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

### 7. Add a sender

1. In the UI, open **Settings**
2. **Add account**
3. Gmail address and the name that should fill `[Your Name]`
4. Save

Account age still sets the scrape cap. Tokyo calendar age raises each account’s cap at Tokyo midnight, and the scraper idles once today’s located saves reach that budget.

## Email templates

Plain-text files in `templates/`. Manage them on the **Templates** page, or edit the files directly.

- Filename: `{slug} (n).txt` — for example `apac (1).txt`, `japan (1).txt`, `usa (1).txt`
- Line 1: `Subject: ...`
- Rest: body
- Placeholders: `[Name]` (display name; missing → `there`), `[Your Name]` (the name saved for the selected sender), `[Link]`

**Named regions** (one file covers many countries): `eu`, `emea`, `apac`, `latam`, `etc` (Other).

**Countries** use the country name: `japan`, `usa`, `india`, `germany`. Typing `ja` / `jp` or `us` is treated as `japan` / `usa`.

The mail modal picks the first match that has files: country file → named region → Other. Add APAC once and Asian/Pacific countries use it unless a country file exists.

The dashboard reloads templates from disk after you save in the UI.

## Exclude countries

`exclude-regions.txt` is a hand-edited skip list (one country slug per line). The scraper will not save those countries, the dashboard hides them, and matching users are deleted from SQLite.

Tiny countries that already had **fewer than 10** users were seeded here once. New small countries are **not** auto-added — otherwise they could never grow. Add a slug in the file (`iceland`, or a named region such as `eu` to drop every EU country), or click **−** next to a country in the Users sidebar. `#` starts a comment. `noloc` is not a country; do not list it.

Edits are picked up while scrape/dashboard are running.

## How to contact someone

1. **Scrape** — keep the app running so users accumulate. Dev.to resumes from its `last_id` parameter. Pause or change the daily located-save cap on the **Scraper** page.
2. **Settings** — add each sender address and the name that fills `[Your Name]`.
3. **Pool** — pick a country, or search by name or email. Open an email or a social icon, copy the rendered message, and mark it Sent, Failed, or Clear.
4. **Suppress** hides a person from the pool and keeps the email so a later scrape cannot add them again.

Mail is sent by hand. The dashboard does not queue or send messages.

### Scrape throttle

The scraper stays running but **idles** when today’s **located** saves (country ≠ `noloc`) reach the daily scrape cap. Default cap:

`floor(1.5 × sum of active Gmail daily caps)`

Set an absolute cap (or pause scraping) from the **Scraper** page. Saves tagged `noloc` still happen but **do not** count toward the budget. Override the auto ratio with `SCRAPE_MAIL_CAP_RATIO` (default `1.5`) when cap mode is Auto.

### Optional env knobs

| Variable | Default | Meaning |
| --- | --- | --- |
| `MAIL_DAILY_LIMIT` | `20` | Fallback daily cap if no account caps apply |
| `SCRAPE_MAIL_CAP_RATIO` | `1.5` | Auto scrape cap = ratio × active mail caps (dashboard can override with a manual daily cap) |
