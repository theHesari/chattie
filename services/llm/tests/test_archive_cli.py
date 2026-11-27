import argparse
from datetime import date, timedelta

from company.characters import replace_character
from db.company.setup import cmd_archive

TODAY = date(2026, 11, 27)


def test_the_archive_command_archives_only_stale_characters_and_says_how_many(world_db, generator_conn, capsys):
    for user in ("u-stale", "u-fresh"):
        replace_character(generator_conn, user_id=user, display_name=user, role="employee", department_id=3, today=TODAY)
    world_db.execute("UPDATE company.employees SET last_active_at = %s WHERE user_id = 'u-stale'", (TODAY - timedelta(days=45),))

    cmd_archive(generator_conn, argparse.Namespace(days=30, today=TODAY))

    assert "archived 1" in capsys.readouterr().out
    active = dict(world_db.execute("SELECT user_id, is_active FROM company.employees WHERE user_id IN ('u-stale', 'u-fresh')").fetchall())
    assert active == {"u-stale": False, "u-fresh": True}
