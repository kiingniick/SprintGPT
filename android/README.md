# SprintGPT for Android (native, on-device)

This is a fully native Android app that **runs the SprintGPT Python/Flask server
on the phone itself** (via [Chaquopy](https://chaquo.com/chaquopy/)) and displays
it in a full-screen WebView. No internet connection or external server is needed —
everything, including the database, lives on the device.

## How it works

- `app/src/main/python/android_main.py` starts the Flask app on `127.0.0.1:5000`,
  storing its SQLite database in the app's private files directory.
- `MainActivity.java` boots the embedded Python interpreter, then loads the local
  server in a WebView (with a loading screen and auto-retry while the server warms up).

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
