"""On-device entry point.

Chaquopy calls main(files_dir) from the Android app on a background thread. We
point SprintGPT's storage and session secret at the app's private files
directory (the only writable location on Android), then run the Flask server on
localhost so the WebView can load it like a normal website — except everything
runs entirely on the phone.
"""
import os
import secrets

_started = False


def main(files_dir):
    global _started
    if _started:
        return
    _started = True

    # Storage lives in the app's private, writable files dir.
    os.environ.setdefault("SPRINTGPT_DB", os.path.join(files_dir, "sprintgpt.db"))

    # A stable session secret, generated once and kept in the files dir (so the
    # config layer never tries to write to the read-only app bundle).
    secret_path = os.path.join(files_dir, ".secret_key")
    key = None
    try:
        if os.path.exists(secret_path):
            with open(secret_path, "r", encoding="utf-8") as fh:
                key = fh.read().strip()
    except OSError:
        key = None
    if not key:
        key = secrets.token_hex(32)
        try:
            with open(secret_path, "w", encoding="utf-8") as fh:
                fh.write(key)
        except OSError:
            pass
    os.environ["SPRINTGPT_SECRET"] = key

    from sprintgpt.webapp import create_app

    app = create_app()
    # threaded=True so the WebView's requests don't block each other; no reloader
    # (there's no main thread / signal handling inside the app).
    app.run(host="127.0.0.1", port=5000, threaded=True, use_reloader=False)
