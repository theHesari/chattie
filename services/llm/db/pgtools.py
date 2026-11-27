"""Locating the PostgreSQL client tools (pg_dump, pg_restore)."""

import os
import shutil
from collections.abc import Callable, Mapping
from pathlib import Path

DEFAULT_PG_BIN = "/usr/local/opt/postgresql@15/bin"  # Homebrew on the developer's Mac


def pg_tool(name: str, env: Mapping[str, str] = os.environ, which: Callable[[str], str | None] = shutil.which) -> Path:
    """The configured folder (PG_BIN) if it holds the tool, otherwise the tool on the PATH (CI runners)."""
    candidate = Path(env.get("PG_BIN") or DEFAULT_PG_BIN) / name
    if candidate.exists():
        return candidate
    found = which(name)
    if found:
        return Path(found)
    raise FileNotFoundError(f"{name} not found: set PG_BIN to the folder holding your PostgreSQL client tools")
