"""Paceloop entry point.

By default this launches the Paceloop web app:

    python main.py                # open http://127.0.0.1:5000

The command-line interface is still available for scripting:

    python main.py cli --help
    python -m sprintgpt.cli --help
"""
import argparse
import sys
import webbrowser
from threading import Timer

from sprintgpt.webapp import create_app


def run_web(host: str, port: int, open_browser: bool) -> None:
    app = create_app()
    url = f"http://{host}:{port}"
    print(f"Paceloop is running at {url}  (press Ctrl+C to stop)")
    if open_browser:
        Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host=host, port=port, debug=False)


def main() -> None:
    # Delegate to the CLI when the first argument is `cli`.
    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        from sprintgpt.cli import main as cli_main

        cli_main(sys.argv[2:])
        return

    parser = argparse.ArgumentParser(description="Launch the Paceloop web app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--no-browser", action="store_true", help="Don't auto-open a browser")
    args = parser.parse_args()
    run_web(args.host, args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
