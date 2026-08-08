# SprintGPT on iPhone / iPad 🍏

There are **two** ways to run SprintGPT on iOS. Pick based on whether you want to
pay Apple.

| Path | Cost | Needs a Mac? | App Store / TestFlight? | Best for |
| --- | --- | --- | --- | --- |
| **PWA (Add to Home Screen)** | Free | No | No | Getting testers on iPhones **today** |
| **Native app (Capacitor)** | **$99/yr** Apple Developer Program | No (cloud build) | **Yes, TestFlight** | Real App Store distribution |

---

## Path 1 — PWA (free, works right now) ✅

No App Store, no Apple fee, no Mac. Because SprintGPT is a website, iOS can pin it
to the Home Screen and run it full-screen like an app (with the real app icon).

1. Open **[the live app](https://kiingniick.github.io/SprintGPT/)** in **Safari**
   (must be Safari — iOS blocks Home-Screen install from Chrome).
2. Tap **Share** (the square-with-an-up-arrow), then **Add to Home Screen → Add**.
3. Launch it from the new icon. Done.

Send your 20 testers that link and they're running in ~15 seconds. The
[`/install`](https://kiingniick.github.io/SprintGPT/install) page walks them
through it automatically when it detects an iPhone.

---

## Path 2 — Native app on TestFlight 🚀

> **Heads up (the honest bit):** TestFlight **requires the paid Apple Developer
> Program — $99/year**. Apple does not allow TestFlight, or installing on real
> iPhones, with a free account. There is no workaround. Everything below is
> scaffolded and ready — it just can't upload until you're enrolled.

The app is a thin **WKWebView wrapper (Capacitor)** that loads your hosted
server (same accounts/data as web + Android). It does **not** run Python
on-device — iOS can't embed the Chaquopy engine the Android app uses, so iPhone
users always talk to your self-hosted server.

### One-time setup (do this once)

1. **Enroll** in the [Apple Developer Program](https://developer.apple.com/programs/enroll/) ($99/yr).
2. In [App Store Connect](https://appstoreconnect.apple.com) → **Apps → +** →
   create an app with bundle id **`com.sprintgpt.app`**.
3. Create an **App Store Connect API key**: Users and Access → Integrations →
   App Store Connect API → generate a key with **App Manager** access. Download
   the `AuthKey_XXXX.p8` (you only get it once) and note the **Key ID** and
   **Issuer ID**. Note your **Team ID** under Membership.

### Build in the cloud (no Mac) — recommended

Add these repo secrets (**Settings → Secrets and variables → Actions**):

| Secret | Where to find it |
| --- | --- |
| `APPLE_TEAM_ID` | App Store Connect → Membership |
| `ASC_KEY_ID` | the API key's Key ID |
| `ASC_ISSUER_ID` | the API key's Issuer ID |
| `ASC_PRIVATE_KEY` | paste the **entire** `AuthKey_XXXX.p8` file contents |

Then: **Actions → iOS TestFlight → Run workflow**, bump the **build number**, and
run it. GitHub spins up a macOS runner, builds a signed `.ipa`, and uploads it to
TestFlight (see [`.github/workflows/ios-testflight.yml`](../.github/workflows/ios-testflight.yml)).

### Build locally (if you have a Mac with Xcode)

```bash
cd ios
npm install
npx cap add ios        # generates ios/App (an Xcode project)
npx cap sync ios
npx cap open ios        # opens Xcode → set your Team → Product ▸ Archive ▸ Distribute
```

### Invite testers

App Store Connect → your app → **TestFlight**:
- **Internal testing:** add up to 100 people on your team — available instantly,
  no review.
- **External testing:** create a public/shared link for up to 10,000 testers —
  requires a quick one-time Beta App Review.

---

## How it's wired

- [`capacitor.config.json`](capacitor.config.json) — `server.url` points the app
  at `https://kiingniick.github.io/SprintGPT/` (the stable link that always
  redirects to your current server), exactly like the Android app's default.
- [`www/index.html`](www/index.html) — offline fallback shell (Capacitor needs a
  `webDir`; the app normally loads the remote site).
- The `ios/App` Xcode project is **generated, not committed** (`npx cap add ios`).
- App icon comes from `sprintgpt/static/icon-1024.png` (regenerate any icon with
  `python tools/make_icons.py`).

To point the app at a different server, edit `server.url` and re-run
`npx cap sync ios`.
