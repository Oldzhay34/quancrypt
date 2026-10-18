"""Where the Quancrypt installation is (D-277): `QUANCRYPT_HOME`, else `home:` in `~/.config/quancrypt/config.yaml`."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

HOME_VARIABLE = "QUANCRYPT_HOME"
LANGUAGE_VARIABLE = "QUANCRYPT_LANG"
CONFIG_RELATIVE = Path(".config") / "quancrypt" / "config.yaml"
_MAX_CONFIG_BYTES = 16 * 1024


class InstallNotFoundError(Exception):
    """No usable Quancrypt installation directory. The message names paths, never secrets."""


@dataclass(frozen=True)
class Settings:
    home: Path  # holds docker-compose.yml and .env


def load_settings(env: Mapping[str, str], user_home: Path) -> Settings:
    configured = env.get(HOME_VARIABLE) or _from_config(user_home / CONFIG_RELATIVE)
    if not configured:
        raise InstallNotFoundError(f"set {HOME_VARIABLE} or home: in {user_home / CONFIG_RELATIVE}")
    home = Path(configured).expanduser()
    if not home.is_absolute():
        raise InstallNotFoundError(f"{HOME_VARIABLE} must be an absolute path")
    for name in ("docker-compose.yml", ".env"):
        if not (home / name).is_file():
            raise InstallNotFoundError(f"{home / name} does not exist")
    return Settings(home.resolve())


def _from_config(path: Path) -> str | None:
    try:
        if path.stat().st_size > _MAX_CONFIG_BYTES:
            return None
        data: Any = yaml.safe_load(path.read_text("utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    value = data.get("home") if isinstance(data, dict) else None
    return value if isinstance(value, str) else None
