# Paceloop for Android (native app)

A native Android app that displays Paceloop in a full-screen WebView. On first
launch it asks how to run:

- **Run on this phone** — it starts the Paceloop Python/Flask server *on the phone
  itself* (via [Chaquopy](https://chaquo.com/chaquopy/)). No internet needed;
  everything, including the database, lives on the device.
- **Connect to a server** — it loads a Paceloop you host yourself (see the repo
  root `README.md` → "Host it yourself"). Works over mobile data or Wi-Fi, and the
  app and website share the same account and data.

The choice is stored in `SharedPreferences` and can be changed anytime from the
in-app **Account settings → App connection** link, the **Connection** menu item, or
the connection-error screen (all navigate to the `sprintgpt://settings` scheme,
which `MainActivity` intercepts to show the native setup screen).

## How it works

- `app/src/main/python/android_main.py` starts the Flask app on `127.0.0.1:5000`,
  storing its SQLite database in the app's private files directory. It's only
  launched in on-device mode.
- `MainActivity.java` reads the saved mode. In on-device mode it boots the embedded
  Python interpreter and loads `http://127.0.0.1:5000/` (with a loading screen and
  auto-retry while the server warms up). In server mode it loads your URL directly
  and shows a retry/error screen if it's unreachable.
- The WebView's User-Agent is tagged with `SprintGPTApp/1.0` so the web app knows
  it's running inside the app and shows the connection controls.

### Staying up to date

- A few seconds after launch, `MainActivity.checkForUpdate()` fetches a small public
  manifest — [`app-version.json`](https://kiingniick.github.io/SprintGPT/app-version.json)
  hosted on GitHub Pages — off the UI thread. Using Pages means the check works even
  in fully offline/on-device mode or when your server is down.
- If the manifest's `versionCode` is greater than the installed `BuildConfig.VERSION_CODE`,
  it shows an **Update available** dialog with **Update now** (opens `apkUrl`), **Later**,
  and **Skip this version** (remembered in `SharedPreferences` so the user isn't nagged
  until an even newer build). Network failures are swallowed silently.

## Building the APK

Requirements: JDK 17, the Android SDK (platform 34, build-tools 34), and a Python
**3.12** interpreter on the build machine (Chaquopy's `buildPython`).

1. Sync the Python sources from the repo root into the app (they're not committed
   here to avoid duplication):

   ```powershell
   Copy-Item ..\sprintgpt app\src\main\python\sprintgpt -Recurse -Force
   Copy-Item ..\README.md  app\src\main\python\README.md -Force
   ```

2. Build, pointing Chaquopy at your Python 3.12:

   ```powershell
   .\gradlew.bat assembleDebug -PbuildPython="C:/path/to/python3.12/python.exe"
   ```

3. The installable APK is written to
   `app/build/outputs/apk/debug/app-debug.apk`. Copy it to an Android phone and
   open it (you may need to allow "install from unknown sources").

> Tip: bake in the recommended server so "Connect to a server" is pre-filled:
> `.\gradlew.bat assembleDebug -PbuildPython=... -PserverUrl="https://kiingniick.github.io/SprintGPT/"`

## Publishing a release (so auto-update works)

The in-app updater and the website's one-tap download both rely on two things being
in sync. When you ship a new build:

1. **Bump the version** in `app/build.gradle` (`versionCode` **and** `versionName`).
2. **Build** the APK (steps above).
3. **Create a GitHub release** and upload the APK **twice**: once versioned
   (`SprintGPT-<version>.apk`) and once with the fixed name **`SprintGPT.apk`**. The
   fixed name is what powers the permanent download link
   `releases/latest/download/SprintGPT.apk` used by the installer page.
4. **Update the manifest** [`app-version.json`](https://kiingniick.github.io/SprintGPT/app-version.json)
   on the `gh-pages` branch to the new `versionCode`/`versionName` (and a short
   `notes` line). Existing users are reminded on their next launch.
