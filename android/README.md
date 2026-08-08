# SprintGPT for Android (native app)

A native Android app that displays SprintGPT in a full-screen WebView. On first
launch it asks how to run:

- **Run on this phone** — it starts the SprintGPT Python/Flask server *on the phone
  itself* (via [Chaquopy](https://chaquo.com/chaquopy/)). No internet needed;
  everything, including the database, lives on the device.
- **Connect to a server** — it loads a SprintGPT you host yourself (see the repo
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
