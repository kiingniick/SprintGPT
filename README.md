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
- [What you get](#-what-you-get)
- [Bringing in your runs](#-bringing-in-your-runs)
- [Using it on your phone](#-using-it-on-your-phone)
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

SprintGPT is a mobile‑first Progressive Web App:

1. Run it bound to your local network:
   ```bash
   python main.py --host 0.0.0.0 --port 5000 --no-browser
   ```
2. On your phone (same Wi‑Fi), open `http://<your-computer-ip>:5000`.
3. In the browser menu, choose **Add to Home Screen** / **Install app**. It launches
   full‑screen with an app‑style bottom tab bar.

> The app shell is cached by a service worker for fast, offline‑friendly loads. For
> installability over the network, browsers may require HTTPS — a tool like `ngrok` or
> a Cloudflare tunnel gives you a quick HTTPS URL.

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
main.py                  # launches the web app (or `cli` passthrough)
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
