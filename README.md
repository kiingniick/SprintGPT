<div align="center">

# 🏃 SprintGPT

### Your AI running coach, right in the browser.

Track every run, understand your heart‑rate training, predict race times, and get a
personalized training plan — all built **by runners, for runners**.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-web%20app-000000?logo=flask&logoColor=white)
![PWA](https://img.shields.io/badge/PWA-installable-5A0FC8?logo=pwa&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-2ea44f)

</div>

---

## 📖 Contents

- [Why SprintGPT?](#-why-sprintgpt)
- [Quick start](#-quick-start-2-minutes)
- [Install by platform](#-install-by-platform)
- [What you get](#-what-you-get)
- [Bringing in your runs](#-bringing-in-your-runs)
- [Using it on your phone](#-using-it-on-your-phone)
- [Host it yourself (run over the internet)](#-host-it-yourself-run-over-the-internet)
- [Your account & settings](#-your-account--settings)
- [The built‑in coach](#-the-built-in-coach)
- [For app owners & admins](#-for-app-owners--admins)
- [Command line (optional)](#-command-line-optional)
- [How the coaching works](#-how-the-coaching-works)
- [Project layout](#-project-layout)
- [License](#-license)

---

## 🎯 Why SprintGPT?

Most running apps either lock the good stuff behind a subscription or bury your
numbers in noise. SprintGPT is different:

- **It's yours.** Your runs, goals, and heart‑rate profile live in your own private
  account. The coach answers from *your* data — no external APIs, no keys, no tracking.
- **It's honest.** Race predictions are grounded in what you've *actually* run and get
  more optimistic only as you build real endurance — no fantasy finish times.
- **It's everywhere.** A fast, mobile‑first web app you can install on your phone and
  use like a native app, online or off.

---

## ⚡ Quick start (2 minutes)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Launch the app (opens http://127.0.0.1:5000)
python main.py
```

That's it. You'll land on a friendly **welcome guide** — from there, create a free
account, bring in your runs, and start training smarter.

> **Just want to look around first?** Seed some demo data, then launch:
> ```bash
> python main.py cli seed
> python main.py
> ```

<details>
<summary><b>More launch options</b></summary>

```bash
python main.py --port 8000     # run on a custom port
python main.py --no-browser    # don't auto-open a browser
python main.py --host 0.0.0.0  # expose on your local network (for phones)
```
</details>

---

## 📲 Install by platform

Pick your device below for step-by-step install instructions.

<details>
<summary><b>🤖 Android — install the native app (APK)</b></summary>

SprintGPT ships as a **fully native Android app**. On first launch it asks how you want to run:

- **Run on this phone** — everything stays on your device and works **fully offline**. No server, no account sharing.
- **Connect to a server** — point the app at a SprintGPT you [host yourself](#-host-it-yourself-run-over-the-internet). It runs over **mobile data or Wi-Fi**, and the app and website share the **same account and runs**.

Install steps:

1. On your phone, open the [latest release](https://github.com/kiingniick/SprintGPT/releases/latest) and download **`SprintGPT-<version>.apk`**.
2. Tap the downloaded file. If prompted, allow **Install from unknown sources** for your browser or files app.
3. Open **SprintGPT** and pick a mode. (On-device mode takes a few seconds the first time to unpack its built-in Python runtime.)

> Release builds come **pre-filled with a recommended server** so "Connect to a server"
> is one tap — you can always type your own [self-hosted URL](#-host-it-yourself-run-over-the-internet) instead.
> Every menu option now lives in a single, mobile-friendly **☰ menu** in the top bar.

> You can switch modes anytime: open **Account settings → App connection**, or tap **Connection** in the menu.
>
> Requires a 64-bit (`arm64-v8a`) device — virtually every phone from the last several years. The APK is debug-signed for easy sideloading.
</details>

<details>
<summary><b>🍎 iPhone / iPad — install as a web app</b></summary>

There's no App Store build yet, but SprintGPT is an installable Progressive Web App:

1. Make sure a SprintGPT server is reachable — run one yourself (see Windows/macOS/Linux below) or use your hosted URL — and open it in **Safari**.
2. Tap the **Share** button, then **Add to Home Screen**.
3. Launch it from the new icon; it opens full-screen with an app-style tab bar.
</details>

<details>
<summary><b>🪟 Windows — run from source</b></summary>

Install [Python 3.11+](https://www.python.org/downloads/windows/) (tick **"Add Python to PATH"**), then in PowerShell:

```powershell
git clone https://github.com/kiingniick/SprintGPT.git
cd SprintGPT
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Your browser opens at <http://127.0.0.1:5000>. To keep it like a desktop app, click the **Install** icon in Chrome/Edge's address bar.
</details>

<details>
<summary><b>🍏 macOS — run from source</b></summary>

Install Python 3.11+ (`brew install python`, or from [python.org](https://www.python.org/downloads/macos/)), then in Terminal:

```bash
git clone https://github.com/kiingniick/SprintGPT.git
cd SprintGPT
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

Open <http://127.0.0.1:5000>. In Chrome/Edge you can **Install** it as an app; in Safari (Sonoma+) use **File → Add to Dock**.
</details>

<details>
<summary><b>🐧 Linux — run from source</b></summary>

Install Python 3.11+ (e.g. `sudo apt install python3 python3-venv python3-pip`), then in a terminal:

```bash
git clone https://github.com/kiingniick/SprintGPT.git
cd SprintGPT
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

Open <http://127.0.0.1:5000> and use your browser's **Install app** option for a standalone window.
</details>

<details>
<summary><b>🛠️ Build the Android APK yourself</b></summary>

Want to build the native app from source? See [`android/README.md`](https://github.com/kiingniick/SprintGPT/blob/main/android/README.md) — you'll need JDK 17, the Android SDK (platform 34), and a Python 3.12 interpreter for Chaquopy, then:

```powershell
cd android
.\gradlew.bat assembleDebug -PbuildPython="C:/path/to/python3.12/python.exe"
```

The APK lands in `android/app/build/outputs/apk/debug/app-debug.apk`.
</details>

---

## 🎁 What you get

| Feature | What it does for you |
| --- | --- |
| **📊 Dashboard** | Fitness, fatigue & form (CTL/ATL/TSB), weekly volume, elevation, and recent runs at a glance. |
| **❤️ Heart‑rate zones** | Five‑zone breakdowns (Karvonen or %HRmax), per‑run time‑in‑zone, and TRIMP training load. |
| **🔮 Race predictions** | Realistic, progressive 5K → marathon times based on your own runs and endurance. |
| **⏱️ Splits calculator** | Turn one goal time into exact even per‑mile and per‑km splits. |
| **🗺️ Personalized plans** | Base → Build → Peak → Taper periodization tuned to your goal race and fitness. |
| **💬 Coach chatbot** | Ask about your training in plain English — answered from your data, fully offline. |
| **📥 Easy imports** | Free Strava export, live Strava sync, CSV, manual entry, or official race results by name. |
| **📱 Installable app** | Add it to your home screen and run it like a native mobile app. |

---

## 📥 Bringing in your runs

SprintGPT meets your data wherever it lives. Pick whichever is easiest:

### 1. Free Strava export — *recommended, no subscription* ⭐

Strava gates its API behind a paid tier, but **every athlete can export their full
history for free**, and SprintGPT reads it directly.

1. Go to **Strava → Settings → My Account → [Download or Delete Your Account](https://www.strava.com/athlete/delete_your_account)**.
2. Under **Download Request**, click **Request Your Archive**.
3. Strava emails you a link (usually within a few hours).
4. In SprintGPT, on the **"Import your Strava history"** card, upload the `.zip`
   (or its `activities.csv`). Distance, time, elevation, and average HR import instantly.

> Every run keeps its Strava id, so re‑importing (or later live‑syncing) never
> creates duplicates.

### 2. Import race results by name 🏅

Your official meet times usually live on results sites, not in a training app. The
**Meets** tab pulls them in with nothing but your name:

1. Open **Meets** and search your full name.
2. Pick your profile from the matches — the school/city subtitle helps you spot yourself.
3. SprintGPT imports every distance race (800 m+ on the track, plus all cross country).

- **Source today:** Athletic.net (US high‑school, college & club XC + track).
- **Location‑aware:** set your city/state in Account settings and athletes from your
  area rank first with a **"Your area"** badge — perfect for common names.
- Sprints under 800 m, relays, and field events are skipped; re‑importing is safe.

### 3. CSV or manual entry 📝

Add single runs from the dashboard, or import a CSV
(`date, distance, duration` required; `name, elevation, hr` optional):

```csv
date,distance,duration,name,hr
2026-07-01,10k,45:30,Morning tempo,162
2026-07-03,5k,21:40,Parkrun,175
2026-07-06,21.1km,1:38:20,Long run,151
```

Distances accept `5k`, `10k`, `half`, `marathon`, `8.5km`, `5000m`, `3.1mi`.
Times accept `mm:ss`, `hh:mm:ss`, or `2700s` / `45m` / `1.5h`.

### 4. Live Strava sync — *optional, needs API access* 🔗

<details>
<summary><b>Owner setup + per‑runner connection steps</b></summary>

If you (the app owner) have Strava API access, SprintGPT is multi‑user for live sync.

**Owner setup (once):**
1. Create an app at <https://www.strava.com/settings/api>.
2. Copy `.env.example` to `.env` and fill in `STRAVA_CLIENT_ID` and `STRAVA_CLIENT_SECRET`.
3. Set the app's **Authorization Callback Domain** (`localhost` for local, or your public host).
4. Restart the app.

**For each runner (in the browser):** click **Connect with Strava**, approve access,
and runs import automatically. Use **Sync latest runs** anytime, or **Disconnect** to unlink.

> Behind an HTTPS tunnel/proxy (Cloudflare, ngrok), SprintGPT trusts `X‑Forwarded‑*`
> headers so the OAuth redirect uses the correct `https://` URL.
</details>

---

## 📱 Using it on your phone

Three ways, from simplest to most connected:

- **Native app, offline** — install the [Android APK](#-install-by-platform) and choose
  **Run on this phone**. Works with no internet at all.
- **Native app, over data** — install the APK, choose **Connect to a server**, and enter
  your [self-hosted URL](#-host-it-yourself-run-over-the-internet). Works on mobile data
  and syncs with the website.
- **Web app (PWA)** — on the same Wi‑Fi as your computer:
  1. Run it bound to your local network:
     ```bash
     python main.py --host 0.0.0.0 --port 5000 --no-browser
     ```
  2. On your phone, open `http://<your-computer-ip>:5000`.
  3. In the browser menu, choose **Add to Home Screen** / **Install app** for a
     full‑screen, app‑style experience.

> The app shell is cached by a service worker for fast, offline‑friendly loads. To use
> the PWA over mobile data (not just local Wi‑Fi), host it publicly — see below.

---

## 🌐 Host it yourself (run over the internet)

Want your runs on **every device over mobile data**, with the phone app and website
sharing one account? Run SprintGPT as a real server. It's the same app — just served by
a production web server (**waitress**) instead of the local dev server.

```bash
pip install -r requirements.txt
python serve.py            # listens on 0.0.0.0:8000 (set PORT to change)
```

Then put it behind HTTPS and point your phone at it (**Connect to a server** → your URL).
Pick the setup that fits you:

<details>
<summary><b>🐳 Docker (recommended — one command)</b></summary>

```bash
docker build -t sprintgpt .
docker run -d -p 8000:8000 -v sprintgpt-data:/data \
  -e SPRINTGPT_SECRET="$(openssl rand -hex 32)" \
  -e APP_BASE_URL="https://sprintgpt.example.com" \
  sprintgpt
```

- The `-v sprintgpt-data:/data` volume keeps your database and session key across
  restarts and upgrades (the DB lives at `/data/sprintgpt.db`).
- Front it with a reverse proxy that terminates HTTPS (Caddy, Nginx, or a Cloudflare
  Tunnel). SprintGPT already trusts `X-Forwarded-*`, so external links stay `https://`.
</details>

<details>
<summary><b>☁️ A host with buildpacks (Render, Railway, Fly, Heroku-style)</b></summary>

A `Procfile` is included (`web: python serve.py`). Most platforms will:

1. Detect Python and install `requirements.txt`.
2. Start the `web` process (they inject `PORT`; `serve.py` reads it automatically).
3. Terminate HTTPS for you at their edge.

Set these environment variables in the dashboard, then deploy:

```
SPRINTGPT_SECRET=<a long random string>   # keeps everyone logged in across restarts
APP_BASE_URL=https://your-app.onrender.com # used for links in password-reset emails
SPRINTGPT_DB=/data/sprintgpt.db            # point at a persistent disk/volume
```
</details>

<details>
<summary><b>🖥️ A plain server / VPS (systemd + reverse proxy)</b></summary>

```bash
git clone https://github.com/kiingniick/SprintGPT.git && cd SprintGPT
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
SPRINTGPT_SECRET=$(openssl rand -hex 32) PORT=8000 python serve.py
```

Keep it running with systemd (or `pm2`, `supervisor`, …) and put Caddy/Nginx in front
for HTTPS. On Linux you can also use gunicorn if you prefer:

```bash
gunicorn --workers 1 --threads 8 --bind 0.0.0.0:8000 wsgi:app
```

> **Use one worker with several threads.** SprintGPT stores everything in a single
> SQLite file (WAL mode is enabled for concurrency); a single threaded worker avoids
> cross-process write locks and is plenty for a running club or small community.
</details>

**What to set for a public server**

| Variable | Why it matters |
| --- | --- |
| `SPRINTGPT_SECRET` | Signs login cookies. Set a fixed random value so restarts don't log everyone out. |
| `SPRINTGPT_DB` | Path to the SQLite file — point it at persistent storage you back up. |
| `APP_BASE_URL` | Public `https://` base used to build password‑reset links in emails. |
| `ADMIN_EMAILS` | Who can see the `/admin` analytics dashboard. |
| `SMTP_*` | Optional — send real password‑reset emails (see below). |

> Once it's live, open the app, choose **Connect to a server**, and paste your URL — or
> just open the URL in any browser and **Install** it as a PWA. Same account everywhere.

---

## 👤 Your account & settings

- **Private by default.** Signed‑out visitors only ever see the welcome guide and the
  login / sign‑up pages. Everything else requires logging in.
- **Passwords are hashed** — never stored in plain text.
- **Forgot your password?** Use the link on the log‑in page for a secure, single‑use
  reset link (valid 1 hour) that logs you straight in.
- Click your name (top‑right) to open **Account settings** and update your display
  name, home city/state (improves meet matching), or change your password.

### 🎨 Color themes

Pick your own theme from the dashboard's **Appearance** card — polished presets
(Emerald, Ocean, Violet, Sunset, Rose, Midnight, Daylight) or a **custom** theme from
two accent colors. It's saved to your account and applied across every device.

<details>
<summary><b>Password reset email (optional SMTP)</b></summary>

Password reset works out of the box; without SMTP the link is shown on screen. To send
real emails, add these to your `.env` (see `.env.example`):

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your_app_password      # Gmail: use an App Password, not your login
SMTP_FROM=SprintGPT <you@gmail.com>
SMTP_USE_TLS=true
APP_BASE_URL=https://your-public-url  # optional; used to build links in emails
```

Reset tokens are random, stored **hashed**, single‑use, and expire after 1 hour.
</details>

---

## 💬 The built-in coach

Open the **Coach** tab and ask in plain English:

> *"How much have I run this week?"* · *"How's my fitness?"* · *"Predict my 10K"* ·
> *"What pace should my easy runs be?"* · *"How are my heart‑rate zones?"* ·
> *"What should I do today?"*

- Answers are computed from **your own data** — no external services, so it works
  offline and keeps everything private.
- Tap **Rename** to call your coach anything you like (e.g. "Ada"). It's cosmetic only.
- History is saved to your account; **Clear** wipes it anytime.

---

## 🛠️ For app owners & admins

Admins get an **Analytics** tab at `/admin` with developer‑focused stats — growth
(signups over 24h / 7d / 30d), engagement (activation, Strava links, chat volume,
goals), usage (runs, distance, elevation, sources, themes, locations), and recent
signups. The dashboard **auto‑refreshes live** and is private to admins only.

Set who can see it via `ADMIN_EMAILS` in `.env` (comma‑separated). If left blank, the
**first account you register becomes the owner/admin**:

```
ADMIN_EMAILS=you@example.com,cofounder@example.com
```

---

## 💻 Command line (optional)

Everything is scriptable via the CLI:

```bash
python main.py cli --help
python main.py cli add 10k 45:30 --hr 162 --elevation 80 --name "Tempo"
python main.py cli import-strava export_12345.zip          # free Strava data export
python main.py cli import-csv sample_runs.csv
python main.py cli import-meets "Jordan Rivera" --pick 1    # official race results by name
python main.py cli status
python main.py cli predict
python main.py cli splits marathon 3:30:00
python main.py cli goal half 2026-11-15 --target 1:45:00
python main.py cli plan --all
python main.py cli profile --max-hr 190 --resting-hr 50
```

---

## 🧠 How the coaching works

- **VDOT** is estimated from your performances (Daniels & Gilbert), then mapped to
  easy / marathon / threshold / interval / repetition training paces.
- **Race predictions** take a robust "current potential" from a high percentile of your
  genuine efforts (so one fluke or corrupt GPS record can't skew them), then project it
  with Riegel's endurance law — using an exponent that grows the further a race is
  **beyond your longest actual run**. Predictions stay realistic and improve
  progressively as you build endurance.
- **Training load** (CTL/ATL/TSB) uses exponentially‑weighted daily load — heart‑rate
  TRIMP when HR is available, otherwise distance × relative intensity.
- **Per‑run HR zones** model beat‑by‑beat HR as a distribution around the average and
  integrate over each zone's band, so a single average HR still yields a realistic
  time‑in‑zone breakdown.
- **Splits** divide a total time evenly across the distance, with the final partial
  mile/km scaled to its exact length.
- **Plans** periodize the weeks from today to race day, growing volume with a recovery
  cutback every 4th week and selecting quality sessions to suit the phase and goal distance.

---

## 🗂️ Project layout

```
main.py                  # local dev launcher for the web app (or `cli` passthrough)
serve.py                 # production server (waitress) for hosting it publicly
wsgi.py                  # WSGI entry point (gunicorn/waitress: `wsgi:app`)
Dockerfile, Procfile     # container + buildpack deploy for self-hosting
requirements.txt, .env.example, README.md, sample_runs.csv
sprintgpt/
  webapp.py              # Flask app + routes (accounts, dashboard, docs, admin, sw.js)
  templates/             # welcome, login, signup, account, admin, docs, dashboard, chat, meets, plan, splits, activity, base
  static/style.css       # mobile-first responsive dark UI
  static/manifest.webmanifest, sw.js, icon.svg   # PWA (installable app)
  config.py              # env / token loading
  models.py              # Activity, Goal, Profile, Workout, WeeklyPlan
  storage.py             # SQLite persistence
  strava.py              # OAuth (web + CLI) + activity sync
  chat.py                # built-in data-driven coach chatbot engine
  themes.py              # account color-theme presets + custom palette logic
  importer.py            # manual + CSV + Strava-export import, unit parsing
  meets.py               # import race results by name (Athletic.net XC + track)
  mailer.py              # SMTP email sender (password-reset links)
  analysis.py            # VDOT, paces, CTL/ATL/TSB, HR zones + TRIMP
  predictor.py           # endurance-aware, progressive race prediction
  planner.py             # periodized plan generation
  cli.py                 # rich-powered command line
```

---

<div align="center">

**SprintGPT is a training aid, not medical advice. Listen to your body.** 💚

Released under the [MIT License](https://github.com/kiingniick/SprintGPT/blob/main/LICENSE).

</div>
