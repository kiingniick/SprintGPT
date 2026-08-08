"""Paceloop web application (Flask).

The primary interface: each visitor gets their own private space (identified by a
signed session cookie) where they can connect their Strava account, import runs,
track progress and heart-rate zones, calculate splits, and get AI training plans.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import tempfile
import zipfile
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from flask import (
    Flask,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

from .analysis import (
    activity_zone_breakdown,
    classify_hr,
    compute_fitness,
    compute_splits,
    format_pace,
    format_time,
    hr_zone_bounds,
    total_elevation_gain,
    training_paces,
    weekly_volume_series,
    zone_distribution,
)
from .chat import SUGGESTIONS, build_reply
from .config import load_config
from .health import ft_in_to_cm, lb_to_kg, strength_recommendation
from .themes import THEMES, DEFAULT_THEME, palette_to_css, resolve_palette
from .importer import (
    import_csv,
    import_strava_export,
    make_manual_activity,
    parse_distance,
    parse_duration,
)
from .mailer import MailerError, send_email
from .meets import PROVIDERS, MeetImportError, import_results, search_athletes
from .models import Goal, Profile
from .platforms import PLATFORMS, RELEASES_URL, detect_platform
from .planner import PlanContext, generate_plan, race_week_note
from .predictor import PacePredictor
from .recovery import install_crash_handler, read_incidents
from .storage import Storage
from .strava import StravaClient, StravaError, StravaTokens

ZONE_COLORS = ["#4ade80", "#22d3ee", "#facc15", "#fb923c", "#f87171"]


def _reset_email_text(link: str) -> str:
    return (
        "Hi,\n\n"
        "We received a request to reset your Paceloop password. Open the link "
        "below to choose a new one (it expires in 1 hour):\n\n"
        f"{link}\n\n"
        "Once you set a new password you'll be logged in automatically.\n\n"
        "If you didn't request this, you can safely ignore this email - your "
        "password won't change.\n\n"
        "- Paceloop"
    )


def _reset_email_html(link: str) -> str:
    return f"""\
<div style="font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:520px;margin:0 auto;color:#0f172a">
  <h2 style="margin:0 0 12px">Reset your Paceloop password</h2>
  <p>We received a request to reset your password. Click the button below to
     choose a new one. This link expires in <strong>1 hour</strong>.</p>
  <p style="margin:24px 0">
    <a href="{link}" style="background:#10b981;color:#04231a;text-decoration:none;
       font-weight:700;padding:12px 22px;border-radius:10px;display:inline-block">
       Choose a new password</a>
  </p>
  <p>Once you set a new password, you'll be logged in automatically.</p>
  <p style="color:#64748b;font-size:13px">If you didn't request this, you can safely
     ignore this email &mdash; your password won't change.</p>
  <p style="color:#64748b;font-size:13px">Or paste this link into your browser:<br>
     <a href="{link}" style="color:#0ea5e9">{link}</a></p>
</div>"""


def _store() -> Storage:
    return Storage(load_config().db_path)


def _current_user(store: Storage) -> int:
    """Return the logged-in account's user id.

    The login gate (before_request) guarantees a valid `uid` on every protected
    route, so this is a simple lookup.
    """
    return int(session["uid"])


def _is_admin_email(email: str, uid: int, first_uid: Optional[int]) -> bool:
    """Admin if listed in ADMIN_EMAILS, or (when none set) the first account."""
    if not email:
        return False
    admins = load_config().admin_emails
    if admins:
        return email.strip().lower() in admins
    # Bootstrap: with no ADMIN_EMAILS configured, the earliest account is owner.
    return first_uid is not None and uid == first_uid


def _strava_client_for(store: Storage, user_id: int) -> StravaClient:
    """Build a StravaClient bound to a user's stored tokens (with auto-persist)."""
    cfg = load_config()
    creds = (cfg.strava_client_id, cfg.strava_client_secret)
    stored = store.get_strava(user_id)
    tokens = None
    if stored:
        tokens = StravaTokens(stored["access_token"], stored["refresh_token"], stored["expires_at"])

    def on_refresh(new: StravaTokens) -> None:
        # Persist refreshed tokens; a fresh connection keeps the same DB row.
        refresh_store = _store()
        refresh_store.set_strava(user_id, None, None, new.access_token,
                                 new.refresh_token, new.expires_at)
        refresh_store.close()

    return StravaClient(*creds, tokens=tokens, on_refresh=on_refresh)


def create_app() -> Flask:
    app = Flask(__name__)
    cfg = load_config()
    app.secret_key = cfg.secret_key
    # Strava export archives can be large (they bundle GPS files). Allow up to 1 GB.
    app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024
    # Trust X-Forwarded-* from a single proxy (e.g. Cloudflare tunnel / ngrok) so
    # url_for(_external=True) produces correct https:// OAuth redirect URLs.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.jinja_env.filters["pace"] = lambda s: format_pace(s) if s else "-"
    app.jinja_env.filters["clock"] = lambda s: format_time(s) if s else "-"

    @app.context_processor
    def inject_account():
        """Expose the logged-in account and its color theme to every template."""
        account = None
        theme_key = DEFAULT_THEME
        accent = accent2 = None
        uid = session.get("uid")
        if uid:
            store = _store()
            row = store.get_user(uid)
            first_uid = store.first_user_id()
            store.close()
            if row and row["email"]:
                account = {
                    "name": row["account_name"] or row["email"].split("@")[0],
                    "email": row["email"],
                    "city": row["city"] or "",
                    "state": row["state"] or "",
                }
                theme_key = row["theme"] or DEFAULT_THEME
                accent, accent2 = row["accent"], row["accent2"]
                account["bot_name"] = row["bot_name"] or "Coach"
                account["is_admin"] = _is_admin_email(row["email"], uid, first_uid)
        palette = resolve_palette(theme_key, accent, accent2)
        # The Android app tags its WebView User-Agent so we can surface the
        # "App connection" control (which lets people switch between running
        # on-device and connecting to a hosted server).
        is_app = "SprintGPTApp" in (request.headers.get("User-Agent") or "")
        return {
            "account": account,
            "is_app": is_app,
            "theme_css": palette_to_css(palette),
            "current_theme": theme_key,
            "custom_accent": accent or palette["accent"],
            "custom_accent2": accent2 or palette["accent2"],
            "themes": [{"key": k, **v} for k, v in THEMES.items()],
        }

    # Pages visible without an account. Everything else requires logging in, so
    # the only thing a signed-out visitor ever sees is the start guide.
    PUBLIC_ENDPOINTS = {"welcome", "login", "signup", "logout", "service_worker",
                        "static", "forgot_password", "reset_password", "docs", "readme_raw",
                        "install"}

    @app.before_request
    def require_login():
        endpoint = request.endpoint
        if endpoint is None or endpoint in PUBLIC_ENDPOINTS:
            return None
        uid = session.get("uid")
        if not uid:
            return redirect(url_for("welcome"))
        # Validate the account still exists; otherwise force a clean re-login.
        store = _store()
        exists = store.get_user(uid) is not None
        store.close()
        if not exists:
            session.clear()
            return redirect(url_for("welcome"))
        return None

    # ---- PWA service worker -------------------------------------------------
    @app.route("/sw.js")
    def service_worker():
        resp = make_response(app.send_static_file("sw.js"))
        resp.headers["Content-Type"] = "application/javascript"
        resp.headers["Service-Worker-Allowed"] = "/"
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    # ---- welcome / start guide ---------------------------------------------
    @app.route("/welcome")
    def welcome():
        # Logged-in users don't need the sign-up guide; send them to their dashboard.
        if session.get("uid"):
            return redirect(url_for("dashboard"))
        platform = detect_platform(request.headers.get("User-Agent", ""))
        return render_template("welcome.html", detected_platform=platform)

    # ---- install / get the app (platform-aware) ----------------------------
    @app.route("/install")
    def install():
        platform = detect_platform(request.headers.get("User-Agent", ""))
        return render_template(
            "install.html",
            platforms=PLATFORMS,
            detected_platform=platform,
            releases_url=RELEASES_URL,
        )

    # ---- documentation (renders the project README) ------------------------
    README_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "README.md")

    @app.route("/docs")
    def docs():
        return render_template("docs.html")

    @app.route("/readme.md")
    def readme_raw():
        try:
            with open(README_PATH, "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            text = "# Documentation\n\nThe README could not be loaded on the server."
        resp = make_response(text)
        resp.headers["Content-Type"] = "text/markdown; charset=utf-8"
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    # ---- dashboard ----------------------------------------------------------
    @app.route("/")
    def dashboard():
        store = _store()
        uid = _current_user(store)
        activities = store.get_activities(uid)
        profile = store.get_profile(uid) or Profile()
        goal = store.get_goal(uid)
        cfg = load_config()
        strava = store.get_strava(uid)

        ctx = {
            "has_data": bool(activities),
            "profile": profile,
            "goal": goal,
            "strava_configured": cfg.strava_configured,
            "strava_connected": bool(strava),
            "strava_name": strava["display_name"] if strava else None,
        }

        if activities:
            fitness = compute_fitness(activities, profile=profile)
            total_km = sum(a.distance_km for a in activities)
            ctx["fitness"] = fitness
            ctx["total_km"] = round(total_km, 1)
            ctx["total_elevation"] = int(total_elevation_gain(activities))
            ctx["run_count"] = len(activities)
            ctx["form_label"] = (
                "Fresh" if fitness.tsb > 5 else "Fatigued" if fitness.tsb < -10 else "Balanced"
            )

            vol = weekly_volume_series(activities, weeks=12)
            ctx["vol_labels"] = [d.strftime("%b %d") for d, _ in vol]
            ctx["vol_values"] = [km for _, km in vol]

            vdot = fitness.recent_vdot or fitness.best_vdot
            paces = training_paces(vdot) if vdot else {}
            ctx["paces"] = {k: format_pace(v) for k, v in paces.items()}

            zones = zone_distribution(activities, profile)
            ctx["zones"] = zones
            ctx["zone_labels"] = [f"{z.key} {z.name}" for z in zones]
            ctx["zone_minutes"] = [z.minutes for z in zones]
            ctx["zone_colors"] = ZONE_COLORS
            ctx["zone_total_min"] = round(sum(z.minutes for z in zones), 1)
            ctx["hr_bounds"] = hr_zone_bounds(profile)

            predictor = PacePredictor()
            trained = predictor.train(activities)
            preds = []
            for label, key in [("5K", "5k"), ("10K", "10k"), ("Half", "half"),
                               ("Marathon", "marathon")]:
                dist = parse_distance(key)
                p = predictor.predict(activities, dist)
                pace = p.predicted_time_s / (dist / 1000.0) if dist else 0
                preds.append({
                    "label": label,
                    "time": format_time(p.predicted_time_s),
                    "pace": format_pace(pace),
                    "method": f"{p.method}/{p.confidence}",
                })
            ctx["predictions"] = preds
            ctx["pred_trained"] = trained

            zbounds = hr_zone_bounds(profile)
            recent = []
            for a in reversed(activities[-10:]):
                zi = classify_hr(a.average_hr, profile) if a.average_hr else None
                recent.append({
                    "a": a,
                    "zone_key": zbounds[zi].key if zi is not None else None,
                    "zone_index": zi,
                })
            ctx["recent"] = recent

        weekly_km = ctx["fitness"].weekly_km if activities else 0.0
        ctx["strength"] = strength_recommendation(
            profile, weekly_km, goal.distance_m if goal else None
        )

        store.close()
        return render_template("dashboard.html", **ctx)

    # ---- add / import runs --------------------------------------------------
    @app.route("/runs", methods=["POST"])
    def add_run():
        store = _store()
        uid = _current_user(store)
        try:
            hr = request.form.get("hr", "").strip()
            elev = request.form.get("elevation", "").strip()
            activity = make_manual_activity(
                date_str=request.form.get("date") or date.today().isoformat(),
                distance_str=request.form["distance"],
                duration_str=request.form["time"],
                name=request.form.get("name") or "Manual run",
                average_hr=float(hr) if hr else None,
                elevation_m=float(elev) if elev else 0.0,
            )
            if store.add_activity(uid, activity):
                flash(f"Added {activity.distance_km:.2f} km run.", "success")
            else:
                flash("That run looks like a duplicate; skipped.", "warning")
        except (KeyError, ValueError) as e:
            flash(f"Could not add run: {e}", "error")
        store.close()
        return redirect(url_for("dashboard"))

    @app.route("/import", methods=["POST"])
    def import_runs():
        store = _store()
        uid = _current_user(store)
        file = request.files.get("csv")
        if not file or not file.filename:
            flash("No CSV file selected.", "error")
            store.close()
            return redirect(url_for("dashboard"))
        try:
            with tempfile.NamedTemporaryFile(
                "w", suffix=".csv", delete=False, newline="", encoding="utf-8"
            ) as tmp:
                tmp.write(file.stream.read().decode("utf-8"))
                tmp_path = tmp.name
            activities = import_csv(tmp_path)
            added = sum(1 for a in activities if store.add_activity(uid, a) is not None)
            flash(f"Imported {added}/{len(activities)} runs.", "success")
        except (ValueError, UnicodeDecodeError) as e:
            flash(f"Import failed: {e}", "error")
        store.close()
        return redirect(url_for("dashboard"))

    @app.route("/import/strava-export", methods=["POST"])
    def import_strava_export_route():
        """Import runs straight from a Strava bulk-export archive (no API needed)."""
        store = _store()
        uid = _current_user(store)
        file = request.files.get("archive")
        if not file or not file.filename:
            flash("Choose your Strava export .zip (or activities.csv) first.", "error")
            store.close()
            return redirect(url_for("dashboard"))

        suffix = ".zip" if file.filename.lower().endswith(".zip") else ".csv"
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        tmp_path = tmp.name
        tmp.close()
        try:
            file.save(tmp_path)  # streams to disk, so large archives stay off-heap
            activities = import_strava_export(tmp_path)
            if not activities:
                flash(
                    "No runs found in that export. Make sure it's the archive Strava "
                    "emailed you (containing activities.csv).", "warning",
                )
            else:
                added = sum(1 for a in activities if store.add_activity(uid, a) is not None)
                skipped = len(activities) - added
                msg = f"Imported {added} runs from your Strava export."
                if skipped:
                    msg += f" ({skipped} already in your log.)"
                flash(msg, "success")
        except (ValueError, zipfile.BadZipFile, UnicodeDecodeError) as e:
            flash(f"Could not read that export: {e}", "error")
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            store.close()
        return redirect(url_for("dashboard"))

    # ---- profile / goal -----------------------------------------------------
    @app.route("/settings", methods=["POST"])
    def settings():
        store = _store()
        uid = _current_user(store)
        try:
            existing = store.get_profile(uid) or Profile()
            resting = request.form.get("resting_hr", "").strip()
            age = request.form.get("age", "").strip()
            max_hr = request.form.get("max_hr", "").strip()
            if max_hr:
                max_hr_val = int(max_hr)
            elif age:
                max_hr_val = Profile.estimate_max_hr(int(age))
            else:
                max_hr_val = existing.max_hr

            # Body metrics: always stored metric; the form sends whichever
            # unit system the athlete picked. Blank fields keep prior values.
            units = (request.form.get("units", "").strip() or existing.units or "imperial")
            height_cm = existing.height_cm
            weight_kg = existing.weight_kg
            if units == "metric":
                h = request.form.get("height_cm", "").strip()
                w = request.form.get("weight_kg", "").strip()
                if h:
                    height_cm = float(h)
                if w:
                    weight_kg = float(w)
            else:
                ft = request.form.get("height_ft", "").strip()
                inch = request.form.get("height_in", "").strip()
                lb = request.form.get("weight_lb", "").strip()
                if ft or inch:
                    height_cm = ft_in_to_cm(float(ft or 0), float(inch or 0))
                if lb:
                    weight_kg = lb_to_kg(float(lb))

            profile = Profile(
                max_hr=max_hr_val,
                resting_hr=int(resting) if resting else None,
                sex=request.form.get("sex", "m"),
                height_cm=height_cm,
                weight_kg=weight_kg,
                units=units,
            )
            store.set_profile(uid, profile)
            flash("Profile saved. Zones, BMI, and strength guidance updated.", "success")
        except ValueError as e:
            flash(f"Invalid profile: {e}", "error")
        store.close()
        return redirect(url_for("dashboard"))

    @app.route("/goal", methods=["POST"])
    def set_goal():
        store = _store()
        uid = _current_user(store)
        try:
            target = request.form.get("target", "").strip()
            goal = Goal(
                race_name=request.form.get("name") or "My race",
                race_date=date.fromisoformat(request.form["date"]),
                distance_m=parse_distance(request.form["distance"]),
                target_time_s=parse_duration(target) if target else None,
            )
            store.set_goal(uid, goal)
            flash(f"Goal set: {goal.race_name}.", "success")
        except (KeyError, ValueError) as e:
            flash(f"Could not set goal: {e}", "error")
        store.close()
        return redirect(url_for("dashboard"))

    # ---- plan ---------------------------------------------------------------
    @app.route("/plan")
    def plan():
        store = _store()
        uid = _current_user(store)
        activities = store.get_activities(uid)
        profile = store.get_profile(uid) or Profile()
        goal = store.get_goal(uid)
        if goal is None:
            store.close()
            flash("Set a goal race first to generate a plan.", "warning")
            return redirect(url_for("dashboard"))

        fitness = compute_fitness(activities, profile=profile) if activities else compute_fitness([])
        plan_ctx = PlanContext(fitness=fitness, goal=goal, start_volume_km=fitness.weekly_km)
        plans = generate_plan(plan_ctx)
        store.close()
        return render_template(
            "plan.html",
            goal=goal,
            plans=plans,
            fitness=fitness,
            start_volume=plan_ctx.start_volume_km or 20,
            race_note=race_week_note(goal),
            day_names=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        )

    # ---- splits calculator --------------------------------------------------
    @app.route("/splits")
    def splits():
        distance_raw = request.args.get("distance", "").strip()
        time_raw = request.args.get("time", "").strip()
        unit = request.args.get("unit", "mi")
        result = None
        error = None
        if distance_raw and time_raw:
            try:
                dist_m = parse_distance(distance_raw)
                total_s = parse_duration(time_raw)
                rows = compute_splits(dist_m, total_s, unit=unit)
                result = {
                    "distance_raw": distance_raw,
                    "time_raw": time_raw,
                    "unit": unit,
                    "unit_label": "mile" if unit == "mi" else "km",
                    "distance_km": round(dist_m / 1000.0, 2),
                    "distance_mi": round(dist_m / 1609.34, 2),
                    "total_time": format_time(total_s),
                    "avg_pace_km": format_pace(total_s / (dist_m / 1000.0)),
                    "avg_pace_mi": format_pace(total_s / (dist_m / 1609.34)),
                    "splits": [
                        {
                            "label": s.label,
                            "split": format_time(s.split_s),
                            "cumulative": format_time(s.cumulative_s),
                            "pace": format_pace(s.split_s / (s.segment_m / 1000.0)),
                            "partial": s.partial,
                        }
                        for s in rows
                    ],
                }
            except (ValueError, ZeroDivisionError) as e:
                error = str(e)
        return render_template(
            "splits.html", result=result, error=error,
            distance_raw=distance_raw, time_raw=time_raw, unit=unit,
        )

    # ---- activity detail ----------------------------------------------------
    @app.route("/activity/<int:activity_id>")
    def activity(activity_id: int):
        store = _store()
        uid = _current_user(store)
        act = store.get_activity(uid, activity_id)
        profile = store.get_profile(uid) or Profile()
        store.close()
        if act is None:
            flash("Run not found.", "error")
            return redirect(url_for("dashboard"))

        mile_splits = compute_splits(act.distance_m, act.moving_time_s, unit="mi")
        km_splits = compute_splits(act.distance_m, act.moving_time_s, unit="km")
        zones = activity_zone_breakdown(act, profile) if act.average_hr else []
        zone_total = sum(z.minutes for z in zones)
        current_zone = (
            hr_zone_bounds(profile)[classify_hr(act.average_hr, profile)]
            if act.average_hr else None
        )

        def fmt_splits(rows):
            return [
                {
                    "label": s.label,
                    "split": format_time(s.split_s),
                    "cumulative": format_time(s.cumulative_s),
                    "pace": format_pace(s.split_s / (s.segment_m / 1000.0)),
                    "partial": s.partial,
                }
                for s in rows
            ]

        return render_template(
            "activity.html", act=act,
            pace=format_pace(act.pace_s_per_km),
            duration=format_time(act.moving_time_s),
            mile_splits=fmt_splits(mile_splits), km_splits=fmt_splits(km_splits),
            zones=zones, zone_total=round(zone_total, 1),
            zone_colors=ZONE_COLORS, current_zone=current_zone,
        )

    # ---- auth: signup / login / logout --------------------------------------
    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if session.get("uid"):
            return redirect(url_for("dashboard"))
        if request.method == "GET":
            return render_template("signup.html")

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if "@" not in email or "." not in email:
            flash("Please enter a valid email address.", "error")
            return redirect(url_for("signup"))
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return redirect(url_for("signup"))

        store = _store()
        try:
            if store.email_exists(email):
                flash("That email is already registered - try logging in.", "warning")
                return redirect(url_for("login"))
            uid = store.create_account(email, generate_password_hash(password), name)
        finally:
            store.close()

        session.clear()
        session["uid"] = uid
        session.permanent = True
        flash(f"Welcome to Paceloop, {name or 'runner'}! Your account is ready.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if session.get("uid"):
            return redirect(url_for("dashboard"))
        if request.method == "GET":
            return render_template("login.html")

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        store = _store()
        row = store.get_account_by_email(email)
        store.close()
        if not row or not row["password_hash"] or not check_password_hash(row["password_hash"], password):
            flash("Wrong email or password. Please try again.", "error")
            return redirect(url_for("login"))

        session.clear()
        session["uid"] = row["id"]
        session.permanent = True
        name = row["account_name"] or email.split("@")[0]
        flash(f"Welcome back, {name}!", "success")
        return redirect(url_for("dashboard"))

    @app.route("/logout")
    def logout():
        session.clear()
        flash("You've been logged out.", "success")
        return redirect(url_for("welcome"))

    # ---- password reset (via email link) ------------------------------------
    def _reset_link(token: str) -> str:
        """Absolute URL for the reset page (honors APP_BASE_URL if set)."""
        base = load_config().app_base_url
        if base:
            return base.rstrip("/") + url_for("reset_password", token=token)
        return url_for("reset_password", token=token, _external=True)

    @app.route("/forgot", methods=["GET", "POST"])
    def forgot_password():
        if session.get("uid"):
            return redirect(url_for("dashboard"))
        if request.method == "GET":
            return render_template("forgot.html")

        email = request.form.get("email", "").strip().lower()
        cfg = load_config()
        store = _store()
        row = store.get_account_by_email(email) if email else None
        dev_link = None
        if row:
            token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            expires = datetime.now(timezone.utc) + timedelta(hours=1)
            store.create_password_reset(row["id"], token_hash, expires)
            link = _reset_link(token)
            app.logger.info("Password reset link for %s: %s", email, link)
            if cfg.email_configured:
                try:
                    send_email(
                        cfg, email, "Reset your Paceloop password",
                        _reset_email_text(link), _reset_email_html(link),
                    )
                except MailerError as e:
                    # Delivery failed - don't strand the user; show the link instead.
                    app.logger.warning("Reset email to %s failed: %s", email, e)
                    dev_link = link
            else:
                # No SMTP configured (e.g. local single-owner install): show the link.
                dev_link = link
        store.close()
        # Always show the same confirmation regardless of whether the email exists,
        # so we don't leak which addresses have accounts.
        return render_template(
            "forgot_sent.html", email=email, dev_link=dev_link,
            email_configured=cfg.email_configured,
        )

    @app.route("/reset/<token>", methods=["GET", "POST"])
    def reset_password(token):
        store = _store()
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        reset = store.get_valid_reset(token_hash)
        if not reset:
            store.close()
            flash("That reset link is invalid or has expired. Request a new one.", "error")
            return redirect(url_for("forgot_password"))

        if request.method == "GET":
            store.close()
            return render_template("reset.html", token=token)

        new = request.form.get("new_password") or ""
        confirm = request.form.get("confirm_password") or ""
        if len(new) < 6:
            store.close()
            flash("Password must be at least 6 characters.", "error")
            return redirect(url_for("reset_password", token=token))
        if new != confirm:
            store.close()
            flash("Passwords don't match.", "error")
            return redirect(url_for("reset_password", token=token))

        uid = reset["user_id"]
        store.set_password(uid, generate_password_hash(new))
        store.consume_reset(reset["id"])
        store.close()

        # Log them straight in after a successful reset, for a friendly experience.
        session.clear()
        session["uid"] = uid
        session.permanent = True
        flash("Your password has been reset - you're now logged in.", "success")
        return redirect(url_for("dashboard"))

    # ---- account settings ---------------------------------------------------
    @app.route("/account")
    def account_settings():
        store = _store()
        uid = _current_user(store)
        row = store.get_user(uid)
        store.close()
        return render_template("account.html", user=row)

    @app.route("/account/update", methods=["POST"])
    def account_update():
        store = _store()
        uid = _current_user(store)
        name = (request.form.get("name") or "").strip()[:80]
        city = (request.form.get("city") or "").strip()[:80]
        state = (request.form.get("state") or "").strip()[:40]
        if not name:
            row = store.get_user(uid)
            name = (row["account_name"] if row else None) or "Runner"
        store.update_account(uid, name, city, state)
        store.close()
        flash("Account details saved.", "success")
        return redirect(url_for("account_settings"))

    @app.route("/account/password", methods=["POST"])
    def account_password():
        store = _store()
        uid = _current_user(store)
        current = request.form.get("current_password") or ""
        new = request.form.get("new_password") or ""
        confirm = request.form.get("confirm_password") or ""
        row = store.get_user(uid)
        if not row or not check_password_hash(row["password_hash"] or "", current):
            flash("Your current password is incorrect.", "error")
        elif len(new) < 6:
            flash("New password must be at least 6 characters.", "error")
        elif new != confirm:
            flash("New passwords don't match.", "error")
        else:
            store.set_password(uid, generate_password_hash(new))
            flash("Password updated.", "success")
        store.close()
        return redirect(url_for("account_settings"))

    # ---- admin analytics dashboard ------------------------------------------
    @app.route("/admin")
    def admin():
        store = _store()
        uid = _current_user(store)
        row = store.get_user(uid)
        first_uid = store.first_user_id()
        if not row or not _is_admin_email(row["email"], uid, first_uid):
            store.close()
            flash("That area is for administrators only.", "error")
            return redirect(url_for("dashboard"))

        stats = store.admin_stats()
        series = store.signup_series(30)
        sources = store.source_breakdown()
        themes_dist = store.theme_breakdown()
        locations = store.top_locations(8)
        recent = store.recent_signups(25)
        store.close()

        incidents = read_incidents(25)

        return render_template(
            "admin.html",
            stats=stats,
            signup_labels=[d[5:] for d, _ in series],   # MM-DD
            signup_values=[c for _, c in series],
            sources=sources,
            source_labels=[s[0] for s in sources],
            source_values=[s[1] for s in sources],
            themes_dist=themes_dist,
            locations=locations,
            recent=recent,
            incidents=incidents,
        )

    @app.route("/admin/stats.json")
    def admin_stats_json():
        """Private, admin-only live feed powering the auto-updating dashboard."""
        store = _store()
        uid = _current_user(store)
        row = store.get_user(uid)
        first_uid = store.first_user_id()
        if not row or not _is_admin_email(row["email"], uid, first_uid):
            store.close()
            return jsonify({"error": "forbidden"}), 403

        stats = store.admin_stats()
        series = store.signup_series(30)
        sources = store.source_breakdown()
        store.close()
        incidents = read_incidents(0)
        return jsonify({
            "stats": stats,
            "signup_labels": [d[5:] for d, _ in series],
            "signup_values": [c for _, c in series],
            "source_labels": [s[0] for s in sources],
            "source_values": [s[1] for s in sources],
            "incidents": {
                "total": incidents["total"],
                "recovered": incidents["recovered"],
                "failed": incidents["failed"],
            },
            "updated_at": datetime.now().strftime("%H:%M:%S"),
        })

    # ---- appearance / color theme -------------------------------------------
    @app.route("/appearance", methods=["POST"])
    def appearance():
        store = _store()
        uid = _current_user(store)
        theme = request.form.get("theme", DEFAULT_THEME)
        if theme == "custom":
            accent = request.form.get("accent") or None
            accent2 = request.form.get("accent2") or None
            store.set_theme(uid, "custom", accent, accent2)
            flash("Saved your custom color theme.", "success")
        elif theme in THEMES:
            store.set_theme(uid, theme, None, None)
            flash(f"Theme set to {THEMES[theme]['name']}.", "success")
        else:
            flash("Unknown theme.", "error")
        store.close()
        return redirect(url_for("dashboard") + "#appearance")

    # ---- coach chatbot ------------------------------------------------------
    @app.route("/chat")
    def chat():
        store = _store()
        uid = _current_user(store)
        bot_name = store.get_bot_name(uid)
        messages = store.get_chat_messages(uid)
        has_data = store.count_activities(uid) > 0
        store.close()
        return render_template(
            "chat.html",
            bot_name=bot_name,
            messages=messages,
            suggestions=SUGGESTIONS,
            has_data=has_data,
        )

    @app.route("/chat/send", methods=["POST"])
    def chat_send():
        if request.is_json:
            message = ((request.get_json(silent=True) or {}).get("message") or "").strip()
        else:
            message = (request.form.get("message") or "").strip()
        store = _store()
        uid = _current_user(store)
        bot_name = store.get_bot_name(uid)
        if not message:
            store.close()
            return jsonify({"error": "empty"}), 400

        activities = store.get_activities(uid)
        profile = store.get_profile(uid) or Profile()
        goal = store.get_goal(uid)
        reply = build_reply(message, activities, profile, goal, bot_name)

        store.add_chat_message(uid, "user", message)
        store.add_chat_message(uid, "bot", reply)
        store.close()
        return jsonify({"reply": reply, "bot_name": bot_name})

    @app.route("/chat/rename", methods=["POST"])
    def chat_rename():
        name = (request.form.get("bot_name") or "").strip()[:40]
        store = _store()
        uid = _current_user(store)
        if name:
            store.set_bot_name(uid, name)
            flash(f"Your coach is now called {name}.", "success")
        else:
            flash("Please enter a name for your coach.", "error")
        store.close()
        return redirect(url_for("chat"))

    @app.route("/chat/clear", methods=["POST"])
    def chat_clear():
        store = _store()
        uid = _current_user(store)
        store.clear_chat(uid)
        store.close()
        flash("Chat history cleared.", "success")
        return redirect(url_for("chat"))

    # ---- meet results (import races by name) --------------------------------
    @app.route("/meets")
    def meets():
        """Search public results sites for an athlete by name."""
        q = (request.args.get("q") or "").strip()
        store = _store()
        uid = _current_user(store)
        row = store.get_user(uid)
        store.close()
        home_city = (row["city"] if row else "") or ""
        home_state = (row["state"] if row else "") or ""
        matches, error, searched = [], None, bool(q)
        if q:
            try:
                matches = search_athletes(q, city=home_city, state=home_state)
            except MeetImportError as e:
                error = str(e)
        return render_template(
            "meets.html", q=q, matches=matches, error=error, searched=searched,
            home_city=home_city, home_state=home_state,
            providers=[p.label for p in PROVIDERS.values()],
        )

    @app.route("/meets/import", methods=["POST"])
    def meets_import():
        """Pull every distance race off the chosen profile into the user's log."""
        store = _store()
        uid = _current_user(store)
        ref = (request.form.get("ref") or "").strip()
        athlete_name = (request.form.get("athlete_name") or "").strip()
        try:
            activities = import_results(ref)
            if not activities:
                flash(
                    "No distance races (800 m+ or cross country) were found on "
                    "that profile.", "warning",
                )
            else:
                added = sum(1 for a in activities if store.add_activity(uid, a) is not None)
                skipped = len(activities) - added
                who = f" for {athlete_name}" if athlete_name else ""
                msg = f"Imported {added} race{'s' if added != 1 else ''}{who}."
                if skipped:
                    msg += f" ({skipped} already in your log.)"
                flash(msg, "success" if added else "warning")
        except MeetImportError as e:
            flash(str(e), "error")
        store.close()
        return redirect(url_for("dashboard"))

    # ---- strava (per user) --------------------------------------------------
    @app.route("/strava/connect")
    def strava_connect():
        store = _store()
        uid = _current_user(store)
        client = _strava_client_for(store, uid)
        store.close()
        try:
            redirect_uri = url_for("strava_callback", _external=True)
            return redirect(client.build_authorize_url(redirect_uri))
        except StravaError as e:
            flash(str(e), "error")
            return redirect(url_for("dashboard"))

    @app.route("/strava/callback")
    def strava_callback():
        code = request.args.get("code")
        if not code:
            flash("Strava authorization was cancelled.", "warning")
            return redirect(url_for("dashboard"))
        store = _store()
        uid = _current_user(store)
        client = _strava_client_for(store, uid)
        try:
            result = client.exchange_code(code)
            store.set_strava(
                uid, result.athlete_id, result.display_name,
                result.tokens.access_token, result.tokens.refresh_token,
                result.tokens.expires_at,
            )
            flash(
                f"Connected to Strava{' as ' + result.display_name if result.display_name else ''}. "
                "Syncing your runs...", "success",
            )
            # Immediately pull in their runs so the dashboard isn't empty.
            activities = client.fetch_activities()
            added = sum(1 for a in activities if store.add_activity(uid, a) is not None)
            flash(f"Imported {added} runs from Strava.", "success")
        except StravaError as e:
            flash(str(e), "error")
        store.close()
        return redirect(url_for("dashboard"))

    @app.route("/strava/sync", methods=["POST"])
    def strava_sync():
        store = _store()
        uid = _current_user(store)
        client = _strava_client_for(store, uid)
        try:
            latest = store.latest_activity_date(uid)
            after = (latest - timedelta(days=1)) if latest else None
            activities = client.fetch_activities(after=after)
            added = sum(1 for a in activities if store.add_activity(uid, a) is not None)
            flash(f"Synced {len(activities)} runs from Strava, {added} new.", "success")
        except StravaError as e:
            flash(str(e), "error")
        store.close()
        return redirect(url_for("dashboard"))

    @app.route("/strava/disconnect", methods=["POST"])
    def strava_disconnect():
        store = _store()
        uid = _current_user(store)
        store.clear_strava(uid)
        store.close()
        flash("Disconnected from Strava. Your synced runs are kept.", "success")
        return redirect(url_for("dashboard"))

    # Detect crashes, auto-recover the fixable ones, and fail gracefully otherwise.
    install_crash_handler(app)

    return app
