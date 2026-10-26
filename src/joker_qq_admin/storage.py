from __future__ import annotations

from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any


class SQLiteStore:
    """Small persistent store for official QQ bot features.

    The official bot only gives the application openid values. All group and
    user state is therefore keyed by those values instead of numeric QQ IDs.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._connection = sqlite3.connect(
            self.path,
            check_same_thread=False,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._initialize()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _initialize(self) -> None:
        with self._lock:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    scope_id TEXT NOT NULL,
                    setting_key TEXT NOT NULL,
                    setting_value TEXT NOT NULL,
                    PRIMARY KEY (scope_id, setting_key)
                );
                CREATE TABLE IF NOT EXISTS replies (
                    scope_id TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    response TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (scope_id, trigger)
                );
                CREATE TABLE IF NOT EXISTS message_stats (
                    scope_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    messages INTEGER NOT NULL DEFAULT 0,
                    last_seen TEXT NOT NULL,
                    PRIMARY KEY (scope_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS checkins (
                    scope_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    day TEXT NOT NULL,
                    streak INTEGER NOT NULL,
                    points INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (scope_id, user_id, day)
                );
                CREATE TABLE IF NOT EXISTS server_bindings (
                    scope_id TEXT PRIMARY KEY,
                    server_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS official_group_bindings (
                    group_openid TEXT PRIMARY KEY,
                    numeric_group_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS lotteries (
                    scope_id TEXT NOT NULL,
                    lottery_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    winner_count INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL,
                    drawn_at TEXT
                );
                CREATE TABLE IF NOT EXISTS lottery_entries (
                    lottery_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (lottery_id, user_id),
                    FOREIGN KEY (lottery_id) REFERENCES lotteries(lottery_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS blacklist (
                    scope_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (scope_id, user_id)
                );
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def get_setting(self, scope_id: str, key: str, default: str = "") -> str:
        with self._lock, closing(self._connection.execute(
            "SELECT setting_value FROM settings WHERE scope_id=? AND setting_key=?",
            (scope_id, key),
        )) as cursor:
            row = cursor.fetchone()
        return str(row[0]) if row else default

    def set_setting(self, scope_id: str, key: str, value: Any) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO settings(scope_id, setting_key, setting_value)
                VALUES (?, ?, ?)
                ON CONFLICT(scope_id, setting_key) DO UPDATE SET setting_value=excluded.setting_value
                """,
                (scope_id, key, str(value)),
            )

    def record_message(self, scope_id: str, user_id: str) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO message_stats(scope_id, user_id, messages, last_seen)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(scope_id, user_id) DO UPDATE SET
                    messages=message_stats.messages + 1,
                    last_seen=excluded.last_seen
                """,
                (scope_id, user_id, self._now()),
            )

    def user_message_count(self, scope_id: str, user_id: str) -> int:
        with self._lock, closing(self._connection.execute(
            "SELECT messages FROM message_stats WHERE scope_id=? AND user_id=?",
            (scope_id, user_id),
        )) as cursor:
            row = cursor.fetchone()
        return int(row[0]) if row else 0

    def group_message_count(self, scope_id: str) -> int:
        with self._lock, closing(self._connection.execute(
            "SELECT COALESCE(SUM(messages), 0) FROM message_stats WHERE scope_id=?",
            (scope_id,),
        )) as cursor:
            return int(cursor.fetchone()[0])

    def top_users(self, scope_id: str, limit: int = 10) -> list[tuple[str, int]]:
        with self._lock, closing(self._connection.execute(
            """
            SELECT user_id, messages FROM message_stats
            WHERE scope_id=? ORDER BY messages DESC, user_id ASC LIMIT ?
            """,
            (scope_id, max(1, min(limit, 50))),
        )) as cursor:
            return [(str(row[0]), int(row[1])) for row in cursor.fetchall()]

    def check_in(self, scope_id: str, user_id: str) -> dict[str, int | bool]:
        today = date.today()
        today_text = today.isoformat()
        with self._lock:
            existing = self._connection.execute(
                "SELECT streak, points FROM checkins WHERE scope_id=? AND user_id=? AND day=?",
                (scope_id, user_id, today_text),
            ).fetchone()
            if existing:
                return {"created": False, "streak": int(existing[0]), "points": int(existing[1])}

            previous = self._connection.execute(
                """
                SELECT streak FROM checkins
                WHERE scope_id=? AND user_id=? ORDER BY day DESC LIMIT 1
                """,
                (scope_id, user_id),
            ).fetchone()
            previous_streak = int(previous[0]) if previous else 0
            previous_day = self._connection.execute(
                """
                SELECT day FROM checkins
                WHERE scope_id=? AND user_id=? ORDER BY day DESC LIMIT 1
                """,
                (scope_id, user_id),
            ).fetchone()
            streak = previous_streak + 1 if previous_day and str(previous_day[0]) == (today.fromordinal(today.toordinal() - 1)).isoformat() else 1
            points = 10 + min(streak, 30)
            self._connection.execute(
                "INSERT INTO checkins(scope_id, user_id, day, streak, points, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (scope_id, user_id, today_text, streak, points, self._now()),
            )
            return {"created": True, "streak": streak, "points": points}

    def checkin_history(self, scope_id: str, user_id: str, limit: int = 30) -> list[sqlite3.Row]:
        with self._lock, closing(self._connection.execute(
            """
            SELECT day, streak, points FROM checkins
            WHERE scope_id=? AND user_id=? ORDER BY day DESC LIMIT ?
            """,
            (scope_id, user_id, max(1, min(limit, 365))),
        )) as cursor:
            return cursor.fetchall()

    def points_ranking(self, scope_id: str, limit: int = 10) -> list[tuple[str, int]]:
        with self._lock, closing(self._connection.execute(
            """
            SELECT user_id, COALESCE(SUM(points), 0) AS total
            FROM checkins WHERE scope_id=? GROUP BY user_id
            ORDER BY total DESC, user_id ASC LIMIT ?
            """,
            (scope_id, max(1, min(limit, 50))),
        )) as cursor:
            return [(str(row[0]), int(row[1])) for row in cursor.fetchall()]

    def save_reply(self, scope_id: str, trigger: str, response: str) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO replies(scope_id, trigger, response, enabled, updated_at)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(scope_id, trigger) DO UPDATE SET
                    response=excluded.response, enabled=1, updated_at=excluded.updated_at
                """,
                (scope_id, trigger, response, self._now()),
            )

    def delete_reply(self, scope_id: str, trigger: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM replies WHERE scope_id=? AND trigger=?",
                (scope_id, trigger),
            )
            return cursor.rowcount > 0

    def list_replies(self, scope_id: str) -> list[tuple[str, str, bool]]:
        with self._lock, closing(self._connection.execute(
            "SELECT trigger, response, enabled FROM replies WHERE scope_id=? ORDER BY trigger",
            (scope_id,),
        )) as cursor:
            return [(str(row[0]), str(row[1]), bool(row[2])) for row in cursor.fetchall()]

    def find_reply(self, scope_id: str, trigger: str) -> str | None:
        with self._lock, closing(self._connection.execute(
            "SELECT response FROM replies WHERE scope_id=? AND trigger=? AND enabled=1",
            (scope_id, trigger),
        )) as cursor:
            row = cursor.fetchone()
        return str(row[0]) if row else None

    def bind_server(self, scope_id: str, server_id: str) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO server_bindings(scope_id, server_id, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(scope_id) DO UPDATE SET server_id=excluded.server_id, updated_at=excluded.updated_at
                """,
                (scope_id, server_id, self._now()),
            )

    def get_server(self, scope_id: str) -> str | None:
        with self._lock, closing(self._connection.execute(
            "SELECT server_id FROM server_bindings WHERE scope_id=?",
            (scope_id,),
        )) as cursor:
            row = cursor.fetchone()
        return str(row[0]) if row else None

    def unbind_server(self, scope_id: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM server_bindings WHERE scope_id=?",
                (scope_id,),
            )
            return cursor.rowcount > 0

    def bind_official_group(self, group_openid: str, numeric_group_id: str) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO official_group_bindings(group_openid, numeric_group_id, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(group_openid) DO UPDATE SET
                    numeric_group_id=excluded.numeric_group_id, updated_at=excluded.updated_at
                """,
                (group_openid, numeric_group_id, self._now()),
            )

    def get_official_group_binding(self, group_openid: str) -> str | None:
        with self._lock, closing(self._connection.execute(
            "SELECT numeric_group_id FROM official_group_bindings WHERE group_openid=?",
            (group_openid,),
        )) as cursor:
            row = cursor.fetchone()
        return str(row[0]) if row else None

    def create_lottery(self, scope_id: str, title: str, winner_count: int) -> int:
        with self._lock:
            cursor = self._connection.execute(
                "INSERT INTO lotteries(scope_id, title, winner_count, created_at) VALUES (?, ?, ?, ?)",
                (scope_id, title, max(1, min(winner_count, 20)), self._now()),
            )
            return int(cursor.lastrowid)

    def open_lottery(self, scope_id: str) -> sqlite3.Row | None:
        with self._lock, closing(self._connection.execute(
            "SELECT * FROM lotteries WHERE scope_id=? AND status='open' ORDER BY lottery_id DESC LIMIT 1",
            (scope_id,),
        )) as cursor:
            return cursor.fetchone()

    def add_lottery_entry(self, lottery_id: int, user_id: str, display_name: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                """
                INSERT OR IGNORE INTO lottery_entries(lottery_id, user_id, display_name, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (lottery_id, user_id, display_name or user_id, self._now()),
            )
            return cursor.rowcount > 0

    def lottery_entries(self, lottery_id: int) -> list[tuple[str, str]]:
        with self._lock, closing(self._connection.execute(
            "SELECT user_id, display_name FROM lottery_entries WHERE lottery_id=? ORDER BY created_at",
            (lottery_id,),
        )) as cursor:
            return [(str(row[0]), str(row[1])) for row in cursor.fetchall()]

    def draw_lottery(self, lottery_id: int) -> None:
        with self._lock:
            self._connection.execute(
                "UPDATE lotteries SET status='drawn', drawn_at=? WHERE lottery_id=? AND status='open'",
                (self._now(), lottery_id),
            )

    def add_blacklist(self, scope_id: str, user_id: str, reason: str = "") -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO blacklist(scope_id, user_id, reason, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(scope_id, user_id) DO UPDATE SET reason=excluded.reason
                """,
                (scope_id, user_id, reason, self._now()),
            )

    def remove_blacklist(self, scope_id: str, user_id: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM blacklist WHERE scope_id=? AND user_id=?",
                (scope_id, user_id),
            )
            return cursor.rowcount > 0

    def is_blacklisted(self, scope_id: str, user_id: str) -> bool:
        with self._lock, closing(self._connection.execute(
            "SELECT 1 FROM blacklist WHERE scope_id=? AND user_id=?",
            (scope_id, user_id),
        )) as cursor:
            return cursor.fetchone() is not None

    def list_blacklist(self, scope_id: str) -> list[tuple[str, str]]:
        with self._lock, closing(self._connection.execute(
            "SELECT user_id, reason FROM blacklist WHERE scope_id=? ORDER BY created_at",
            (scope_id,),
        )) as cursor:
            return [(str(row[0]), str(row[1])) for row in cursor.fetchall()]

    def clear_blacklist(self, scope_id: str) -> int:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM blacklist WHERE scope_id=?",
                (scope_id,),
            )
            return int(cursor.rowcount)

