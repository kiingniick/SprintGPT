"""Command-line interface for SprintGPT."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .analysis import (
    compute_fitness,
    format_pace,
    format_time,
    training_paces,
    weekly_volume_series,
)
from .config import load_config
from .importer import (
    import_csv,
    import_strava_export,
    make_manual_activity,
    parse_distance,
    parse_duration,
)
from .models import RACE_DISTANCES, Goal, Profile
from .planner import PlanContext, generate_plan, race_week_note
from .predictor import PacePredictor
from .storage import DEMO_TOKEN, Storage

console = Console()


def _storage() -> Storage:
    return Storage(load_config().db_path)


def _uid(store: Storage) -> int:
    """The CLI operates on a single shared local user (also the web 'demo')."""
    return store.get_or_create_user(DEMO_TOKEN)


# ---- commands ---------------------------------------------------------------
def cmd_strava_auth(args: argparse.Namespace) -> None:
    from .strava import StravaClient, StravaError

    cfg = load_config()
    store = _storage()
    uid = _uid(store)
    try:
        client = StravaClient(cfg.strava_client_id, cfg.strava_client_secret)
        result = client.authorize_cli()
        store.set_strava(uid, result.athlete_id, result.display_name,
                         result.tokens.access_token, result.tokens.refresh_token,
                         result.tokens.expires_at)
        console.print("[green]Authorized. Strava tokens saved.[/green]")
    except StravaError as e:
        console.print(f"[red]{e}[/red]")
    store.close()


def cmd_sync(args: argparse.Namespace) -> None:
    from .strava import StravaClient, StravaError, StravaTokens

    cfg = load_config()
    store = _storage()
    uid = _uid(store)
    stored = store.get_strava(uid)
    if not stored:
        console.print("[red]Not connected to Strava. Run: python main.py cli strava-auth[/red]")
        store.close()
        return
    tokens = StravaTokens(stored["access_token"], stored["refresh_token"], stored["expires_at"])

    def on_refresh(new: StravaTokens) -> None:
        store.set_strava(uid, None, None, new.access_token, new.refresh_token, new.expires_at)

    client = StravaClient(cfg.strava_client_id, cfg.strava_client_secret,
                          tokens=tokens, on_refresh=on_refresh)
    after = None
    if not args.full:
        latest = store.latest_activity_date(uid)
        if latest:
            after = latest - timedelta(days=1)
    try:
        with console.status("Fetching activities from Strava..."):
            activities = client.fetch_activities(after=after)
    except StravaError as e:
        console.print(f"[red]{e}[/red]")
        store.close()
        return

    added = sum(1 for a in activities if store.add_activity(uid, a) is not None)
    console.print(
        f"[green]Synced {len(activities)} runs from Strava, {added} new.[/green]"
    )
    store.close()


def cmd_add(args: argparse.Namespace) -> None:
    store = _storage()
    uid = _uid(store)
    when = args.date or date.today().isoformat()
    activity = make_manual_activity(
        date_str=when,
        distance_str=args.distance,
        duration_str=args.time,
        name=args.name or "Manual run",
        average_hr=float(args.hr) if args.hr else None,
        elevation_m=float(args.elevation) if args.elevation else 0.0,
    )
    rid = store.add_activity(uid, activity)
    if rid:
        console.print(
            f"[green]Added:[/green] {activity.distance_km:.2f} km in "
            f"{format_time(activity.moving_time_s)} "
            f"({format_pace(activity.pace_s_per_km)}) on {when}"
        )
    else:
        console.print("[yellow]That run looks like a duplicate; skipped.[/yellow]")
    store.close()


def cmd_splits(args: argparse.Namespace) -> None:
    from .analysis import compute_splits

    dist_m = parse_distance(args.distance)
    total_s = parse_duration(args.time)
    rows = compute_splits(dist_m, total_s, unit=args.unit)
    if not rows:
        console.print("[red]Could not compute splits from those inputs.[/red]")
        return

    unit_label = "Mile" if args.unit == "mi" else "Km"
    avg_pace = format_pace(total_s / (dist_m / 1000.0))
    console.print(
        f"[green]{args.distance}[/green] in [bold]{format_time(total_s)}[/bold] "
        f"= {avg_pace} average, even effort:"
    )
    tbl = Table(title=f"Per-{unit_label} Splits", show_edge=False)
    tbl.add_column(unit_label, style="cyan")
    tbl.add_column("Split", justify="right")
    tbl.add_column("Pace", justify="right")
    tbl.add_column("Cumulative", justify="right")
    for s in rows:
        label = s.label + (" (partial)" if s.partial else "")
        pace = format_pace(s.split_s / (s.segment_m / 1000.0))
        tbl.add_row(label, format_time(s.split_s), pace, format_time(s.cumulative_s))
    console.print(tbl)


def cmd_profile(args: argparse.Namespace) -> None:
    store = _storage()
    uid = _uid(store)
    current = store.get_profile(uid) or Profile()
    if args.max_hr:
        max_hr = args.max_hr
    elif args.age:
        max_hr = Profile.estimate_max_hr(args.age)
    else:
        max_hr = current.max_hr
    profile = Profile(
        max_hr=max_hr,
        resting_hr=args.resting_hr if args.resting_hr is not None else current.resting_hr,
        sex=args.sex,
    )
    store.set_profile(uid, profile)
    from .analysis import hr_zone_bounds

    tbl = Table(title=f"HR Zones (max {profile.max_hr}"
                f"{', resting ' + str(profile.resting_hr) if profile.resting_hr else ''})",
                show_edge=False)
    tbl.add_column("Zone", style="cyan")
    tbl.add_column("Range (bpm)", justify="right")
    for z in hr_zone_bounds(profile):
        tbl.add_row(f"{z.key} {z.name}", f"{z.low_bpm}-{z.high_bpm}")
    console.print(tbl)
    store.close()


def cmd_import_csv(args: argparse.Namespace) -> None:
    store = _storage()
    uid = _uid(store)
    activities = import_csv(args.path)
    added = sum(1 for a in activities if store.add_activity(uid, a) is not None)
    console.print(f"[green]Imported {added}/{len(activities)} runs from {args.path}.[/green]")
    store.close()


def cmd_import_strava(args: argparse.Namespace) -> None:
    store = _storage()
    uid = _uid(store)
    try:
        activities = import_strava_export(args.path)
    except (ValueError, OSError) as e:
        console.print(f"[red]Could not read that export: {e}[/red]")
        store.close()
        return
    added = sum(1 for a in activities if store.add_activity(uid, a) is not None)
    skipped = len(activities) - added
    console.print(
        f"[green]Imported {added} runs from your Strava export "
        f"({len(activities)} found, {skipped} already in your log).[/green]"
    )
    store.close()


def cmd_import_meets(args: argparse.Namespace) -> None:
    """Search results databases by name and import an athlete's races."""
    from .meets import MeetImportError, import_results, search_athletes

    try:
        matches = search_athletes(args.name)
    except MeetImportError as e:
        console.print(f"[red]{e}[/red]")
        return
    if not matches:
        console.print(f"[yellow]No athletes matched '{args.name}'.[/yellow]")
        return

    if args.pick is None:
        table = Table(title=f"Matches for '{args.name}'")
        table.add_column("#", justify="right")
        table.add_column("Name")
        table.add_column("Details")
        table.add_column("Source")
        for i, m in enumerate(matches, 1):
            table.add_row(str(i), m.name, m.detail or "-", m.source)
        console.print(table)
        console.print("Re-run with [cyan]--pick N[/cyan] to import that athlete's races.")
        return

    if not 1 <= args.pick <= len(matches):
        console.print(f"[red]--pick must be between 1 and {len(matches)}.[/red]")
        return

    chosen = matches[args.pick - 1]
    try:
        activities = import_results(chosen.ref)
    except MeetImportError as e:
        console.print(f"[red]{e}[/red]")
        return

    store = _storage()
    uid = _uid(store)
    added = sum(1 for a in activities if store.add_activity(uid, a) is not None)
    skipped = len(activities) - added
    console.print(
        f"[green]Imported {added} races for {chosen.name} "
        f"({len(activities)} found, {skipped} already in your log).[/green]"
    )
    store.close()


def cmd_status(args: argparse.Namespace) -> None:
    store = _storage()
    uid = _uid(store)
    activities = store.get_activities(uid)
    if not activities:
        console.print("[yellow]No runs yet. Add some with `add`, `import-csv`, or `sync`.[/yellow]")
        store.close()
        return

    profile = store.get_profile(uid)
    fitness = compute_fitness(activities, profile=profile)
    total_km = sum(a.distance_km for a in activities)

    form_label = (
        "fresh" if fitness.tsb > 5 else "fatigued" if fitness.tsb < -10 else "balanced"
    )
    summary = Table.grid(padding=(0, 2))
    summary.add_column(justify="right", style="cyan")
    summary.add_column()
    summary.add_row("Total runs", str(len(activities)))
    summary.add_row("Total distance", f"{total_km:.1f} km")
    summary.add_row("Last 7 days", f"{fitness.weekly_km:.1f} km")
    summary.add_row("Fitness (CTL)", f"{fitness.ctl}")
    summary.add_row("Fatigue (ATL)", f"{fitness.atl}")
    summary.add_row("Form (TSB)", f"{fitness.tsb}  [{form_label}]")
    summary.add_row("VDOT (recent)", f"{fitness.recent_vdot}")
    summary.add_row("VDOT (best)", f"{fitness.best_vdot}")
    console.print(Panel(summary, title="SprintGPT - Fitness Status", border_style="green"))

    # Weekly volume trend.
    series = weekly_volume_series(activities, weeks=8)
    if series:
        peak = max((km for _, km in series), default=1.0) or 1.0
        trend = Table(title="Weekly Volume (last 8 weeks)", show_edge=False)
        trend.add_column("Week of")
        trend.add_column("km", justify="right")
        trend.add_column("")
        for wk_start, km in series:
            bar = "#" * int(round(km / peak * 24))
            trend.add_row(wk_start.isoformat(), f"{km:.1f}", f"[green]{bar}[/green]")
        console.print(trend)

    # Training paces.
    vdot = fitness.recent_vdot or fitness.best_vdot
    if vdot:
        paces = training_paces(vdot)
        pace_tbl = Table(title=f"Your Training Paces (VDOT {vdot})", show_edge=False)
        pace_tbl.add_column("Zone", style="cyan")
        pace_tbl.add_column("Pace", justify="right")
        for zone in ("easy", "marathon", "threshold", "interval", "repetition"):
            pace_tbl.add_row(zone.capitalize(), format_pace(paces[zone]))
        console.print(pace_tbl)

    # Heart-rate zone distribution (if HR data + profile available).
    if profile:
        from .analysis import zone_distribution

        zones = zone_distribution(activities, profile)
        total_min = sum(z.minutes for z in zones)
        if total_min > 0:
            hr_tbl = Table(title="Heart-Rate Zone Distribution", show_edge=False)
            hr_tbl.add_column("Zone", style="cyan")
            hr_tbl.add_column("Range", justify="right")
            hr_tbl.add_column("Minutes", justify="right")
            hr_tbl.add_column("Share", justify="right")
            for z in zones:
                pct = z.minutes / total_min * 100 if total_min else 0
                bar = "#" * int(round(pct / 5))
                hr_tbl.add_row(f"{z.key} {z.name}", f"{z.low_bpm}-{z.high_bpm}",
                               f"{z.minutes:.0f}", f"[green]{bar}[/green] {pct:.0f}%")
            console.print(hr_tbl)
    store.close()


def cmd_predict(args: argparse.Namespace) -> None:
    store = _storage()
    uid = _uid(store)
    activities = store.get_activities(uid)
    if not activities:
        console.print("[yellow]No data to predict from yet.[/yellow]")
        store.close()
        return

    predictor = PacePredictor()
    trained = predictor.train(activities)

    if args.distance:
        distances = {args.distance: parse_distance(args.distance)}
    else:
        distances = {k: RACE_DISTANCES[k] for k in ("5k", "10k", "half", "marathon")}

    tbl = Table(title="Race Predictions", show_edge=False)
    tbl.add_column("Distance", style="cyan")
    tbl.add_column("Predicted time", justify="right")
    tbl.add_column("Pace", justify="right")
    tbl.add_column("Method", justify="right", style="dim")
    for label, dist_m in distances.items():
        p = predictor.predict(activities, dist_m)
        pace = p.predicted_time_s / (dist_m / 1000.0) if dist_m else 0
        tbl.add_row(label, format_time(p.predicted_time_s), format_pace(pace),
                    f"{p.method}/{p.confidence}")
    console.print(tbl)
    if trained:
        console.print("[dim]Model trained on your own runs.[/dim]")
    else:
        console.print("[dim]Using physiology model (need ~12+ runs to train the ML model).[/dim]")
    store.close()


def cmd_goal(args: argparse.Namespace) -> None:
    store = _storage()
    uid = _uid(store)
    dist_m = parse_distance(args.distance)
    target_s = None
    if args.target:
        target_s = parse_duration(args.target)
    goal = Goal(
        race_name=args.name or f"{args.distance} race",
        race_date=date.fromisoformat(args.date),
        distance_m=dist_m,
        target_time_s=target_s,
    )
    store.set_goal(uid, goal)
    console.print(
        f"[green]Goal set:[/green] {goal.race_name} - {dist_m/1000:.1f} km on "
        f"{goal.race_date:%b %d, %Y}"
        + (f", target {format_time(target_s)}" if target_s else "")
    )
    store.close()


def cmd_plan(args: argparse.Namespace) -> None:
    store = _storage()
    uid = _uid(store)
    activities = store.get_activities(uid)
    goal = store.get_goal(uid)

    if goal is None:
        if not (args.distance and args.date):
            console.print(
                "[yellow]No goal set. Either run `goal` first, or pass "
                "--distance and --date.[/yellow]"
            )
            store.close()
            return
        goal = Goal(
            race_name=args.name or f"{args.distance} race",
            race_date=date.fromisoformat(args.date),
            distance_m=parse_distance(args.distance),
        )

    profile = store.get_profile(uid)
    fitness = compute_fitness(activities, profile=profile) if activities else compute_fitness([])
    if not activities:
        console.print("[yellow]No run data yet; building a beginner-safe plan. "
                      "Add data for a personalized one.[/yellow]")

    ctx = PlanContext(fitness=fitness, goal=goal, start_volume_km=fitness.weekly_km)
    plans = generate_plan(ctx)

    console.print(Panel(
        f"[bold]{goal.race_name}[/bold] - {goal.distance_m/1000:.1f} km on "
        f"{goal.race_date:%A, %b %d, %Y}\n"
        f"{len(plans)} week plan  |  starting volume ~{ctx.start_volume_km or 20:.0f} km/wk  |  "
        f"VDOT {fitness.recent_vdot or fitness.best_vdot or 'n/a'}",
        title="SprintGPT Training Plan", border_style="green",
    ))

    show_weeks = plans if args.all else plans[: args.weeks]
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for plan in show_weeks:
        tbl = Table(
            title=f"Week {plan.week_index + 1} - {plan.phase.upper()} "
            f"({plan.start_day:%b %d})  ~{plan.total_distance_m/1000:.0f} km",
            show_edge=False, title_justify="left",
        )
        tbl.add_column("Day", style="cyan", width=4)
        tbl.add_column("Type", width=11)
        tbl.add_column("km", justify="right", width=5)
        tbl.add_column("Session")
        for w in plan.workouts:
            km = f"{w.distance_m/1000:.1f}" if w.distance_m else "-"
            color = {
                "long": "yellow", "tempo": "magenta", "interval": "red",
                "repetition": "red", "easy": "green", "recovery": "green",
                "rest": "dim", "race": "bold blue",
            }.get(w.kind, "white")
            tbl.add_row(day_names[w.day.weekday()], f"[{color}]{w.kind}[/{color}]",
                        km, w.description)
        console.print(tbl)

    if not args.all and len(plans) > args.weeks:
        console.print(f"[dim]...{len(plans) - args.weeks} more weeks. "
                      f"Use `plan --all` to see the whole block.[/dim]")
    console.print(f"[bold]{race_week_note(goal)}[/bold]")
    store.close()


def cmd_seed(args: argparse.Namespace) -> None:
    """Populate the DB with realistic sample runs for a quick demo."""
    import random

    store = _storage()
    uid = _uid(store)
    random.seed(7)
    # Give the demo a sensible profile so HR zones work out of the box.
    store.set_profile(uid, Profile(max_hr=190, resting_hr=50, sex="m"))
    today = date.today()
    added = 0
    # 14 weeks of ~4 runs/week building fitness.
    for wk in range(14, 0, -1):
        base_speed = 2.75 + (14 - wk) * 0.015  # gradual improvement
        for _ in range(4):
            d = today - timedelta(days=wk * 7 + random.randint(0, 6))
            roll = random.random()
            if roll < 0.55:
                dist = random.uniform(6, 11) * 1000
                speed = base_speed
                hr = random.randint(140, 152)  # aerobic
            elif roll < 0.75:
                dist = random.uniform(14, 22) * 1000  # long run
                speed = base_speed - 0.15
                hr = random.randint(148, 158)
            else:
                dist = random.uniform(4, 6) * 1000  # workout
                speed = base_speed + 0.45
                hr = random.randint(168, 182)  # threshold/VO2max
            speed *= random.uniform(0.98, 1.02)
            time_s = int(dist / speed)
            act = make_manual_activity(
                date_str=datetime(d.year, d.month, d.day, 7).isoformat(),
                distance_str=f"{dist/1000:.2f}km",
                duration_str=f"{time_s}s",
                name="Sample run",
                average_hr=hr,
            )
            if store.add_activity(uid, act):
                added += 1
    console.print(f"[green]Seeded {added} sample runs.[/green] "
                  f"View in the web app at /demo, or try `status`, `predict`, `plan`.")
    store.close()


# ---- parser -----------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sprintgpt",
        description="SprintGPT - your AI running coach.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("strava-auth", help="Authorize access to your Strava account").set_defaults(
        func=cmd_strava_auth
    )

    sp = sub.add_parser("sync", help="Sync runs from Strava")
    sp.add_argument("--full", action="store_true", help="Re-sync full history")
    sp.set_defaults(func=cmd_sync)

    sp = sub.add_parser("add", help="Add one run manually")
    sp.add_argument("distance", help="e.g. 10k, 5000m, 8.5km, 3.1mi")
    sp.add_argument("time", help="e.g. 45:30 or 1:32:10 or 2700s")
    sp.add_argument("--date", help="ISO date/time (default: today)")
    sp.add_argument("--name", help="Label for the run")
    sp.add_argument("--hr", help="Average heart rate in bpm")
    sp.add_argument("--elevation", help="Elevation gain in meters")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("splits", help="Get exact even splits from one total time")
    sp.add_argument("distance", help="e.g. marathon, 10k, 13.1mi")
    sp.add_argument("time", help="Total time, e.g. 3:30:00 or 45:30")
    sp.add_argument("--unit", choices=["mi", "km"], default="mi", help="Split unit")
    sp.set_defaults(func=cmd_splits)

    sp = sub.add_parser("profile", help="Set your heart-rate profile")
    sp.add_argument("--max-hr", type=int, help="Max heart rate (bpm)")
    sp.add_argument("--resting-hr", type=int, help="Resting heart rate (bpm)")
    sp.add_argument("--age", type=int, help="Estimate max HR from age if --max-hr omitted")
    sp.add_argument("--sex", choices=["m", "f"], default="m")
    sp.set_defaults(func=cmd_profile)

    sp = sub.add_parser(
        "import-strava",
        help="Import runs from a Strava bulk-export archive (.zip or activities.csv)",
    )
    sp.add_argument("path", help="Path to the Strava export .zip or activities.csv")
    sp.set_defaults(func=cmd_import_strava)

    sp = sub.add_parser("import-csv", help="Import runs from a CSV file")
    sp.add_argument("path", help="Path to CSV (headers: date, distance, duration[, name, elevation])")
    sp.set_defaults(func=cmd_import_csv)

    sp = sub.add_parser(
        "import-meets",
        help="Find and import your race results by name (from Athletic.net)",
    )
    sp.add_argument("name", help="Athlete name to search, e.g. \"Jordan Rivera\"")
    sp.add_argument("--pick", type=int, default=None,
                    help="Import the Nth match from the search list")
    sp.set_defaults(func=cmd_import_meets)

    sub.add_parser("status", help="Show fitness, trends, and training paces").set_defaults(
        func=cmd_status
    )

    sp = sub.add_parser("predict", help="Predict race times")
    sp.add_argument("--distance", help="Single distance (e.g. 10k). Omit for a full table.")
    sp.set_defaults(func=cmd_predict)

    sp = sub.add_parser("goal", help="Set your target race")
    sp.add_argument("distance", help="e.g. half, marathon, 10k")
    sp.add_argument("date", help="Race date, ISO format YYYY-MM-DD")
    sp.add_argument("--name", help="Race name")
    sp.add_argument("--target", help="Goal time, e.g. 1:45:00")
    sp.set_defaults(func=cmd_goal)

    sp = sub.add_parser("plan", help="Generate a personalized training plan")
    sp.add_argument("--distance", help="Goal distance (if no goal set)")
    sp.add_argument("--date", help="Race date YYYY-MM-DD (if no goal set)")
    sp.add_argument("--name", help="Race name")
    sp.add_argument("--weeks", type=int, default=4, help="How many weeks to display")
    sp.add_argument("--all", action="store_true", help="Show every week")
    sp.set_defaults(func=cmd_plan)

    sub.add_parser("seed", help="Add sample data for a demo").set_defaults(func=cmd_seed)
    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
