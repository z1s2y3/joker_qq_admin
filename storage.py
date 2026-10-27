from __future__ import annotations

from contextlib import closing
from datetime import date, datetime, timezone
import hashlib
import hmac
from pathlib import Path
import secrets
import sqlite3
import time
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
                    match_mode TEXT NOT NULL DEFAULT 'exact',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (scope_id, trigger)
                );
                CREATE TABLE IF NOT EXISTS user_replies (
                    scope_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    response TEXT NOT NULL,
                    match_mode TEXT NOT NULL DEFAULT 'exact',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (scope_id, user_id, trigger)
                );
                CREATE TABLE IF NOT EXISTS message_stats (
                    scope_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    messages INTEGER NOT NULL DEFAULT 0,
                    last_seen TEXT NOT NULL,
                    PRIMARY KEY (scope_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS message_records (
                    scope_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    recalled INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (scope_id, message_id)
                );
                CREATE TABLE IF NOT EXISTS group_admins (
                    scope_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
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
                CREATE TABLE IF NOT EXISTS keyword_rules (
                    rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    duration_minutes INTEGER NOT NULL DEFAULT 10,
                    duration_seconds INTEGER NOT NULL DEFAULT 600,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (scope_id, action, trigger)
                );
                CREATE TABLE IF NOT EXISTS scheduled_messages (
                    schedule_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    interval_seconds INTEGER NOT NULL,
                    next_run_at INTEGER NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_sent_at TEXT NOT NULL DEFAULT '',
                    last_error TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    run_at INTEGER NOT NULL,
                    mute_seconds INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    completed_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    last_error TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS dashboard_users (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL DEFAULT '',
                    display_name TEXT NOT NULL DEFAULT '',
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    scope_id TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    email_verified INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dashboard_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES dashboard_users(user_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS dashboard_user_groups (
                    user_id INTEGER NOT NULL,
                    scope_id TEXT NOT NULL,
                    card_code TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, scope_id),
                    UNIQUE (scope_id),
                    FOREIGN KEY (user_id) REFERENCES dashboard_users(user_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS dashboard_user_licenses (
                    user_id INTEGER PRIMARY KEY,
                    card_code TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES dashboard_users(user_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS dashboard_email_verifications (
                    email TEXT PRIMARY KEY,
                    code_hash TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    sent_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS access_cards (
                    card_code TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    scope_id TEXT NOT NULL DEFAULT '',
                    max_uses INTEGER NOT NULL DEFAULT 1,
                    used_count INTEGER NOT NULL DEFAULT 0,
                    bot_used_count INTEGER NOT NULL DEFAULT 0,
                    expires_at INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS bot_authorizations (
                    user_openid TEXT PRIMARY KEY,
                    scope_id TEXT NOT NULL DEFAULT '',
                    card_code TEXT NOT NULL,
                    expires_at INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS group_authorizations (
                    scope_id TEXT PRIMARY KEY,
                    card_code TEXT NOT NULL,
                    expires_at INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column("dashboard_users", "email", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("dashboard_users", "display_name", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("dashboard_users", "email_verified", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("replies", "match_mode", "TEXT NOT NULL DEFAULT 'exact'")
            self._ensure_column("user_replies", "match_mode", "TEXT NOT NULL DEFAULT 'exact'")
            self._ensure_column("message_records", "recalled", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("keyword_rules", "duration_seconds", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("access_cards", "bot_used_count", "INTEGER NOT NULL DEFAULT 0")
            self._connection.execute("UPDATE message_records SET content='' WHERE content <> ''")
            self._connection.execute(
                """
                UPDATE keyword_rules
                SET duration_seconds=MAX(1, duration_minutes) * 60
                WHERE duration_seconds IS NULL OR duration_seconds <= 0
                """
            )
            self._connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_dashboard_users_email ON dashboard_users(email) WHERE email <> ''"
            )
            self._connection.execute(
                """
                INSERT OR IGNORE INTO dashboard_user_groups(user_id, scope_id, card_code, created_at)
                SELECT user_id, scope_id, '', created_at
                FROM dashboard_users
                WHERE role='group' AND scope_id <> ''
                """
            )
            self._connection.execute(
                """
                INSERT OR IGNORE INTO group_authorizations(scope_id, card_code, expires_at, enabled, created_at)
                SELECT g.scope_id, g.card_code, c.expires_at,
                    CASE WHEN c.enabled=1 THEN 1 ELSE 0 END, g.created_at
                FROM dashboard_user_groups g
                JOIN access_cards c ON c.card_code=g.card_code
                WHERE g.card_code <> ''
                """
            )
            migrated = self._connection.execute(
                "SELECT 1 FROM settings WHERE scope_id='__global__' AND setting_key='group_authorization_migration_v1'"
            ).fetchone()
            if not migrated:
                self._connection.execute(
                    """
                    UPDATE access_cards
                    SET used_count=MAX(0, used_count-1)
                    WHERE used_count>0
                      AND card_code IN (
                        SELECT card_code FROM dashboard_user_licenses
                        UNION
                        SELECT card_code FROM bot_authorizations WHERE bot_used_count=0
                      )
                      AND NOT EXISTS (
                        SELECT 1 FROM group_authorizations g WHERE g.card_code=access_cards.card_code
                      )
                    """
                )
                self._connection.execute("DELETE FROM dashboard_user_licenses")
                self._connection.execute("DELETE FROM bot_authorizations")
                self._connection.execute(
                    "INSERT INTO settings(scope_id, setting_key, setting_value) VALUES ('__global__', 'group_authorization_migration_v1', '1')"
                )
            released_cards = self._connection.execute(
                "SELECT 1 FROM settings WHERE scope_id='__global__' AND setting_key='group_authorization_migration_v2'"
            ).fetchone()
            if not released_cards:
                self._connection.execute(
                    """
                    UPDATE access_cards
                    SET used_count=0
                    WHERE used_count>0
                      AND NOT EXISTS (
                        SELECT 1 FROM group_authorizations g WHERE g.card_code=access_cards.card_code
                      )
                    """
                )
                self._connection.execute(
                    "INSERT INTO settings(scope_id, setting_key, setting_value) VALUES ('__global__', 'group_authorization_migration_v2', '1')"
                )

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {
            str(row[1])
            for row in self._connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            self._connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _password_hash(password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 240000)
        return f"pbkdf2_sha256$240000${salt.hex()}${digest.hex()}"

    @staticmethod
    def _password_matches(password: str, encoded: str) -> bool:
        try:
            algorithm, rounds, salt_hex, digest_hex = encoded.split("$", 3)
            if algorithm != "pbkdf2_sha256":
                return False
            digest = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds)
            )
        except (TypeError, ValueError):
            return False
        return hmac.compare_digest(digest.hex(), digest_hex)

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _email_code_hash(email: str, code: str) -> str:
        return hashlib.sha256(f"{email.lower()}:{code}".encode("utf-8")).hexdigest()

    def ensure_dashboard_admin(self, username: str, password: str) -> None:
        username = str(username or "").strip()
        if not username or not password:
            return
        with self._lock:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO dashboard_users
                    (username, password_hash, role, created_at)
                VALUES (?, ?, 'admin', ?)
                """,
                (username, self._password_hash(password), self._now()),
            )

    def authenticate_dashboard_user(self, username: str, password: str) -> dict[str, Any] | None:
        with self._lock, closing(self._connection.execute(
            """
            SELECT user_id, username, email, display_name, password_hash, role, scope_id, email_verified
            FROM dashboard_users WHERE (username=? OR email=?) AND enabled=1
            """,
            (str(username or "").strip(), str(username or "").strip().lower()),
        )) as cursor:
            row = cursor.fetchone()
        if not row or not self._password_matches(password, str(row[4])):
            return None
        return {
            "user_id": int(row[0]),
            "username": str(row[1]),
            "email": str(row[2] or ""),
            "display_name": str(row[3] or ""),
            "role": str(row[5]),
            "scope_id": str(row[6] or ""),
            "email_verified": bool(row[7]),
        }

    def create_dashboard_session(self, user_id: int, max_age: int) -> str:
        token = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + max(300, min(int(max_age), 2_592_000))
        with self._lock:
            self._connection.execute(
                "INSERT INTO dashboard_sessions(token_hash, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
                (self._token_hash(token), int(user_id), expires_at, self._now()),
            )
        return token

    def get_dashboard_session(self, token: str) -> dict[str, Any] | None:
        if not token:
            return None
        with self._lock, closing(self._connection.execute(
            """
            SELECT s.user_id, u.username, u.email, u.display_name, u.role, u.scope_id, u.email_verified, s.expires_at
            FROM dashboard_sessions s JOIN dashboard_users u ON u.user_id=s.user_id
            WHERE s.token_hash=? AND s.expires_at>? AND u.enabled=1
            """,
            (self._token_hash(token), int(time.time())),
        )) as cursor:
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "user_id": int(row[0]),
            "username": str(row[1]),
            "email": str(row[2] or ""),
            "display_name": str(row[3] or ""),
            "role": str(row[4]),
            "scope_id": str(row[5] or ""),
            "email_verified": bool(row[6]),
            "expires_at": int(row[7]),
        }

    def delete_dashboard_session(self, token: str) -> None:
        if not token:
            return
        with self._lock:
            self._connection.execute("DELETE FROM dashboard_sessions WHERE token_hash=?", (self._token_hash(token),))

    def create_access_card(
        self,
        kind: str,
        scope_id: str = "",
        max_uses: int = 1,
        days: int = 30,
        expires_at: int | None = None,
    ) -> str:
        if kind not in {"license", "portal", "group", "bot"}:
            raise ValueError("invalid card kind")
        code = f"JOKER-{secrets.token_hex(5).upper()}"
        now = int(time.time())
        if expires_at is None:
            expires_at = now + max(1, min(int(days), 3650)) * 86400
        else:
            expires_at = int(expires_at)
            if expires_at <= now:
                raise ValueError("到期时间必须晚于当前时间")
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO access_cards(card_code, kind, scope_id, max_uses, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (code, kind, str(scope_id or "").strip(), 1, expires_at, self._now()),
            )
        return code

    def list_access_cards(self) -> list[dict[str, Any]]:
        with self._lock, closing(self._connection.execute(
            "SELECT card_code, kind, scope_id, max_uses, used_count, bot_used_count, expires_at, enabled, created_at FROM access_cards ORDER BY created_at DESC"
        )) as cursor:
            return [
                {
                    "card_code": str(row[0]), "kind": str(row[1]), "scope_id": str(row[2]),
                    "max_uses": int(row[3]), "used_count": int(row[4]), "bot_used_count": int(row[5]),
                    "expires_at": int(row[6]), "enabled": bool(row[7]), "created_at": str(row[8]),
                }
                for row in cursor.fetchall()
            ]

    def set_access_card_enabled(self, card_code: str, enabled: bool) -> bool:
        code = str(card_code).strip().upper()
        with self._lock:
            cursor = self._connection.execute(
                "UPDATE access_cards SET enabled=? WHERE card_code=?", (1 if enabled else 0, code)
            )
            if cursor.rowcount and not enabled:
                self._connection.execute(
                    "UPDATE bot_authorizations SET enabled=0 WHERE card_code=?", (code,)
                )
                self._connection.execute(
                    "UPDATE group_authorizations SET enabled=0 WHERE card_code=?", (code,)
                )
            return cursor.rowcount > 0

    def delete_access_card(self, card_code: str) -> bool:
        code = str(card_code).strip().upper()
        if not code:
            return False
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                self._connection.execute(
                    "UPDATE bot_authorizations SET enabled=0 WHERE card_code=?", (code,)
                )
                self._connection.execute(
                    "DELETE FROM group_authorizations WHERE card_code=?", (code,)
                )
                self._connection.execute(
                    "DELETE FROM dashboard_user_licenses WHERE card_code=?", (code,)
                )
                self._connection.execute(
                    "DELETE FROM dashboard_user_groups WHERE card_code=?", (code,)
                )
                cursor = self._connection.execute(
                    "DELETE FROM access_cards WHERE card_code=?", (code,)
                )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
            return cursor.rowcount > 0

    def _user_has_active_license(self, user_id: int) -> tuple[str, bool] | None:
        row = self._connection.execute(
            """
            SELECT c.card_code, c.enabled, c.expires_at
            FROM dashboard_user_licenses ul
            JOIN access_cards c ON c.card_code=ul.card_code
            WHERE ul.user_id=? AND c.kind IN ('license', 'portal', 'group')
            """,
            (int(user_id),),
        ).fetchone()
        if not row or not bool(row[1]) or (int(row[2]) and int(row[2]) <= int(time.time())):
            return None
        return str(row[0]), True

    def issue_registration_email_code(self, email: str) -> str:
        email = str(email or "").strip().lower()
        if not email or "@" not in email or len(email) > 320:
            raise ValueError("邮箱格式不正确")
        now = int(time.time())
        with self._lock:
            existing = self._connection.execute(
                "SELECT sent_at FROM dashboard_email_verifications WHERE email=?", (email,)
            ).fetchone()
            if existing and now - int(existing[0]) < 60:
                raise ValueError("验证码已发送，请 60 秒后再试")
            code = f"{secrets.randbelow(1_000_000):06d}"
            self._connection.execute(
                """
                INSERT INTO dashboard_email_verifications(email, code_hash, expires_at, attempts, sent_at)
                VALUES (?, ?, ?, 0, ?)
                ON CONFLICT(email) DO UPDATE SET
                    code_hash=excluded.code_hash,
                    expires_at=excluded.expires_at,
                    attempts=0,
                    sent_at=excluded.sent_at
                """,
                (email, self._email_code_hash(email, code), now + 600, now),
            )
        return code

    def discard_registration_email_code(self, email: str) -> None:
        with self._lock:
            self._connection.execute(
                "DELETE FROM dashboard_email_verifications WHERE email=?", (str(email or "").strip().lower(),)
            )

    def _registration_email_code_valid(self, email: str, code: str) -> bool:
        row = self._connection.execute(
            "SELECT code_hash, expires_at, attempts FROM dashboard_email_verifications WHERE email=?",
            (email,),
        ).fetchone()
        if not row or int(row[1]) <= int(time.time()) or int(row[2]) >= 5:
            return False
        if not hmac.compare_digest(str(row[0]), self._email_code_hash(email, code)):
            self._connection.execute(
                "UPDATE dashboard_email_verifications SET attempts=attempts+1 WHERE email=?", (email,)
            )
            return False
        return True

    def register_group_user(
        self, username: str, password: str, card_code: str = "", email: str = "", verification_code: str = ""
    ) -> dict[str, Any] | None:
        username = str(username or "").strip()
        email = str(email or "").strip().lower()
        verification_code = str(verification_code or "").strip()
        if len(username) < 3 or len(password) < 6 or not email or not verification_code:
            return None
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                if not self._registration_email_code_valid(email, verification_code):
                    self._connection.execute("COMMIT")
                    return None
                cursor = self._connection.execute(
                    "INSERT INTO dashboard_users(username, email, display_name, password_hash, role, scope_id, email_verified, created_at) VALUES (?, ?, ?, ?, 'group', ?, ?, ?)",
                    (username, email, username, self._password_hash(password), "", 1 if email else 0, self._now()),
                )
                self._connection.execute(
                    "DELETE FROM dashboard_email_verifications WHERE email=?", (email,)
                )
                self._connection.execute("COMMIT")
            except sqlite3.IntegrityError:
                self._connection.execute("ROLLBACK")
                return None
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return self.authenticate_dashboard_user(username, password)

    def redeem_dashboard_user_license(self, user_id: int, card_code: str) -> dict[str, Any] | None:
        """Attach one valid robot authorization card to a verified dashboard user."""

        card_code = str(card_code or "").strip().upper()
        if not user_id or not card_code:
            return None
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                user = self._connection.execute(
                    "SELECT role, email_verified FROM dashboard_users WHERE user_id=? AND enabled=1",
                    (int(user_id),),
                ).fetchone()
                if not user or str(user[0]) != "group" or not bool(user[1]):
                    self._connection.execute("ROLLBACK")
                    return None
                existing = self._connection.execute(
                    "SELECT card_code FROM dashboard_user_licenses WHERE user_id=?",
                    (int(user_id),),
                ).fetchone()
                row = self._connection.execute(
                    """
                    SELECT max_uses, used_count, expires_at, enabled
                    FROM access_cards
                    WHERE card_code=? AND kind IN ('license', 'portal', 'group')
                    """,
                    (card_code,),
                ).fetchone()
                if not row or not bool(row[3]) or (int(row[2]) and int(row[2]) <= int(time.time())):
                    self._connection.execute("ROLLBACK")
                    return None
                if existing and str(existing[0]) == card_code:
                    self._connection.execute("COMMIT")
                    return {"card_code": card_code, "expires_at": int(row[2]), "already_redeemed": True}
                if int(row[1]) >= int(row[0]):
                    self._connection.execute("ROLLBACK")
                    return None
                if existing:
                    self._connection.execute(
                        "UPDATE access_cards SET used_count=MAX(0, used_count-1) WHERE card_code=?",
                        (str(existing[0]),),
                    )
                self._connection.execute(
                    """
                    INSERT INTO dashboard_user_licenses(user_id, card_code, created_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET card_code=excluded.card_code, created_at=excluded.created_at
                    """,
                    (int(user_id), card_code, self._now()),
                )
                self._connection.execute(
                    "UPDATE access_cards SET used_count=used_count+1 WHERE card_code=?",
                    (card_code,),
                )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return {"card_code": card_code, "expires_at": int(row[2])}

    def dashboard_user_license_status(self, user_id: int) -> dict[str, Any]:
        with self._lock, closing(self._connection.execute(
            """
            SELECT c.card_code, c.expires_at, c.enabled
            FROM dashboard_user_licenses ul
            JOIN access_cards c ON c.card_code=ul.card_code
            WHERE ul.user_id=?
            """,
            (int(user_id),),
        )) as cursor:
            row = cursor.fetchone()
        active = bool(row and row[2] and (not int(row[1]) or int(row[1]) > int(time.time())))
        return {
            "active": active,
            "card_code": str(row[0]) if row else "",
            "expires_at": int(row[1]) if row else 0,
        }

    def _claim_group_authorization_locked(self, scope_id: str, card_code: str) -> dict[str, Any] | None:
        scope_id = self._canonical_group_scope_locked(scope_id)
        aliases = self._group_scope_aliases_locked(scope_id)
        card = self._connection.execute(
            "SELECT used_count, expires_at, enabled FROM access_cards WHERE card_code=?",
            (card_code,),
        ).fetchone()
        if not card or not bool(card[2]) or (int(card[1]) and int(card[1]) <= int(time.time())):
            return {"error": "授权卡无效、已停用或已过期"}
        placeholders = ",".join("?" for _ in aliases)
        existing = self._connection.execute(
            f"SELECT scope_id, card_code, expires_at, enabled FROM group_authorizations "
            f"WHERE scope_id IN ({placeholders}) ORDER BY CASE WHEN scope_id=? THEN 0 ELSE 1 END LIMIT 1",
            (*aliases, scope_id),
        ).fetchone()
        if existing and str(existing[1]) == card_code:
            if bool(existing[3]) and (not int(existing[2]) or int(existing[2]) > int(time.time())):
                return {"scope_id": str(existing[0]), "card_code": card_code, "expires_at": int(existing[2]), "already_authorized": True}
            return {"error": "当前群已使用该卡，但授权已过期或已停用，请使用新卡续期"}
        if int(card[0]) >= 1:
            return {"error": "该授权卡已绑定其他群组，每张卡仅可授权一次"}
        stored_scope_id = str(existing[0]) if existing else scope_id
        self._connection.execute(
            """
            INSERT INTO group_authorizations(scope_id, card_code, expires_at, enabled, created_at)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(scope_id) DO UPDATE SET card_code=excluded.card_code,
                expires_at=excluded.expires_at, enabled=1, created_at=excluded.created_at
            """,
            (stored_scope_id, card_code, int(card[1]), self._now()),
        )
        self._connection.execute(
            "UPDATE access_cards SET used_count=used_count+1 WHERE card_code=?",
            (card_code,),
        )
        return {"scope_id": stored_scope_id, "card_code": card_code, "expires_at": int(card[1]), "already_authorized": False}

    def claim_group_authorization(self, scope_id: str, card_code: str) -> dict[str, Any] | None:
        """Authorize one official group. Every card can be consumed by one group only."""

        scope_id = str(scope_id or "").strip()
        card_code = str(card_code or "").strip().upper()
        if not scope_id or not card_code:
            return None
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                result = self._claim_group_authorization_locked(scope_id, card_code)
                if not result or result.get("error"):
                    self._connection.execute("ROLLBACK")
                    return result
                self._connection.execute("COMMIT")
                return result
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def group_authorized(self, scope_id: str) -> bool:
        with self._lock:
            aliases = self._group_scope_aliases_locked(scope_id)
            placeholders = ",".join("?" for _ in aliases)
            now = int(time.time())
            row = self._connection.execute(
                f"""
                SELECT 1 FROM group_authorizations g
                JOIN access_cards c ON c.card_code=g.card_code
                WHERE g.scope_id IN ({placeholders}) AND g.enabled=1 AND c.enabled=1
                  AND (g.expires_at=0 OR g.expires_at>?)
                  AND (c.expires_at=0 OR c.expires_at>?)
                LIMIT 1
                """,
                (*aliases, now, now),
            ).fetchone()
            return row is not None

    def group_authorization_status(self, scope_id: str) -> dict[str, Any] | None:
        with self._lock:
            canonical_scope_id = self._canonical_group_scope_locked(scope_id)
            aliases = self._group_scope_aliases_locked(canonical_scope_id)
            placeholders = ",".join("?" for _ in aliases)
            row = self._connection.execute(
                f"""
                SELECT g.scope_id, g.card_code, g.expires_at, g.enabled, g.created_at, c.enabled, c.expires_at
                FROM group_authorizations g
                JOIN access_cards c ON c.card_code=g.card_code
                WHERE g.scope_id IN ({placeholders})
                ORDER BY CASE WHEN g.scope_id=? THEN 0 ELSE 1 END
                LIMIT 1
                """,
                (*aliases, canonical_scope_id),
            ).fetchone()
        if not row:
            return None
        active = bool(row[3] and row[5] and (not int(row[2]) or int(row[2]) > int(time.time())) and (not int(row[6]) or int(row[6]) > int(time.time())))
        return {"scope_id": str(row[0]), "card_code": str(row[1]), "expires_at": int(row[2]), "enabled": active, "created_at": str(row[4])}

    def list_group_authorizations(self) -> list[dict[str, Any]]:
        with self._lock, closing(self._connection.execute(
            """
            SELECT g.scope_id, g.card_code, g.expires_at, g.enabled, g.created_at,
                COALESCE(b.numeric_group_id, '')
            FROM group_authorizations g
            LEFT JOIN official_group_bindings b ON b.group_openid=g.scope_id
            ORDER BY g.created_at DESC
            """
        )) as cursor:
            return [
                {
                    "scope_id": str(row[0]), "card_code": str(row[1]),
                    "expires_at": int(row[2]), "enabled": bool(row[3]),
                    "created_at": str(row[4]), "numeric_group_id": str(row[5] or ""),
                }
                for row in cursor.fetchall()
            ]

    def delete_group_authorization(self, scope_id: str) -> bool:
        """Revoke a group's authorization without making its consumed card reusable."""

        normalized_scope = str(scope_id or "").strip()
        if not normalized_scope:
            return False
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                aliases = self._group_scope_aliases_locked(normalized_scope)
                placeholders = ",".join("?" for _ in aliases)
                cursor = self._connection.execute(
                    f"DELETE FROM group_authorizations WHERE scope_id IN ({placeholders})",
                    tuple(aliases),
                )
                self._connection.execute(
                    f"DELETE FROM dashboard_user_groups WHERE scope_id IN ({placeholders})",
                    tuple(aliases),
                )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
            return cursor.rowcount > 0

    def bind_group_authorization(self, user_id: int, scope_id: str, card_code: str = "") -> dict[str, Any] | None:
        """Attach a verified dashboard user to an already authorized official group."""

        scope_id = str(scope_id or "").strip()
        card_code = str(card_code or "").strip().upper()
        if not user_id or not scope_id or not card_code:
            return {"error": "请填写授权卡密和目标 QQ 群号"}
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                user = self._connection.execute(
                    "SELECT role, email_verified FROM dashboard_users WHERE user_id=? AND enabled=1",
                    (int(user_id),),
                ).fetchone()
                if not user or str(user[0]) != "group" or not bool(user[1]):
                    self._connection.execute("ROLLBACK")
                    return {"error": "账号未完成邮箱验证或已被停用"}
                owner = self._connection.execute(
                    "SELECT user_id FROM dashboard_user_groups WHERE scope_id=?", (scope_id,)
                ).fetchone()
                if owner and int(owner[0]) != int(user_id):
                    self._connection.execute("ROLLBACK")
                    return {"error": "该官方群已绑定其他分群账号"}
                legacy = self._connection.execute(
                    "SELECT card_code FROM dashboard_user_licenses WHERE user_id=?",
                    (int(user_id),),
                ).fetchone()
                group_existing = self._connection.execute(
                    "SELECT card_code FROM group_authorizations WHERE scope_id=?",
                    (scope_id,),
                ).fetchone()
                if legacy and str(legacy[0]) == card_code:
                    if not group_existing:
                        self._connection.execute(
                            "UPDATE access_cards SET used_count=MAX(0, used_count-1) WHERE card_code=?",
                            (card_code,),
                        )
                    self._connection.execute("DELETE FROM dashboard_user_licenses WHERE user_id=?", (int(user_id),))
                group_result = self._claim_group_authorization_locked(scope_id, card_code)
                if not group_result or group_result.get("error"):
                    self._connection.execute("ROLLBACK")
                    return group_result
                current = self._connection.execute(
                    "SELECT 1 FROM dashboard_user_groups WHERE user_id=? AND scope_id=?",
                    (int(user_id), scope_id),
                ).fetchone()
                if current:
                    self._connection.execute(
                        "UPDATE dashboard_user_groups SET card_code=? WHERE user_id=? AND scope_id=?",
                        (card_code, int(user_id), scope_id),
                    )
                else:
                    self._connection.execute(
                        "INSERT INTO dashboard_user_groups(user_id, scope_id, card_code, created_at) VALUES (?, ?, ?, ?)",
                        (int(user_id), scope_id, card_code, self._now()),
                    )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return {"scope_id": scope_id, "already_bound": bool(current), "expires_at": group_result["expires_at"], "message": "官方群已授权并绑定，可开始配置功能"}

    def list_dashboard_user_groups(self, user_id: int, *, include_inactive: bool = True) -> list[dict[str, Any]]:
        with self._lock, closing(self._connection.execute(
            "SELECT scope_id, card_code, created_at FROM dashboard_user_groups WHERE user_id=? ORDER BY created_at DESC",
            (int(user_id),),
        )) as cursor:
            rows = cursor.fetchall()
        known = {str(item["scope_id"]): item for item in self.list_scopes()}
        result: list[dict[str, Any]] = []
        for row in rows:
            scope_id = str(row[0])
            item = dict(known.get(scope_id, {"scope_id": scope_id, "numeric_group_id": "", "server_id": "", "message_count": 0, "reply_count": 0, "auto_reply_enabled": True, "message_recording_enabled": True, "admin_count": 0}))
            status = self.group_authorization_status(scope_id)
            item["bound_at"] = str(row[2])
            item["authorization_active"] = bool(status and status["enabled"])
            item["authorization_expires_at"] = int(status["expires_at"]) if status else 0
            item["authorization_status"] = "已授权" if item["authorization_active"] else ("已过期" if status else "待授权")
            item["authorization_card_bound"] = bool(str(row[1] or "").strip())
            if not include_inactive and not item["authorization_active"]:
                continue
            result.append(item)
        return result

    def dashboard_user_manages_scope(self, user_id: int, scope_id: str) -> bool:
        with self._lock:
            aliases = self._group_scope_aliases_locked(scope_id)
            placeholders = ",".join("?" for _ in aliases)
            now = int(time.time())
            row = self._connection.execute(
                f"""
                SELECT 1 FROM dashboard_user_groups u
                JOIN group_authorizations g ON g.scope_id=u.scope_id
                JOIN access_cards c ON c.card_code=g.card_code
                WHERE u.user_id=? AND u.scope_id IN ({placeholders})
                  AND g.enabled=1 AND c.enabled=1
                  AND (g.expires_at=0 OR g.expires_at>?)
                  AND (c.expires_at=0 OR c.expires_at>?)
                LIMIT 1
                """,
                (int(user_id), *aliases, now, now),
            ).fetchone()
            return row is not None

    def set_dashboard_user_password(self, user_id: int, password: str) -> bool:
        if len(str(password or "")) < 6:
            return False
        with self._lock:
            cursor = self._connection.execute(
                "UPDATE dashboard_users SET password_hash=? WHERE user_id=? AND role <> 'admin'",
                (self._password_hash(str(password)), int(user_id)),
            )
            return cursor.rowcount > 0

    def set_dashboard_user_enabled(self, user_id: int, enabled: bool) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "UPDATE dashboard_users SET enabled=? WHERE user_id=? AND role <> 'admin'",
                (1 if enabled else 0, int(user_id)),
            )
            return cursor.rowcount > 0

    def update_dashboard_user_by_admin(
        self,
        user_id: int,
        *,
        username: str | None = None,
        email: str | None = None,
        display_name: str | None = None,
        password: str = "",
        enabled: bool | None = None,
    ) -> bool:
        changes: list[str] = []
        values: list[Any] = []
        if username is not None:
            username = str(username).strip()
            if len(username) < 3:
                return False
            changes.append("username=?")
            values.append(username)
        if email is not None:
            email = str(email).strip().lower()
            if email and "@" not in email:
                return False
            changes.extend(("email=?", "email_verified=?"))
            values.extend((email, 1 if email else 0))
        if display_name is not None:
            changes.append("display_name=?")
            values.append(str(display_name).strip()[:80])
        if password:
            if len(str(password)) < 6:
                return False
            changes.append("password_hash=?")
            values.append(self._password_hash(str(password)))
        if enabled is not None:
            changes.append("enabled=?")
            values.append(1 if enabled else 0)
        if not changes:
            return False
        values.append(int(user_id))
        with self._lock:
            try:
                cursor = self._connection.execute(
                    f"UPDATE dashboard_users SET {', '.join(changes)} WHERE user_id=? AND role <> 'admin'",
                    values,
                )
            except sqlite3.IntegrityError:
                return False
            return cursor.rowcount > 0

    def reset_dashboard_user_password_from_email(
        self, user_id: int, email: str, verification_code: str, password: str
    ) -> bool:
        email = str(email or "").strip().lower()
        if len(str(password or "")) < 6 or not email or not verification_code:
            return False
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                row = self._connection.execute(
                    "SELECT email FROM dashboard_users WHERE user_id=? AND role='group' AND enabled=1",
                    (int(user_id),),
                ).fetchone()
                if not row or str(row[0]).lower() != email or not self._registration_email_code_valid(email, verification_code):
                    self._connection.execute("ROLLBACK")
                    return False
                self._connection.execute(
                    "UPDATE dashboard_users SET password_hash=? WHERE user_id=?",
                    (self._password_hash(str(password)), int(user_id)),
                )
                self._connection.execute("DELETE FROM dashboard_email_verifications WHERE email=?", (email,))
                self._connection.execute("COMMIT")
                return True
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def claim_bot_authorization(self, user_openid: str, card_code: str) -> dict[str, Any] | None:
        user_openid = str(user_openid or "").strip()
        card_code = str(card_code or "").strip().upper()
        if not user_openid or not card_code:
            return None
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                row = self._connection.execute(
                    "SELECT kind, scope_id, max_uses, bot_used_count, expires_at, enabled FROM access_cards WHERE card_code=? AND kind IN ('bot', 'license', 'portal', 'group')",
                    (card_code,),
                ).fetchone()
                if not row or not row[5] or (row[4] and int(row[4]) <= int(time.time())):
                    self._connection.execute("ROLLBACK")
                    return None
                previous = self._connection.execute(
                    "SELECT card_code, enabled, expires_at FROM bot_authorizations WHERE user_openid=?",
                    (user_openid,),
                ).fetchone()
                if previous and str(previous[0]) == card_code and bool(previous[1]) and (not int(previous[2]) or int(previous[2]) > int(time.time())):
                    self._connection.execute("COMMIT")
                    return {"user_openid": user_openid, "scope_id": str(row[1]), "expires_at": int(row[4]), "already_authorized": True}
                if int(row[3]) >= int(row[2]):
                    self._connection.execute("ROLLBACK")
                    return None
                if previous and str(previous[0]) != card_code:
                    self._connection.execute(
                        "UPDATE access_cards SET bot_used_count=MAX(0, bot_used_count-1) WHERE card_code=?",
                        (str(previous[0]),),
                    )
                self._connection.execute(
                    """
                    INSERT INTO bot_authorizations(user_openid, scope_id, card_code, expires_at, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_openid) DO UPDATE SET scope_id=excluded.scope_id,
                        card_code=excluded.card_code, expires_at=excluded.expires_at, enabled=1
                    """,
                    (user_openid, str(row[1]), card_code, int(row[4]), self._now()),
                )
                self._connection.execute("UPDATE access_cards SET bot_used_count=bot_used_count+1 WHERE card_code=?", (card_code,))
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return {"user_openid": user_openid, "scope_id": str(row[1]), "expires_at": int(row[4])}

    def bot_user_authorized(self, user_openid: str, scope_id: str) -> bool:
        with self._lock, closing(self._connection.execute(
            """
            SELECT 1 FROM bot_authorizations
            WHERE user_openid=? AND enabled=1 AND (expires_at=0 OR expires_at>?)
              AND (scope_id='' OR scope_id=?)
            """,
            (str(user_openid), int(time.time()), str(scope_id)),
        )) as cursor:
            return cursor.fetchone() is not None

    def bot_authorization_status(self, user_openid: str, scope_id: str = "") -> dict[str, Any] | None:
        with self._lock, closing(self._connection.execute(
            """
            SELECT user_openid, scope_id, expires_at, enabled, created_at
            FROM bot_authorizations WHERE user_openid=? AND enabled=1
              AND (expires_at=0 OR expires_at>?) AND (scope_id='' OR scope_id=? OR ?='')
            ORDER BY CASE WHEN scope_id=? THEN 0 ELSE 1 END LIMIT 1
            """,
            (str(user_openid), int(time.time()), str(scope_id), str(scope_id), str(scope_id)),
        )) as cursor:
            row = cursor.fetchone()
        if not row:
            return None
        return {"user_openid": str(row[0]), "scope_id": str(row[1]), "expires_at": int(row[2]), "enabled": bool(row[3]), "created_at": str(row[4])}

    def _group_scope_aliases_locked(self, scope_id: str) -> tuple[str, ...]:
        candidate = str(scope_id or "").strip()
        if not candidate:
            return ("",)
        aliases = [candidate]
        rows = self._connection.execute(
            """
            SELECT group_openid, numeric_group_id
            FROM official_group_bindings
            WHERE group_openid=? OR numeric_group_id=?
            """,
            (candidate, candidate),
        ).fetchall()
        for row in rows:
            for value in (row[0], row[1]):
                normalized = str(value or "").strip()
                if normalized and normalized not in aliases:
                    aliases.append(normalized)
        return tuple(aliases)

    def _canonical_group_scope_locked(self, scope_id: str) -> str:
        candidate = str(scope_id or "").strip()
        if not candidate:
            return ""
        row = self._connection.execute(
            "SELECT group_openid FROM official_group_bindings WHERE group_openid=? LIMIT 1",
            (candidate,),
        ).fetchone()
        if row:
            return str(row[0]).strip()
        row = self._connection.execute(
            "SELECT group_openid FROM official_group_bindings WHERE numeric_group_id=? LIMIT 1",
            (candidate,),
        ).fetchone()
        return str(row[0]).strip() if row else candidate

    def resolve_group_scope(self, scope_id: str) -> str:
        """Return the official group OpenID for a numeric group alias when known."""

        with self._lock:
            return self._canonical_group_scope_locked(scope_id)

    def list_bot_authorizations(self) -> list[dict[str, Any]]:
        with self._lock, closing(self._connection.execute(
            "SELECT user_openid, scope_id, card_code, expires_at, enabled, created_at FROM bot_authorizations ORDER BY created_at DESC"
        )) as cursor:
            return [
                {"user_openid": str(row[0]), "scope_id": str(row[1]), "card_code": str(row[2]), "expires_at": int(row[3]), "enabled": bool(row[4]), "created_at": str(row[5])}
                for row in cursor.fetchall()
            ]

    def revoke_bot_authorization(self, user_openid: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "UPDATE bot_authorizations SET enabled=0 WHERE user_openid=?", (str(user_openid).strip(),)
            )
            return cursor.rowcount > 0

    def list_dashboard_users(self) -> list[dict[str, Any]]:
        with self._lock, closing(self._connection.execute(
            "SELECT user_id, username, email, display_name, role, scope_id, enabled, email_verified, created_at FROM dashboard_users ORDER BY created_at DESC"
        )) as cursor:
            return [
                {"user_id": int(row[0]), "username": str(row[1]), "email": str(row[2] or ""), "display_name": str(row[3] or ""), "role": str(row[4]), "scope_id": str(row[5]), "enabled": bool(row[6]), "email_verified": bool(row[7]), "created_at": str(row[8])}
                for row in cursor.fetchall()
            ]

    def update_dashboard_user_profile(
        self, user_id: int, email: str, display_name: str = ""
    ) -> bool:
        email = str(email or "").strip().lower()
        display_name = str(display_name or "").strip()[:80]
        with self._lock:
            try:
                cursor = self._connection.execute(
                    "UPDATE dashboard_users SET email=?, display_name=?, email_verified=? WHERE user_id=?",
                    (email, display_name, 1 if email else 0, int(user_id)),
                )
            except sqlite3.IntegrityError:
                return False
            return cursor.rowcount > 0

    def get_setting(self, scope_id: str, key: str, default: str = "") -> str:
        with self._lock, closing(self._connection.execute(
            "SELECT setting_value FROM settings WHERE scope_id=? AND setting_key=?",
            (scope_id, key),
        )) as cursor:
            row = cursor.fetchone()
        return str(row[0]) if row else default

    def feature_enabled(self, scope_id: str, feature_key: str, default: bool = True) -> bool:
        fallback = "1" if default else "0"
        return self.get_setting(scope_id, f"feature:{feature_key}", fallback) == "1"

    def set_feature_enabled(self, scope_id: str, feature_key: str, enabled: bool) -> None:
        self.set_setting(scope_id, f"feature:{feature_key}", "1" if enabled else "0")

    def feature_settings(self, scope_id: str, feature_keys: list[str]) -> dict[str, bool]:
        return {key: self.feature_enabled(scope_id, key) for key in feature_keys}

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

    def get_bot_owner_openid(self, default: str = "") -> str:
        return self.get_setting("__global__", "bot_owner_openid", default).strip()

    def set_bot_owner_openid(self, owner_openid: str) -> None:
        self.set_setting("__global__", "bot_owner_openid", str(owner_openid or "").strip())

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

    def record_message_content(
        self,
        scope_id: str,
        message_id: str,
        user_id: str,
        content: str,
    ) -> None:
        if not message_id:
            return
        with self._lock:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO message_records(scope_id, message_id, user_id, content, recalled, created_at)
                VALUES (?, ?, ?, '', 0, ?)
                """,
                (scope_id, message_id, user_id, self._now()),
            )

    def list_message_records(self, scope_id: str, limit: int = 100) -> list[dict[str, str]]:
        with self._lock, closing(self._connection.execute(
            """
            SELECT message_id, user_id, recalled, created_at
            FROM message_records WHERE scope_id=? ORDER BY created_at DESC LIMIT ?
            """,
            (scope_id, max(1, min(limit, 500))),
        )) as cursor:
            return [
                {
                    "message_id": str(row[0]),
                    "user_id": str(row[1]),
                    "recalled": bool(row[2]),
                    "created_at": str(row[3]),
                }
                for row in cursor.fetchall()
            ]

    def list_user_message_records(
        self, scope_id: str, user_id: str, limit: int = 20
    ) -> list[dict[str, str]]:
        with self._lock, closing(self._connection.execute(
            """
            SELECT message_id, user_id, recalled, created_at
            FROM message_records
            WHERE scope_id=? AND user_id=? AND recalled=0
            ORDER BY created_at DESC LIMIT ?
            """,
            (scope_id, user_id, max(1, min(limit, 100))),
        )) as cursor:
            return [
                {
                    "message_id": str(row[0]),
                    "user_id": str(row[1]),
                    "recalled": bool(row[2]),
                    "created_at": str(row[3]),
                }
                for row in cursor.fetchall()
            ]

    def mark_message_recalled(self, scope_id: str, message_id: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "UPDATE message_records SET recalled=1 WHERE scope_id=? AND message_id=?",
                (str(scope_id), str(message_id)),
            )
            return cursor.rowcount > 0

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

    def list_message_users(self, scope_id: str, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock, closing(self._connection.execute(
            """
            SELECT user_id, messages, last_seen
            FROM message_stats WHERE scope_id=?
            ORDER BY last_seen DESC, messages DESC LIMIT ?
            """,
            (scope_id, max(1, min(int(limit), 500))),
        )) as cursor:
            return [
                {
                    "user_id": str(row[0]),
                    "messages": int(row[1]),
                    "last_seen": str(row[2]),
                }
                for row in cursor.fetchall()
            ]

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

    @staticmethod
    def _reply_match_mode(match_mode: str) -> str:
        return "fuzzy" if str(match_mode).strip().lower() == "fuzzy" else "exact"

    def save_reply(self, scope_id: str, trigger: str, response: str, match_mode: str = "exact") -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO replies(scope_id, trigger, response, match_mode, enabled, updated_at)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(scope_id, trigger) DO UPDATE SET
                    response=excluded.response, match_mode=excluded.match_mode, enabled=1, updated_at=excluded.updated_at
                """,
                (scope_id, trigger, response, self._reply_match_mode(match_mode), self._now()),
            )

    def delete_reply(self, scope_id: str, trigger: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM replies WHERE scope_id=? AND trigger=?",
                (scope_id, trigger),
            )
            return cursor.rowcount > 0

    def list_replies(self, scope_id: str) -> list[tuple[str, str, bool, str]]:
        with self._lock, closing(self._connection.execute(
            "SELECT trigger, response, enabled, match_mode FROM replies WHERE scope_id=? ORDER BY trigger",
            (scope_id,),
        )) as cursor:
            return [(str(row[0]), str(row[1]), bool(row[2]), self._reply_match_mode(str(row[3]))) for row in cursor.fetchall()]

    def find_reply(self, scope_id: str, trigger: str) -> str | None:
        with self._lock, closing(self._connection.execute(
            "SELECT response FROM replies WHERE scope_id=? AND trigger=? AND enabled=1 AND match_mode='exact'",
            (scope_id, trigger),
        )) as cursor:
            row = cursor.fetchone()
        if row:
            return str(row[0])
        with self._lock, closing(self._connection.execute(
            """
            SELECT response FROM replies
            WHERE scope_id=? AND enabled=1 AND match_mode='fuzzy' AND ? LIKE '%' || trigger || '%'
            ORDER BY LENGTH(trigger) DESC, updated_at DESC LIMIT 1
            """,
            (scope_id, trigger),
        )) as cursor:
            row = cursor.fetchone()
        return str(row[0]) if row else None

    def save_user_reply(
        self, scope_id: str, user_id: str, trigger: str, response: str, match_mode: str = "exact"
    ) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO user_replies(scope_id, user_id, trigger, response, match_mode, enabled, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(scope_id, user_id, trigger) DO UPDATE SET
                    response=excluded.response, match_mode=excluded.match_mode, enabled=1, updated_at=excluded.updated_at
                """,
                (scope_id, user_id, trigger, response, self._reply_match_mode(match_mode), self._now()),
            )

    def delete_user_reply(self, scope_id: str, user_id: str, trigger: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM user_replies WHERE scope_id=? AND user_id=? AND trigger=?",
                (scope_id, user_id, trigger),
            )
            return cursor.rowcount > 0

    def find_user_reply(self, scope_id: str, user_id: str, trigger: str) -> str | None:
        with self._lock, closing(self._connection.execute(
            """
            SELECT response FROM user_replies
            WHERE scope_id=? AND user_id=? AND trigger=? AND enabled=1 AND match_mode='exact'
            """,
            (scope_id, user_id, trigger),
        )) as cursor:
            row = cursor.fetchone()
        if row:
            return str(row[0])
        with self._lock, closing(self._connection.execute(
            """
            SELECT response FROM user_replies
            WHERE scope_id=? AND user_id=? AND enabled=1 AND match_mode='fuzzy'
              AND ? LIKE '%' || trigger || '%'
            ORDER BY LENGTH(trigger) DESC, updated_at DESC LIMIT 1
            """,
            (scope_id, user_id, trigger),
        )) as cursor:
            row = cursor.fetchone()
        return str(row[0]) if row else None

    def list_user_replies(self, scope_id: str, user_id: str = "") -> list[dict[str, str]]:
        query = "SELECT user_id, trigger, response, enabled, match_mode FROM user_replies WHERE scope_id=?"
        params: list[Any] = [scope_id]
        if user_id:
            query += " AND user_id=?"
            params.append(user_id)
        query += " ORDER BY user_id, trigger"
        with self._lock, closing(self._connection.execute(query, params)) as cursor:
            return [
                {
                    "user_id": str(row[0]),
                    "trigger": str(row[1]),
                    "response": str(row[2]),
                    "enabled": "1" if row[3] else "0",
                    "match_mode": self._reply_match_mode(str(row[4])),
                }
                for row in cursor.fetchall()
            ]

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

    def find_official_group_openid(self, numeric_group_id: str) -> str | None:
        """Resolve a user-facing numeric QQ group number to the official group openid."""

        numeric_group_id = str(numeric_group_id or "").strip()
        if not numeric_group_id:
            return None
        with self._lock, closing(self._connection.execute(
            "SELECT group_openid FROM official_group_bindings WHERE numeric_group_id=?",
            (numeric_group_id,),
        )) as cursor:
            row = cursor.fetchone()
        return str(row[0]) if row else None

    def list_scopes(self) -> list[dict[str, Any]]:
        with self._lock:
            scope_ids: set[str] = set()
            for table, column in (
                ("message_stats", "scope_id"),
                ("settings", "scope_id"),
                ("replies", "scope_id"),
                ("user_replies", "scope_id"),
                ("server_bindings", "scope_id"),
                ("official_group_bindings", "group_openid"),
                ("lotteries", "scope_id"),
                ("blacklist", "scope_id"),
                ("message_records", "scope_id"),
                ("group_admins", "scope_id"),
                ("scheduled_messages", "scope_id"),
                ("dashboard_user_groups", "scope_id"),
            ):
                rows = self._connection.execute(
                    f"SELECT DISTINCT {column} FROM {table} WHERE {column} <> ''"
                ).fetchall()
                scope_ids.update(str(row[0]) for row in rows)

            result: list[dict[str, Any]] = []
            for scope_id in sorted(scope_ids):
                group_binding = self._connection.execute(
                    "SELECT numeric_group_id FROM official_group_bindings WHERE group_openid=?",
                    (scope_id,),
                ).fetchone()
                server_binding = self._connection.execute(
                    "SELECT server_id FROM server_bindings WHERE scope_id=?",
                    (scope_id,),
                ).fetchone()
                message_count = self._connection.execute(
                    "SELECT COALESCE(SUM(messages), 0) FROM message_stats WHERE scope_id=?",
                    (scope_id,),
                ).fetchone()[0]
                reply_count = self._connection.execute(
                    "SELECT COUNT(*) FROM replies WHERE scope_id=?",
                    (scope_id,),
                ).fetchone()[0]
                result.append(
                    {
                        "scope_id": scope_id,
                        "numeric_group_id": str(group_binding[0]) if group_binding else "",
                        "server_id": str(server_binding[0]) if server_binding else "",
                        "message_count": int(message_count or 0),
                        "reply_count": int(reply_count or 0),
                        "auto_reply_enabled": self.get_setting(scope_id, "auto_reply_enabled", "1") == "1",
                        "message_recording_enabled": self.feature_enabled(scope_id, "message_records"),
                        "admin_count": self._count_rows("group_admins", scope_id),
                    }
                )
            return result

    def _count_rows(self, table: str, scope_id: str) -> int:
        with closing(self._connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE scope_id=?", (scope_id,)
        )) as cursor:
            return int(cursor.fetchone()[0] or 0)

    def add_group_admin(self, scope_id: str, user_id: str, display_name: str = "") -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO group_admins(scope_id, user_id, display_name, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(scope_id, user_id) DO UPDATE SET display_name=excluded.display_name
                """,
                (scope_id, user_id, display_name or user_id, self._now()),
            )

    def remove_group_admin(self, scope_id: str, user_id: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM group_admins WHERE scope_id=? AND user_id=?",
                (scope_id, user_id),
            )
            return cursor.rowcount > 0

    def is_group_admin(self, scope_id: str, user_id: str) -> bool:
        with self._lock, closing(self._connection.execute(
            "SELECT 1 FROM group_admins WHERE scope_id=? AND user_id=?",
            (scope_id, user_id),
        )) as cursor:
            return cursor.fetchone() is not None

    def list_group_admins(self, scope_id: str) -> list[dict[str, str]]:
        with self._lock, closing(self._connection.execute(
            "SELECT user_id, display_name, created_at FROM group_admins WHERE scope_id=? ORDER BY created_at",
            (scope_id,),
        )) as cursor:
            return [
                {"user_id": str(row[0]), "display_name": str(row[1]), "created_at": str(row[2])}
                for row in cursor.fetchall()
            ]

    def create_scheduled_message(self, scope_id: str, content: str, interval_seconds: int) -> int:
        interval = max(60, min(int(interval_seconds), 31_536_000))
        now = int(datetime.now(timezone.utc).timestamp())
        with self._lock:
            cursor = self._connection.execute(
                """
                INSERT INTO scheduled_messages(scope_id, content, interval_seconds, next_run_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (scope_id, str(content or "")[:4000], interval, now + interval, self._now()),
            )
            return int(cursor.lastrowid)

    def list_scheduled_messages(self, scope_id: str = "") -> list[dict[str, Any]]:
        query = "SELECT schedule_id, scope_id, content, interval_seconds, next_run_at, enabled, last_error FROM scheduled_messages"
        params: list[Any] = []
        if scope_id:
            query += " WHERE scope_id=?"
            params.append(scope_id)
        query += " ORDER BY schedule_id DESC"
        with self._lock, closing(self._connection.execute(query, params)) as cursor:
            return [
                {
                    "schedule_id": int(row[0]),
                    "scope_id": str(row[1]),
                    "content": str(row[2]),
                    "interval_seconds": int(row[3]),
                    "next_run_at": int(row[4]),
                    "enabled": bool(row[5]),
                    "last_error": str(row[6]),
                }
                for row in cursor.fetchall()
            ]

    def due_scheduled_messages(self, now: int | None = None) -> list[dict[str, Any]]:
        current = int(now if now is not None else datetime.now(timezone.utc).timestamp())
        with self._lock, closing(self._connection.execute(
            """
            SELECT schedule_id, scope_id, content, interval_seconds
            FROM scheduled_messages WHERE enabled=1 AND next_run_at<=?
            ORDER BY next_run_at LIMIT 50
            """,
            (current,),
        )) as cursor:
            return [
                {
                    "schedule_id": int(row[0]),
                    "scope_id": str(row[1]),
                    "content": str(row[2]),
                    "interval_seconds": int(row[3]),
                }
                for row in cursor.fetchall()
            ]

    def create_scheduled_task(
        self,
        scope_id: str,
        task_type: str,
        run_at: int,
        *,
        content: str = "",
        mute_seconds: int = 0,
    ) -> int:
        task_type = str(task_type or "").strip().lower()
        if task_type not in {"broadcast", "mute_all", "unmute_all", "song"}:
            raise ValueError("invalid task type")
        if task_type in {"broadcast", "song"} and not str(content).strip():
            raise ValueError("content is required")
        now = int(time.time())
        run_at = int(run_at)
        if run_at < now - 60:
            raise ValueError("run_at is in the past")
        mute_seconds = max(0, min(int(mute_seconds or 0), 2_592_000))
        with self._lock:
            cursor = self._connection.execute(
                """
                INSERT INTO scheduled_tasks(scope_id, task_type, content, run_at, mute_seconds, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(scope_id), task_type, str(content).strip()[:4000], run_at, mute_seconds, self._now()),
            )
            return int(cursor.lastrowid)

    def list_scheduled_tasks(self, scope_id: str = "") -> list[dict[str, Any]]:
        query = """
            SELECT task_id, scope_id, task_type, content, run_at, mute_seconds, enabled, completed_at, last_error
            FROM scheduled_tasks
        """
        params: list[Any] = []
        if scope_id:
            query += " WHERE scope_id=?"
            params.append(str(scope_id))
        query += " ORDER BY run_at DESC, task_id DESC"
        with self._lock, closing(self._connection.execute(query, params)) as cursor:
            return [
                {
                    "task_id": int(row[0]),
                    "scope_id": str(row[1]),
                    "task_type": str(row[2]),
                    "content": str(row[3]),
                    "run_at": int(row[4]),
                    "mute_seconds": int(row[5]),
                    "enabled": bool(row[6]),
                    "completed_at": str(row[7]),
                    "last_error": str(row[8]),
                }
                for row in cursor.fetchall()
            ]

    def due_scheduled_tasks(self, now: int | None = None) -> list[dict[str, Any]]:
        current = int(now if now is not None else time.time())
        with self._lock, closing(self._connection.execute(
            """
            SELECT task_id, scope_id, task_type, content, run_at, mute_seconds
            FROM scheduled_tasks
            WHERE enabled=1 AND completed_at='' AND run_at<=?
            ORDER BY run_at, task_id LIMIT 50
            """,
            (current,),
        )) as cursor:
            return [
                {
                    "task_id": int(row[0]),
                    "scope_id": str(row[1]),
                    "task_type": str(row[2]),
                    "content": str(row[3]),
                    "run_at": int(row[4]),
                    "mute_seconds": int(row[5]),
                }
                for row in cursor.fetchall()
            ]

    def complete_scheduled_task(self, task_id: int, *, error: str = "") -> None:
        with self._lock:
            self._connection.execute(
                """
                UPDATE scheduled_tasks
                SET enabled=0, completed_at=?, last_error=?
                WHERE task_id=?
                """,
                (self._now() if not error else "", str(error)[:500], int(task_id)),
            )

    def delete_scheduled_task(self, task_id: int, scope_id: str = "") -> bool:
        with self._lock:
            if scope_id:
                cursor = self._connection.execute(
                    "DELETE FROM scheduled_tasks WHERE task_id=? AND scope_id=?",
                    (int(task_id), str(scope_id)),
                )
            else:
                cursor = self._connection.execute("DELETE FROM scheduled_tasks WHERE task_id=?", (int(task_id),))
            return cursor.rowcount > 0

    def advance_scheduled_message(self, schedule_id: int, *, error: str = "") -> None:
        now = datetime.now(timezone.utc)
        with self._lock:
            self._connection.execute(
                """
                UPDATE scheduled_messages
                SET next_run_at = CAST(strftime('%s', 'now') AS INTEGER) + interval_seconds,
                    last_sent_at=?, last_error=?
                WHERE schedule_id=?
                """,
                (now.isoformat(timespec="seconds") if not error else "", error[:500], schedule_id),
            )

    def delete_scheduled_message(self, schedule_id: int, scope_id: str = "") -> bool:
        with self._lock:
            if scope_id:
                cursor = self._connection.execute(
                    "DELETE FROM scheduled_messages WHERE schedule_id=? AND scope_id=?",
                    (schedule_id, scope_id),
                )
            else:
                cursor = self._connection.execute(
                    "DELETE FROM scheduled_messages WHERE schedule_id=?", (schedule_id,)
                )
            return cursor.rowcount > 0

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

    def list_keyword_rules(self, scope_id: str, action: str = "") -> list[dict[str, Any]]:
        query = """
            SELECT rule_id, action, trigger, duration_seconds, duration_minutes,
                   enabled, created_at, updated_at
            FROM keyword_rules WHERE scope_id=?
        """
        params: list[Any] = [scope_id]
        if action:
            query += " AND action=?"
            params.append(action)
        query += " ORDER BY action, rule_id"
        with self._lock, closing(self._connection.execute(query, params)) as cursor:
            return [
                {
                    "rule_id": int(row[0]),
                    "action": str(row[1]),
                    "trigger": str(row[2]),
                    "duration_seconds": max(1, int(row[3] or 0)),
                    "duration_minutes": max(1, int(row[4] or 0)),
                    "enabled": bool(row[5]),
                    "created_at": str(row[6]),
                    "updated_at": str(row[7]),
                }
                for row in cursor.fetchall()
            ]

    def save_keyword_rule(
        self, scope_id: str, action: str, trigger: str, duration_seconds: int = 600
    ) -> None:
        now = self._now()
        seconds = max(1, min(int(duration_seconds), 2_592_000))
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO keyword_rules(
                    scope_id, action, trigger, duration_minutes, duration_seconds,
                    enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(scope_id, action, trigger) DO UPDATE SET
                    duration_minutes=excluded.duration_minutes,
                    duration_seconds=excluded.duration_seconds,
                    enabled=1,
                    updated_at=excluded.updated_at
                """ ,
                (scope_id, action, trigger, max(1, seconds // 60), seconds, now, now),
            )

    def delete_keyword_rule(self, scope_id: str, rule_id: int) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM keyword_rules WHERE scope_id=? AND rule_id=?",
                (scope_id, int(rule_id)),
            )
            return cursor.rowcount > 0

