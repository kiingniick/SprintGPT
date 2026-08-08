# SprintGPT

Your AI running coach, in the browser. SprintGPT tracks your running progress
from **Strava** (and manually imported times), analyzes your fitness and
**heart-rate training balance**, predicts race times, and generates
**personalized, periodized training plans** built around your goal race.

## What it does

- **Personal accounts** — sign up with an email and password to get your own private
  space. All your running data, Strava connection, goals, and heart-rate profile are
  linked to your account and isolated from everyone else. Runs you add before signing
  up are automatically carried into your new account.
- **Friendly start guide** — first-time visitors are greeted with a welcome page that
  walks them through getting started in three simple steps.
- **Coach chatbot** — chat with a built-in AI coach that answers using *your own* data
  (mileage, fitness, paces, heart-rate zones, race predictions, and what to run today).
  It runs fully offline (no API keys), and you can rename your coach anything you like —
  purely cosmetic, it still knows all your training.
- **Mobile-first web app (installable PWA)** — a responsive, app-style UI with a
  bottom tab bar, touch-friendly controls, and offline app-shell caching. Runners
  can "Add to Home Screen" and use it like a native app.
- **Web dashboard** — a modern UI showing fitness, fatigue, form, weekly volume,
  total elevation, heart-rate zone distribution, training paces, race
  predictions, and recent runs.
- **Imports your data** several ways: a free **Strava data export** (no API or
  subscription needed — the recommended first-run setup), live **Strava OAuth**
  sync, manual entries / CSV files, or your **official race results by name**.
- **Import race results by name** — type your name to search public results
  databases (Athletic.net cross country & track), pick your profile from the
  matches, and pull every distance race (800 m+ and all XC) straight into your
  log. No files, no accounts to link; re-importing safely skips duplicates.
- **Heart-rate zones** — set your max/resting HR (or estimate from age) to get
  five-zone (Karvonen or %HRmax) boundaries, an overall zone-distribution chart,
  a **per-run time-in-zone breakdown**, and heart-rate-based TRIMP training load.
- **Elevation tracking** — climbing is captured per run (Strava, CSV, or manual)
  and rolled up into a total-elevation stat and per-run detail.
- **Splits calculator** — enter one total time for any distance and get exact
  even **per-mile and per-km splits** (with cumulative times and pace).
- **Predicts race times** with a machine-learning model trained on *your own*
  runs, backed by a physiology model (VDOT / Riegel) when data is scarce.
- **Generates workout plans** with Base → Build → Peak → Taper periodization,
  progressive overload, recovery weeks, and paces personalized to your fitness.

## Setup

```bash
pip install -r requirements.txt
```

## Run the web app

```bash
python main.py                 # opens http://127.0.0.1:5000 in your browser
python main.py --port 8000     # custom port
python main.py --no-browser    # don't auto-open a browser
```

First-time visitors land on a **welcome / start guide** that explains how SprintGPT
works. From there you can **create a free account** (email + password), **log in**, or
explore the demo. Once signed in, everything you do — runs, Strava data, goals, and
heart-rate profile — is saved privately to your account.

From the dashboard you can add runs, upload a CSV, import a Strava export, set your
heart-rate profile, set a goal race, connect Strava, and generate a training plan.

### Accounts

- **The app is private by default:** signed-out visitors only ever see the welcome /
  start guide and the login / sign-up pages. The dashboard, plans, splits, imports, and
  Strava all require logging in.
- **Sign up / Log in** from the top-right of any page (or the welcome guide).
- Passwords are stored hashed (never in plain text).
- **Forgot your password?** Use the link on the log-in page. You'll get an email
  with a secure, single-use link (valid 1 hour) to set a new password — and you're
  logged straight in once you do. See [Password reset email](#password-reset-email)
  for optional SMTP setup; without it, the reset link is shown on screen instead.
- All your runs, Strava connection, goals, and heart-rate profile are linked to your
  account and isolated from other users.

### Account settings

Click your name in the top-right to open **Account settings**, where you can:

- Update your **display name**.
- Set your **home city and state/province** — used to match the right athlete when
  importing race results by name (see below). Full state names ("Oregon") and postal
  codes ("OR") both work.
- **Change your password** (verifies your current one first).

### Password reset email

Password reset works out of the box. If you configure SMTP, reset links are emailed;
otherwise the link is shown on screen (handy for local, single-owner installs).

To send real emails, add these to your `.env` (see `.env.example`):

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your_app_password      # Gmail: use an App Password, not your login
SMTP_FROM=SprintGPT <you@gmail.com>
SMTP_USE_TLS=true
APP_BASE_URL=https://your-public-url  # optional; used to build links in emails
```

Reset tokens are random, stored **hashed**, single-use, and expire after 1 hour.

### Color themes

Every account can pick its own color theme from the dashboard's **Appearance** card. Choose
from polished presets (Emerald, Ocean, Violet, Sunset, Rose, Midnight, and a light
"Daylight" theme) or build a **custom** theme from two accent colors — SprintGPT even picks
readable text automatically. Your choice is saved to your account and applied across the
whole site on every device, injected as CSS variables so the entire UI recolors instantly.

### Use it on your phone (mobile / install as an app)

SprintGPT is a mobile-first Progressive Web App. To use it on your phone:

1. Run it on your computer, binding to your local network:

   ```bash
   python main.py --host 0.0.0.0 --port 5000 --no-browser
   ```

2. On your phone (same Wi-Fi), open `http://<your-computer-ip>:5000`.
3. In the browser menu choose **Add to Home Screen** / **Install app**. It
   launches full-screen with an app-style bottom tab bar (Home, Plan, Splits).

The app shell and assets are cached by a service worker for fast loads. (For
installability over the network, browsers may require HTTPS — a tool like
`ngrok` or a small reverse proxy gives you a quick HTTPS URL for testing.)

Want demo data first? Seed some sample runs, then launch:

```bash
python main.py cli seed
python main.py
```

## Heart-rate zones

Set your profile in the dashboard's **Heart-Rate Profile** card (or via the CLI):

```bash
python main.py cli profile --max-hr 190 --resting-hr 50
python main.py cli profile --age 30            # estimates max HR (Tanaka)
```

- With a **resting HR**, zones use heart-rate reserve (Karvonen) and training
  load is computed with **TRIMP** (more accurate than pace-based load).
- Without one, zones fall back to **%HRmax**.

Zones: Z1 Recovery, Z2 Aerobic/Easy, Z3 Tempo, Z4 Threshold, Z5 VO2max.

Click any run on the dashboard to open its detail page, which shows a
**per-run HR-zone breakdown**. Because a run rarely holds a single heart rate,
the time-in-zone is estimated from the run's average HR using a distribution
model (exact stream data is used when available from Strava).

## Splits calculator

Open the **Splits** tab (or use the CLI) to turn one total time into exact even
splits:

```bash
python main.py cli splits marathon 3:30:00           # per-mile splits
python main.py cli splits 10k 45:00 --unit km        # per-km splits
```

Each activity's detail page also shows its per-mile and per-km splits.

## Chat with your coach

Open the **Coach** tab to chat with SprintGPT's built-in coach. Ask things like
"How much have I run this week?", "How's my fitness?", "Predict my 10K", "What pace
should my easy runs be?", "How are my heart-rate zones?", or "What should I do today?".

- Answers are computed from **your own account data** — no external services or API
  keys, so it works offline and keeps your data private.
- Tap **Rename** in the chat header to call your coach whatever you like (e.g. "Ada").
  The name is cosmetic only; functionality is identical.
- Conversation history is saved to your account, and **Clear** wipes it any time.

## Import your race results by name

Your official meet times usually live on results sites, not in a training app.
The **Meets** tab lets you pull them in with nothing but your name:

1. Open **Meets** and search your full name (as it appears on results).
2. Pick your profile from the matches — the school/city subtitle helps you spot
   yourself when there are name-alikes.
3. SprintGPT imports every distance race off that profile (800 m and up on the
   track, plus all cross country) as race activities. They immediately feed your
   fitness, race predictions, and coach chat.

- Source today: **Athletic.net** (US high-school, college, and club XC + track).
  The importer is provider-based, so more sites can be added over time.
- **Location-aware matching:** if you've set your city/state in account settings,
  athletes from your area are ranked first and flagged **"Your area"**, so it's easy
  to pick the real you (and get accurate times) even with a common name.
- Sprints under 800 m, relays, and field events are skipped so they don't skew
  your distance-running analytics.
- Re-importing is safe — races already in your log are skipped automatically.

From the command line:

```bash
python main.py cli import-meets "Jordan Rivera"            # list matches
python main.py cli import-meets "Jordan Rivera" --pick 1   # import match #1
```

> Note: results sites sit behind bot protection and can occasionally rate-limit
> automated requests. If a search is temporarily blocked, wait a minute and retry.

## Import from Strava — no subscription, no API setup (recommended)

Strava now gates its API behind a paid tier, but **every athlete can still export
their full run history for free**. SprintGPT reads that export directly, so this is
the easiest way to get started — it's built into first-run setup on the dashboard.

1. On <https://www.strava.com/athlete/delete_your_account>, go to **Settings →
   My Account → Download or Delete Your Account**.
2. Under **Download Request**, click **Request Your Archive**.
3. Strava emails you a download link (usually within a few hours).
4. Back in SprintGPT, on the home screen's **"Import your Strava history"** card,
   upload the `.zip` (or its `activities.csv`). Your runs — with distance, time,
   elevation, and average HR — import instantly and stay private to your account.

SprintGPT only reads `activities.csv` from the archive, and every run keeps its
Strava activity id, so re-importing (or later live-syncing) never creates duplicates.

From the CLI:

```bash
python main.py cli import-strava path/to/export_12345.zip
python main.py cli import-strava path/to/activities.csv
```

## Connecting Strava live (optional, requires API access)

If you (the app owner) have Strava API access, SprintGPT is also multi-user for
**live** OAuth sync: you register one Strava API app, and then **each visitor
connects their own Strava account** from the site.

Owner setup (once):

1. Create an app at <https://www.strava.com/settings/api>.
2. Copy `.env.example` to `.env` and fill in `STRAVA_CLIENT_ID` and
   `STRAVA_CLIENT_SECRET`.
3. Set the app's **Authorization Callback Domain** to the domain you serve from:
   - `localhost` for local testing, or
   - your public host, e.g. `your-subdomain.trycloudflare.com` (Strava matches
     the domain and its subdomains).
4. Restart the app.

For each runner (in the browser):

1. Open the site and click **Connect with Strava**.
2. Approve access on Strava — you're redirected back and your runs import
   automatically. Use **Sync latest runs** anytime, or **Disconnect** to unlink.

> Behind an HTTPS tunnel/proxy (Cloudflare, ngrok), SprintGPT trusts
> `X-Forwarded-*` headers so the OAuth redirect uses the correct `https://` URL.

New here and just want to look around? Click **Explore demo** on the home screen
(after `python main.py cli seed`).

## Importing your own times

Add single runs from the dashboard, or import a CSV
(headers: `date, distance, duration` and optional `name, elevation, hr`):

```csv
date,distance,duration,name,hr
2026-07-01,10k,45:30,Morning tempo,162
2026-07-03,5k,21:40,Parkrun,175
2026-07-06,21.1km,1:38:20,Long run,151
```

Distances accept `5k`, `10k`, `half`, `marathon`, `8.5km`, `5000m`, `3.1mi`.
Times accept `mm:ss`, `hh:mm:ss`, or `2700s` / `45m` / `1.5h`.

## Command-line interface (optional)

Everything is also scriptable via the CLI:

```bash
python main.py cli --help
python main.py cli add 10k 45:30 --hr 162 --elevation 80 --name "Tempo"
python main.py cli import-strava export_12345.zip   # free Strava data export
python main.py cli import-csv sample_runs.csv
python main.py cli import-meets "Jordan Rivera" --pick 1   # official race results by name
python main.py cli status
python main.py cli predict
python main.py cli splits marathon 3:30:00
python main.py cli goal half 2026-11-15 --target 1:45:00
python main.py cli plan --all
python main.py cli strava-auth && python main.py cli sync
```

## Project layout

```
main.py                  # launches the web app (or `cli` passthrough)
requirements.txt, .env.example, README.md, sample_runs.csv
sprintgpt/
  webapp.py              # Flask app + routes (accounts, dashboard, splits, activity, plan, sw.js)
  templates/             # welcome, login, signup, forgot, reset, account, dashboard, chat, meets, plan, splits, activity, base
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
  predictor.py           # ML race prediction + fallbacks
  planner.py             # periodized plan generation
  cli.py                 # rich-powered command line
```

## How the coaching works

- **VDOT** is estimated from your performances (Daniels & Gilbert), then mapped
  to easy / marathon / threshold / interval / repetition training paces.
- **Training load** (CTL/ATL/TSB) uses exponentially-weighted daily load —
  heart-rate TRIMP when HR is available, otherwise distance × relative intensity.
- **Per-run HR zones** model beat-by-beat HR as a normal distribution around the
  average and integrate over each zone's bpm band, so a single average HR still
  yields a realistic time-in-zone breakdown.
- **Splits** divide a total time evenly across the distance (constant pace),
  with the final partial mile/km scaled to its exact length.
- **Predictions** blend a gradient-boosted model (once you have ~12+ runs) with
  the VDOT model so extrapolations stay physiologically sensible.
- **Plans** periodize the weeks from today to race day, growing volume with a
  recovery cutback every 4th week and selecting quality sessions appropriate to
  the phase and your goal distance.

> SprintGPT is a training aid, not medical advice. Listen to your body and
> consult a professional for injuries or health concerns.

## License

Released under the [MIT License](LICENSE).
