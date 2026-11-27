"""Full backup of the database named by DB_* (custom pg_dump format), written with owner-only permissions.

    python -m db.backup [path]      (default: ../../backups/<db>-<timestamp>.dump, outside the code folders)
Restore with pg_restore. The file contains accounts and chats: keep it private.
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from db.envfile import load_repo_env
from db.pgtools import pg_tool


def backup(target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PGHOST": os.environ.get("DB_HOST", "localhost"), "PGPORT": os.environ.get("DB_PORT", "5432"),
           "PGUSER": os.environ["DB_USER"], "PGPASSWORD": os.environ["DB_PASSWORD"]}
    done = subprocess.run([str(pg_tool("pg_dump")), "-Fc", "-f", str(target), os.environ.get("DB_NAME", "chattie")],
                          env=env, capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit(f"pg_dump failed: {done.stderr.strip()[-400:]}")
    target.chmod(0o600)
    listing = subprocess.run([str(pg_tool("pg_restore")), "--list", str(target)], capture_output=True, text=True)
    if listing.returncode != 0:
        raise SystemExit("the backup was written but cannot be read back; do not rely on it")
    return target


def main() -> None:
    load_repo_env()
    name = os.environ.get("DB_NAME", "chattie")
    default = Path(__file__).resolve().parents[3].parent / "backups" / f"{name}-{datetime.now():%Y%m%d-%H%M%S}.dump"
    path = backup(Path(sys.argv[1]) if len(sys.argv) > 1 else default)
    print(f"backup written and verified readable: {path} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
