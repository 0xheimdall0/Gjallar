import contextlib
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Where secrets written at runtime by the setup wizard are stored.
# Overridable because in a container the default sits on the image filesystem,
# which is destroyed whenever the container is recreated — taking the admin
# token and the VAPID keys with it. Compose points this at the data volume.
ENV_PATH = Path(os.environ.get("SIGNAL_ENV_FILE") or (BASE_DIR / ".env"))

_overrides: dict[str, str] = {}

load_dotenv(ENV_PATH)

def _current(name: str) -> str | None:
    return _overrides.get(name) or os.environ.get(name) or None

def admin_token() -> str | None:
    return _current("SIGNAL_ADMIN_TOKEN")

def vapid_public_key() -> str | None:
    return _current("SIGNAL_VAPID_PUBLIC_KEY")

def vapid_private_key() -> str | None:
    return _current("SIGNAL_VAPID_PRIVATE_KEY")

def is_configured() -> bool:
    return admin_token() is not None

def persist_env(values: dict[str, str]) -> None:
    existing = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []

    remaining = dict(values)
    out: list[str] = []
    for line in existing:
        key = line.split("=", 1)[0].strip()
        if key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(line)
    out.extend(f"{key}={value}" for key, value in remaining.items())

    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")

    # Owner-only permissions where the platform supports them. Windows does
    # not, and that is not a failure worth stopping for.
    with contextlib.suppress(OSError):
        ENV_PATH.chmod(0o600)

    _overrides.update(values)
    os.environ.update(values)

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
    frontend_dir: Path | None
    setup_allow_remote: bool

def load_settings() -> Settings:
    raw_db_path = Path(_env_str("SIGNAL_DATABASE_PATH", "data/signal.db"))
    database_path = raw_db_path if raw_db_path.is_absolute() else BASE_DIR / raw_db_path

    raw_frontend = _env_str("SIGNAL_FRONTEND_DIR", "")
    frontend_dir = (
        Path(raw_frontend) if raw_frontend else BASE_DIR.parent / "frontend" / "dist"
    )

    return Settings(
        database_path=database_path,
        max_payload=_env_int("SIGNAL_MAX_PAYLOAD_BYTES", 64 * 1024),
        retention_days=_env_int("SIGNAL_RETENTION_DAYS", 90),
        debug=_env_bool("SIGNAL_DEBUG", False),
        admin_token=_env_str("SIGNAL_ADMIN_TOKEN", "") or None,
        vapid_public_key=_env_str("SIGNAL_VAPID_PUBLIC_KEY", "") or None,
        vapid_private_key=_env_str("SIGNAL_VAPID_PRIVATE_KEY", "") or None,
        vapid_subject=_env_str("SIGNAL_VAPID_SUBJECT", "mailto:admin@localhost"),
        frontend_dir=frontend_dir if frontend_dir.is_dir() else None,
        setup_allow_remote=_env_bool("SIGNAL_SETUP_ALLOW_REMOTE", False),
    )

settings = load_settings()
