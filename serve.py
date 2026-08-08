"""Run SprintGPT as a public, production-grade server.

Unlike ``python main.py`` (Flask's built-in development server, meant for local
use), this serves the app with waitress: a battle-tested, cross-platform WSGI
server that's happy handling real traffic on Windows, macOS, and Linux.

    python serve.py                 # listen on 0.0.0.0:8000
    PORT=5000 python serve.py       # custom port (env var)
    python serve.py --port 5000     # custom port (flag)

Put it behind a reverse proxy (Caddy/Nginx/Cloudflare) or a platform that
terminates HTTPS for you, and set APP_BASE_URL so emailed links use your public
address. See the README's "Host it yourself" section.
"""
from __future__ import annotations

import argparse
import os

from sprintgpt.webapp import create_app

app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve SprintGPT for real users.")
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--threads", type=int, default=int(os.getenv("THREADS", "8")))
    args = parser.parse_args()

    try:
        from waitress import serve
    except ImportError:
        print(
            "waitress isn't installed (pip install waitress). Falling back to the\n"
            "development server, which is fine for testing but not for real traffic."
        )
        app.run(host=args.host, port=args.port, threaded=True, use_reloader=False)
        return

    print(f"SprintGPT is serving at http://{args.host}:{args.port}  (Ctrl+C to stop)")
    serve(app, host=args.host, port=args.port, threads=args.threads)


if __name__ == "__main__":
    main()
