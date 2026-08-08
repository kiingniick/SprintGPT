"""WSGI entry point for production servers.

Point any WSGI server at this module's ``app`` object, e.g.:

    gunicorn --workers 1 --threads 8 --bind 0.0.0.0:8000 wsgi:app   # Linux
    waitress-serve --host=0.0.0.0 --port=8000 wsgi:app              # any OS

Prefer a single worker with multiple threads: SprintGPT stores everything in a
single SQLite file, and one threaded worker avoids cross-process write locks.
"""
from sprintgpt.webapp import create_app

app = create_app()
