"""Load the repo-root .env for the command-line tools.

Shells cannot source values such as passwords containing `)` or `#`, and they mangle JSON values, so the
tools read the file themselves with python-dotenv. Variables already in the environment win, which is how
CI and one-off overrides (for example DB_NAME) work.
"""

from pathlib import Path

from dotenv import load_dotenv

REPO_ENV = Path(__file__).resolve().parents[3] / ".env"


def load_repo_env(path: Path = REPO_ENV) -> bool:
    """Load `path` if it exists, without overriding existing variables. True if a file was read."""
    return load_dotenv(path, override=False) if path.exists() else False
