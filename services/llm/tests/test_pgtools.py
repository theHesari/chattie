from pathlib import Path

import pytest

from db.pgtools import pg_tool


def test_the_configured_folder_wins_when_the_tool_is_there(tmp_path):
    (tmp_path / "pg_dump").write_text("")
    assert pg_tool("pg_dump", env={"PG_BIN": str(tmp_path)}, which=lambda _: "/elsewhere/pg_dump") == tmp_path / "pg_dump"


def test_falls_back_to_the_path_when_the_folder_lacks_it(tmp_path):
    """CI runners and other machines do not have Homebrew's folder; pg_dump is simply on the PATH."""
    assert pg_tool("pg_dump", env={"PG_BIN": str(tmp_path / "missing")}, which=lambda name: f"/usr/bin/{name}") == Path("/usr/bin/pg_dump")


def test_a_clear_error_when_nothing_is_found(tmp_path):
    with pytest.raises(FileNotFoundError, match="PG_BIN"):
        pg_tool("pg_dump", env={"PG_BIN": str(tmp_path)}, which=lambda _: None)
