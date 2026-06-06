"""``.env`` loading helpers shared by every platform project.

This is intentionally *not* a `Settings` dataclass — every platform has its
own fields (encryption keys, payload shapes, CDN prefixes, ...). Instead it
provides the env-parsing primitives so each platform's ``config.py`` stays
short and consistent:

    from crawling_core.config import load_env_file, env, env_int, env_bool

    load_env_file(PROJECT_ROOT / ".env")

    @dataclass(frozen=True, slots=True)
    class Settings:
        api_host: str = env("PLATFORM_API_HOST")
        page_size: int = env_int("PLATFORM_PAGE_SIZE", 20)
        ...
"""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: Path) -> None:
    """Populate ``os.environ`` from a dotenv-style file (existing env vars win)."""
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_int(name: str, default: int) -> int:
    value = env(name)
    return int(value) if value else default


def env_float(name: str, default: float) -> float:
    value = env(name)
    return float(value) if value else default


def env_bool(name: str, default: bool) -> bool:
    value = env(name)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def ensure_dirs(*paths: Path) -> None:
    """Create every directory in ``paths`` (and parents) if missing — handy
    for an ``--init-only`` bootstrap step."""
    for path in paths:
        Path(path).mkdir(parents=True, exist_ok=True)
