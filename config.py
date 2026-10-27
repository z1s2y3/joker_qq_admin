from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

DEFAULT_API_BASE_URL = "https://api.bot.qq.com"
DEFAULT_TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
DEFAULT_INTENTS = 1 << 25
DEFAULT_REQUEST_TIMEOUT = 20.0
DEFAULT_SCUM_RELAY_URL = "https://ba.yooyun.top"
DEFAULT_PORTAL_URL = "https://web.yooyun.top"
DEFAULT_ENV_FILE = "/etc/joker_qq_admin/joker_qq_admin.env"


class ConfigError(ValueError):
    """Raised when required official bot configuration is missing."""


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def env_file_path() -> Path:
    return Path(_env("JOKER_ENV_FILE", DEFAULT_ENV_FILE)).expanduser()


def read_env_file(path: str | Path | None = None) -> dict[str, str]:
    env_path = Path(path or env_file_path())
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if value[:1] == value[-1:] and value[:1] in {"'", '"'}:
            value = value[1:-1]
        values[name] = value
    return values


def write_env_file(updates: dict[str, str], path: str | Path | None = None) -> Path:
    env_path = Path(path or env_file_path())
    current = read_env_file(env_path)
    current.update(updates)
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{name}={value}" for name, value in sorted(current.items())]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(env_path, 0o600)
    return env_path


def load_env_file(path: str | Path | None = None) -> None:
    for name, value in read_env_file(path).items():
        os.environ[name] = value


def _float_env(name: str, default: float) -> float:
    value = _env(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc


def _int_env(name: str, default: int) -> int:
    value = _env(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc


def _path_env(name: str, default: str) -> str:
    value = _env(name, default) or default
    if not value.startswith("/") or "?" in value or "#" in value:
        raise ConfigError(f"{name} must be an absolute URL path")
    if len(value) > 1:
        value = "/" + value.strip("/")
    return value


@dataclass(frozen=True, slots=True)
class QQBotConfig:
    app_id: str
    app_secret: str
    api_base_url: str = DEFAULT_API_BASE_URL
    token_url: str = DEFAULT_TOKEN_URL
    gateway_url: str = ""
    transport: str = "websocket"
    intents: int = DEFAULT_INTENTS
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT
    reconnect_min: float = 1.0
    reconnect_max: float = 30.0
    data_dir: Path = Path("data")
    scum_relay_url: str = DEFAULT_SCUM_RELAY_URL
    scum_relay_key: str = ""
    owner_openid: str = ""
    admin_openids: tuple[str, ...] = ()
    game_bridge_url: str = ""
    game_bridge_token: str = ""
    portal_url: str = DEFAULT_PORTAL_URL
    dashboard_bind: str = "127.0.0.1"
    dashboard_port: int = 8080
    dashboard_token: str = ""
    dashboard_path: str = "/admin"
    admin_path: str = ""
    user_path: str = "/user"
    admin_username: str = "admin"
    admin_password: str = ""
    dashboard_session_max_age: int = 604800
    bot_authorization_required: bool = True
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    registration_require_email: bool = True

    @classmethod
    def from_env(cls) -> "QQBotConfig":
        app_id = _env("QQBOT_APP_ID")
        app_secret = _env("QQBOT_APP_SECRET")
        if not app_id or not app_secret:
            raise ConfigError("QQBOT_APP_ID and QQBOT_APP_SECRET are required")

        reconnect_min = _float_env("QQBOT_RECONNECT_MIN", 1.0)
        reconnect_max = _float_env("QQBOT_RECONNECT_MAX", 30.0)
        if reconnect_min <= 0 or reconnect_max < reconnect_min:
            raise ConfigError("QQBOT_RECONNECT_MAX must be >= QQBOT_RECONNECT_MIN > 0")

        dashboard_bind = _env("JOKER_DASHBOARD_BIND", "127.0.0.1")
        dashboard_token = _env("JOKER_DASHBOARD_TOKEN")
        legacy_dashboard_path = _path_env("JOKER_DASHBOARD_PATH", "/admin")
        if legacy_dashboard_path == "/":
            legacy_dashboard_path = "/admin"
        admin_path = _path_env("JOKER_ADMIN_PATH", legacy_dashboard_path)
        user_path = _path_env("JOKER_USER_PATH", "/user")
        if admin_path == "/" or user_path == "/" or admin_path == user_path:
            raise ConfigError("JOKER_ADMIN_PATH and JOKER_USER_PATH must be different non-root paths")
        transport = _env("QQBOT_TRANSPORT", "webhook").lower()
        if transport not in {"websocket", "webhook"}:
            raise ConfigError("QQBOT_TRANSPORT must be websocket or webhook")
        if dashboard_bind not in {"127.0.0.1", "localhost", "::1"} and not dashboard_token:
            raise ConfigError("JOKER_DASHBOARD_TOKEN is required when dashboard is not local-only")

        api_base_url = _env("QQBOT_API_BASE", DEFAULT_API_BASE_URL).rstrip("/")
        if api_base_url == "https://api.sgroup.qq.com":
            api_base_url = DEFAULT_API_BASE_URL

        return cls(
            app_id=app_id,
            app_secret=app_secret,
            api_base_url=api_base_url,
            token_url=_env("QQBOT_TOKEN_URL", DEFAULT_TOKEN_URL),
            gateway_url=_env("QQBOT_GATEWAY_URL"),
            transport=transport,
            intents=_int_env("QQBOT_INTENTS", DEFAULT_INTENTS),
            request_timeout=_float_env("QQBOT_REQUEST_TIMEOUT", DEFAULT_REQUEST_TIMEOUT),
            reconnect_min=reconnect_min,
            reconnect_max=reconnect_max,
            data_dir=Path(_env("JOKER_QQ_DATA_DIR", "data")).expanduser(),
            scum_relay_url=_env("SCUM_RELAY_URL", DEFAULT_SCUM_RELAY_URL).rstrip("/"),
            scum_relay_key=_env("SCUM_RELAY_KEY"),
            owner_openid=_env("QQBOT_OWNER_OPENID"),
            admin_openids=tuple(
                item.strip()
                for item in _env("QQBOT_ADMIN_OPENIDS").split(",")
                if item.strip()
            ),
            game_bridge_url=_env("JOKER_GAME_BRIDGE_URL").rstrip("/"),
            game_bridge_token=_env("JOKER_GAME_BRIDGE_TOKEN"),
            portal_url=_env("JOKER_PORTAL_URL", DEFAULT_PORTAL_URL).rstrip("/"),
            dashboard_bind=dashboard_bind,
            dashboard_port=_int_env("JOKER_DASHBOARD_PORT", 8080),
            dashboard_token=dashboard_token,
            dashboard_path=admin_path,
            admin_path=admin_path,
            user_path=user_path,
            admin_username=_env("JOKER_ADMIN_USERNAME", "admin"),
            admin_password=_env("JOKER_ADMIN_PASSWORD"),
            dashboard_session_max_age=_int_env("JOKER_DASHBOARD_SESSION_MAX_AGE", 604800),
            bot_authorization_required=_env("JOKER_BOT_AUTH_REQUIRED", "1") not in {"0", "false", "no"},
            smtp_host=_env("JOKER_SMTP_HOST"),
            smtp_port=_int_env("JOKER_SMTP_PORT", 587),
            smtp_username=_env("JOKER_SMTP_USERNAME"),
            smtp_password=_env("JOKER_SMTP_PASSWORD"),
            smtp_from=_env("JOKER_SMTP_FROM"),
            smtp_use_tls=_env("JOKER_SMTP_USE_TLS", "1") not in {"0", "false", "no"},
            registration_require_email=_env("JOKER_REGISTRATION_REQUIRE_EMAIL", "1") not in {"0", "false", "no"},
        )

