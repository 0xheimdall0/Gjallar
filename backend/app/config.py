import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    return default if value is None or value == "" else value

def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)

def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

@dataclass(frozen=True)
class Settings:
    database_path: Path
    max_payload: int
    retention_days: int
    debug: bool
    admin_token: str | None
    vapid_public_key: str | None
    vapid_private_key: str | None
    vapid_subject: str

def load_settings() -> Settings:
    raw_db_path = Path(_env_str("SIGNAL_DATABASE_PATH", "data/signal.db"))
    database_path = raw_db_path if raw_db_path.is_absolute() else BASE_DIR / raw_db_path
    return Settings(
        database_path=database_path,
        max_payload=_env_int("SIGNAL_MAX_PAYLOAD_BYTES", 64 * 1024),
        retention_days=_env_int("SIGNAL_RETENTION_DAYS", 90),
        debug=_env_bool("SIGNAL_DEBUG", False),
        admin_token=_env_str("SIGNAL_ADMIN_TOKEN", "") or None,
        vapid_public_key=_env_str("SIGNAL_VAPID_PUBLIC_KEY", "") or None,
        vapid_private_key=_env_str("SIGNAL_VAPID_PRIVATE_KEY", "") or None,
        vapid_subject=_env_str("SIGNAL_VAPID_SUBJECT", "mailto:admin@localhost"),
    )

settings = load_settings()