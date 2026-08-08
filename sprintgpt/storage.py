"""SQLite persistence.

Multi-user: every runner is a row in `users`. A user may be a registered account
(email + hashed password) or an anonymous session (identified by a session token),
optionally linked to a Strava athlete. All activities, goals, and profile settings
are scoped to a user so people only ever see their own data.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from .models import Activity, Goal, Profile

# Session token used by the local CLI and the "Explore demo" web login.
DEMO_TOKEN = "demo"


class Storage:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self) -> None:
        # 1) Create tables (no-ops if they already exist).
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_token TEXT UNIQUE,
                email TEXT,
                password_hash TEXT,
                account_name TEXT,
                city TEXT,
                state TEXT,
                athlete_id TEXT,
                display_name TEXT,
                strava_access_token TEXT,
                strava_refresh_token TEXT,
                strava_expires_at INTEGER,
                max_hr INTEGER DEFAULT 190,
                resting_hr INTEGER,
                sex TEXT DEFAULT 'm',
                theme TEXT DEFAULT 'emerald',
                accent TEXT,
                accent2 TEXT,
                bot_name TEXT DEFAULT 'Coach',
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                start_date TEXT NOT NULL,
                distance_m REAL NOT NULL,
                moving_time_s INTEGER NOT NULL,
                name TEXT,
                elevation_gain_m REAL DEFAULT 0,
                average_hr REAL,
                source TEXT DEFAULT 'manual',
                external_id TEXT
            );

            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                race_name TEXT NOT NULL,
                race_date TEXT NOT NULL,
                distance_m REAL NOT NULL,
                target_time_s INTEGER
            );

            CREATE TABLE IF NOT EXISTS password_resets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used INTEGER DEFAULT 0,
                created_at TEXT
            );
            """
        )
        # 2) Migrate any pre-multi-user tables so the columns below exist.
        self._migrate_legacy()
        # 3) Now the indexes referencing user_id are safe to create.
        self.conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_activities_user ON activities(user_id, start_date);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_activities_user_ext
                ON activities(user_id, external_id) WHERE external_id IS NOT NULL;
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email
                ON users(email) WHERE email IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_messages(user_id, id);
            CREATE INDEX IF NOT EXISTS idx_reset_token ON password_resets(token_hash);
            """
        )
        self.conn.commit()

    def _migrate_legacy(self) -> None:
        """Add columns to pre-existing tables so older DBs keep working."""
        for table in ("activities", "goals"):
            cols = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            if "user_id" not in cols:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER")
        # Account + theme columns added after the initial multi-user schema.
        user_cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(users)")}
        for col in ("email", "password_hash", "account_name", "theme", "accent",
                    "accent2", "bot_name", "city", "state"):
            if col not in user_cols:
                self.conn.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")

    # ---- users --------------------------------------------------------------
    def get_or_create_user(self, session_token: str) -> int:
        row = self.conn.execute(
            "SELECT id FROM users WHERE session_token = ?", (session_token,)
        ).fetchone()
        if row:
            return row["id"]
        cur = self.conn.execute(
            "INSERT INTO users (session_token, created_at) VALUES (?, ?)",
            (session_token, datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()
        return cur.lastrowid

    def find_user_by_token(self, session_token: str) -> Optional[int]:
        row = self.conn.execute(
            "SELECT id FROM users WHERE session_token = ?", (session_token,)
        ).fetchone()
        return row["id"] if row else None

    def get_user(self, user_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()

    # ---- accounts (email + password login) ----------------------------------
    def get_account_by_email(self, email: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
        ).fetchone()

    def email_exists(self, email: str) -> bool:
        return self.get_account_by_email(email) is not None

    def create_account(
        self,
        email: str,
        password_hash: str,
        name: str,
        attach_user_id: Optional[int] = None,
    ) -> int:
        """Create an account, or upgrade an existing anonymous row into one.

        `attach_user_id` lets a visitor keep runs they imported before signing up:
        the anonymous session row is turned into their account instead of orphaning
        that data.
        """
        email = email.strip().lower()
        if attach_user_id is not None:
            self.conn.execute(
                "UPDATE users SET email = ?, password_hash = ?, account_name = ? WHERE id = ?",
                (email, password_hash, name, attach_user_id),
            )
            self.conn.commit()
            return attach_user_id
        cur = self.conn.execute(
            "INSERT INTO users (email, password_hash, account_name, created_at) "
            "VALUES (?, ?, ?, ?)",
            (email, password_hash, name, datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_account(
        self,
        user_id: int,
        name: str,
        city: Optional[str] = None,
        state: Optional[str] = None,
    ) -> None:
        """Save editable account profile fields (name + home location)."""
        self.conn.execute(
            "UPDATE users SET account_name = ?, city = ?, state = ? WHERE id = ?",
            (name, (city or None), (state or None), user_id),
        )
        self.conn.commit()

    def set_password(self, user_id: int, password_hash: str) -> None:
        self.conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id)
        )
        self.conn.commit()

    # ---- password resets ----------------------------------------------------
    def create_password_reset(
        self, user_id: int, token_hash: str, expires_at: datetime
    ) -> int:
        """Store a reset token (hashed), invalidating any earlier unused ones."""
        self.conn.execute(
            "UPDATE password_resets SET used = 1 WHERE user_id = ? AND used = 0",
            (user_id,),
        )
        cur = self.conn.execute(
            "INSERT INTO password_resets (user_id, token_hash, expires_at, used, created_at) "
            "VALUES (?, ?, ?, 0, ?)",
            (user_id, token_hash, expires_at.isoformat(),
             datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_valid_reset(self, token_hash: str) -> Optional[sqlite3.Row]:
        """Return an unused, unexpired reset row for this token hash, or None."""
        row = self.conn.execute(
            "SELECT * FROM password_resets WHERE token_hash = ? AND used = 0",
            (token_hash,),
        ).fetchone()
        if not row:
            return None
        try:
            expires = datetime.fromisoformat(row["expires_at"])
        except (ValueError, TypeError):
            return None
        if expires < datetime.now(timezone.utc):
            return None
        return row

    def consume_reset(self, reset_id: int) -> None:
        self.conn.execute(
            "UPDATE password_resets SET used = 1 WHERE id = ?", (reset_id,)
        )
        self.conn.commit()

    # ---- activities ---------------------------------------------------------
    def add_activity(self, user_id: int, activity: Activity) -> Optional[int]:
        """Insert an activity for a user. Returns row id, or None if duplicate."""
        try:
            cur = self.conn.execute(
                """
                INSERT INTO activities
                    (user_id, start_date, distance_m, moving_time_s, name,
                     elevation_gain_m, average_hr, source, external_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    activity.start_date.isoformat(),
                    activity.distance_m,
                    activity.moving_time_s,
                    activity.name,
                    activity.elevation_gain_m,
                    activity.average_hr,
                    activity.source,
                    activity.external_id,
                ),
            )
            self.conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            # Duplicate (user_id, external_id) - already synced from Strava.
            return None

    def get_activities(self, user_id: int, since: Optional[date] = None) -> list[Activity]:
        query = "SELECT * FROM activities WHERE user_id = ?"
        params: list = [user_id]
        if since is not None:
            query += " AND start_date >= ?"
            params.append(since.isoformat())
        query += " ORDER BY start_date ASC"
        rows = self.conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_activity(r) for r in rows]

    def get_activity(self, user_id: int, activity_id: int) -> Optional[Activity]:
        row = self.conn.execute(
            "SELECT * FROM activities WHERE id = ? AND user_id = ?",
            (activity_id, user_id),
        ).fetchone()
        return self._row_to_activity(row) if row else None

    def latest_activity_date(self, user_id: int) -> Optional[datetime]:
        row = self.conn.execute(
            "SELECT MAX(start_date) AS d FROM activities "
            "WHERE user_id = ? AND source = 'strava'",
            (user_id,),
        ).fetchone()
        if row and row["d"]:
            return datetime.fromisoformat(row["d"])
        return None

    def count_activities(self, user_id: int) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) AS c FROM activities WHERE user_id = ?", (user_id,)
        ).fetchone()["c"]

    # ---- goals --------------------------------------------------------------
    def set_goal(self, user_id: int, goal: Goal) -> int:
        self.conn.execute("DELETE FROM goals WHERE user_id = ?", (user_id,))
        cur = self.conn.execute(
            "INSERT INTO goals (user_id, race_name, race_date, distance_m, target_time_s) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, goal.race_name, goal.race_date.isoformat(),
             goal.distance_m, goal.target_time_s),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_goal(self, user_id: int) -> Optional[Goal]:
        row = self.conn.execute(
            "SELECT * FROM goals WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)
        ).fetchone()
        if not row:
            return None
        return Goal(
            id=row["id"],
            race_name=row["race_name"],
            race_date=date.fromisoformat(row["race_date"]),
            distance_m=row["distance_m"],
            target_time_s=row["target_time_s"],
        )

    # ---- profile (stored on the user row) -----------------------------------
    def set_profile(self, user_id: int, profile: Profile) -> None:
        self.conn.execute(
            "UPDATE users SET max_hr = ?, resting_hr = ?, sex = ? WHERE id = ?",
            (profile.max_hr, profile.resting_hr, profile.sex, user_id),
        )
        self.conn.commit()

    def set_theme(
        self,
        user_id: int,
        theme: str,
        accent: Optional[str] = None,
        accent2: Optional[str] = None,
    ) -> None:
        self.conn.execute(
            "UPDATE users SET theme = ?, accent = ?, accent2 = ? WHERE id = ?",
            (theme, accent, accent2, user_id),
        )
        self.conn.commit()

    # ---- chatbot ------------------------------------------------------------
    def get_bot_name(self, user_id: int) -> str:
        row = self.get_user(user_id)
        name = (row["bot_name"] if row else None) or "Coach"
        return name

    def set_bot_name(self, user_id: int, name: str) -> None:
        self.conn.execute(
            "UPDATE users SET bot_name = ? WHERE id = ?", (name, user_id)
        )
        self.conn.commit()

    def add_chat_message(self, user_id: int, role: str, content: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO chat_messages (user_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?)",
            (user_id, role, content, datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_chat_messages(self, user_id: int, limit: int = 200) -> list[dict]:
        rows = self.conn.execute(
            "SELECT role, content, created_at FROM chat_messages "
            "WHERE user_id = ? ORDER BY id ASC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [{"role": r["role"], "content": r["content"], "created_at": r["created_at"]} for r in rows]

    def clear_chat(self, user_id: int) -> None:
        self.conn.execute("DELETE FROM chat_messages WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def get_profile(self, user_id: int) -> Optional[Profile]:
        row = self.get_user(user_id)
        if not row:
            return None
        return Profile(
            max_hr=row["max_hr"] or 190,
            resting_hr=row["resting_hr"],
            sex=row["sex"] or "m",
        )

    # ---- Strava tokens (per user) -------------------------------------------
    def set_strava(
        self,
        user_id: int,
        athlete_id: Optional[str],
        display_name: Optional[str],
        access_token: str,
        refresh_token: str,
        expires_at: int,
    ) -> None:
        self.conn.execute(
            """
            UPDATE users SET
                athlete_id = COALESCE(?, athlete_id),
                display_name = COALESCE(?, display_name),
                strava_access_token = ?,
                strava_refresh_token = ?,
                strava_expires_at = ?
            WHERE id = ?
            """,
            (athlete_id, display_name, access_token, refresh_token, expires_at, user_id),
        )
        self.conn.commit()

    def get_strava(self, user_id: int) -> Optional[dict]:
        row = self.get_user(user_id)
        if not row or not row["strava_refresh_token"]:
            return None
        return {
            "athlete_id": row["athlete_id"],
            "display_name": row["display_name"],
            "access_token": row["strava_access_token"],
            "refresh_token": row["strava_refresh_token"],
            "expires_at": row["strava_expires_at"] or 0,
        }

    def clear_strava(self, user_id: int) -> None:
        self.conn.execute(
            "UPDATE users SET strava_access_token = NULL, strava_refresh_token = NULL, "
            "strava_expires_at = NULL WHERE id = ?",
            (user_id,),
        )
        self.conn.commit()

    @staticmethod
    def _row_to_activity(row: sqlite3.Row) -> Activity:
        return Activity(
            id=row["id"],
            start_date=datetime.fromisoformat(row["start_date"]),
            distance_m=row["distance_m"],
            moving_time_s=row["moving_time_s"],
            name=row["name"] or "Run",
            elevation_gain_m=row["elevation_gain_m"] or 0.0,
            average_hr=row["average_hr"],
            source=row["source"] or "manual",
            external_id=row["external_id"],
        )

    # ---- admin analytics ----------------------------------------------------
    def first_user_id(self) -> Optional[int]:
        """Lowest-id registered account (used as the bootstrap owner/admin)."""
        row = self.conn.execute(
            "SELECT MIN(id) AS m FROM users WHERE email IS NOT NULL"
        ).fetchone()
        return row["m"] if row and row["m"] is not None else None

    def _scalar(self, query: str, params: tuple = ()):
        return self.conn.execute(query, params).fetchone()[0]

    def admin_stats(self) -> dict:
        """Aggregate developer/analytics numbers across all users."""
        now = datetime.now(timezone.utc)

        def signups_since(days: int) -> int:
            cutoff = (now - timedelta(days=days)).isoformat()
            return self._scalar(
                "SELECT COUNT(*) FROM users WHERE email IS NOT NULL AND created_at >= ?",
                (cutoff,),
            )

        total_accounts = self._scalar(
            "SELECT COUNT(*) FROM users WHERE email IS NOT NULL"
        )
        total_rows = self._scalar("SELECT COUNT(*) FROM users")
        total_runs = self._scalar("SELECT COUNT(*) FROM activities") or 0
        total_distance_m = self._scalar("SELECT COALESCE(SUM(distance_m), 0) FROM activities") or 0
        total_elev_m = self._scalar("SELECT COALESCE(SUM(elevation_gain_m), 0) FROM activities") or 0
        accounts_with_data = self._scalar(
            "SELECT COUNT(DISTINCT a.user_id) FROM activities a "
            "JOIN users u ON u.id = a.user_id WHERE u.email IS NOT NULL"
        )
        strava_connected = self._scalar(
            "SELECT COUNT(*) FROM users "
            "WHERE email IS NOT NULL AND strava_refresh_token IS NOT NULL"
        )
        chat_messages = self._scalar("SELECT COUNT(*) FROM chat_messages") or 0
        chat_users = self._scalar("SELECT COUNT(DISTINCT user_id) FROM chat_messages") or 0
        goals_set = self._scalar("SELECT COUNT(DISTINCT user_id) FROM goals") or 0
        reset_requests = self._scalar("SELECT COUNT(*) FROM password_resets") or 0

        return {
            "total_accounts": total_accounts,
            "anonymous_sessions": max(total_rows - total_accounts, 0),
            "signups_24h": signups_since(1),
            "signups_7d": signups_since(7),
            "signups_30d": signups_since(30),
            "accounts_with_data": accounts_with_data,
            "activation_rate": (
                round(100 * accounts_with_data / total_accounts) if total_accounts else 0
            ),
            "strava_connected": strava_connected,
            "total_runs": total_runs,
            "total_distance_km": round(total_distance_m / 1000.0, 1),
            "total_elevation_m": int(total_elev_m),
            "chat_messages": chat_messages,
            "chat_users": chat_users,
            "goals_set": goals_set,
            "reset_requests": reset_requests,
            "avg_runs_per_active": (
                round(total_runs / accounts_with_data, 1) if accounts_with_data else 0
            ),
        }

    def signup_series(self, days: int = 30) -> list[tuple[str, int]]:
        """Daily signup counts for the last ``days`` days (zero-filled)."""
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days - 1)).date()
        rows = self.conn.execute(
            "SELECT created_at FROM users WHERE email IS NOT NULL AND created_at >= ?",
            (cutoff_date.isoformat(),),
        ).fetchall()
        counts: dict[str, int] = {}
        for r in rows:
            raw = r["created_at"] or ""
            day = raw[:10]
            if day:
                counts[day] = counts.get(day, 0) + 1
        series = []
        for i in range(days):
            d = (cutoff_date + timedelta(days=i)).isoformat()
            series.append((d, counts.get(d, 0)))
        return series

    def source_breakdown(self) -> list[tuple[str, int, float]]:
        """(source, run count, total km) for every activity source."""
        rows = self.conn.execute(
            "SELECT COALESCE(source, 'manual') AS s, COUNT(*) AS c, "
            "COALESCE(SUM(distance_m), 0) AS d FROM activities GROUP BY s ORDER BY c DESC"
        ).fetchall()
        return [(r["s"], r["c"], round(r["d"] / 1000.0, 1)) for r in rows]

    def theme_breakdown(self) -> list[tuple[str, int]]:
        rows = self.conn.execute(
            "SELECT COALESCE(NULLIF(TRIM(theme), ''), 'emerald') AS t, COUNT(*) AS c "
            "FROM users WHERE email IS NOT NULL GROUP BY t ORDER BY c DESC"
        ).fetchall()
        return [(r["t"], r["c"]) for r in rows]

    def top_locations(self, limit: int = 8) -> list[tuple[str, int]]:
        rows = self.conn.execute(
            "SELECT COALESCE(NULLIF(TRIM(state), ''), 'Not set') AS st, COUNT(*) AS c "
            "FROM users WHERE email IS NOT NULL GROUP BY st ORDER BY c DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [(r["st"], r["c"]) for r in rows]

    def recent_signups(self, limit: int = 25) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT u.id, u.email, u.account_name, u.city, u.state, u.created_at,
                   (u.strava_refresh_token IS NOT NULL) AS strava,
                   (SELECT COUNT(*) FROM activities a WHERE a.user_id = u.id) AS runs
            FROM users u
            WHERE u.email IS NOT NULL
            ORDER BY u.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        out = []
        for r in rows:
            out.append({
                "id": r["id"],
                "email": r["email"],
                "name": r["account_name"] or (r["email"].split("@")[0] if r["email"] else "—"),
                "location": ", ".join(b for b in ((r["city"] or "").strip(),
                                                  (r["state"] or "").strip()) if b) or "—",
                "created_at": r["created_at"] or "",
                "strava": bool(r["strava"]),
                "runs": r["runs"],
            })
        return out

    def close(self) -> None:
        self.conn.close()
