from pathlib import Path

import pytest

from db.migrate import MIGRATIONS_DIR, apply_migrations

OLD_SCHEMA = Path(__file__).parent.parent / "db" / "company" / "schema.sql"


@pytest.fixture
def empty_db(owner_conn):
    """A pristine database state: no company schema, no migration table."""
    owner_conn.execute("DROP SCHEMA IF EXISTS company CASCADE")
    owner_conn.execute("DROP TABLE IF EXISTS public.schema_migrations")
    return owner_conn


def test_empty_db_gets_company_schema(empty_db):
    applied = apply_migrations(empty_db, MIGRATIONS_DIR)
    assert applied[0] == "0001"
    assert empty_db.execute("select to_regclass('company.employees')").fetchone()[0] is not None
    versions = [r[0] for r in empty_db.execute("select version from public.schema_migrations order by 1")]
    assert versions[0] == "0001"


def test_second_run_applies_nothing(empty_db):
    apply_migrations(empty_db, MIGRATIONS_DIR)
    assert apply_migrations(empty_db, MIGRATIONS_DIR) == []


def test_existing_schema_is_adopted_not_rerun(empty_db):
    empty_db.execute(OLD_SCHEMA.read_text())  # what setup.py created before migrations existed
    empty_db.execute("insert into company.departments values (1, 'Sales')")
    empty_db.execute(
        "insert into company.employees (id, department_id, name, title, role, salary, hired_at) "
        "values (1, 1, 'Keep Me', 'Account Executive', 'employee', 50000, '2020-01-01')"
    )
    apply_migrations(empty_db, MIGRATIONS_DIR)
    assert empty_db.execute("select name from company.employees where id = 1").fetchone()[0] == "Keep Me"
    assert empty_db.execute("select count(*) from public.schema_migrations where version = '0001'").fetchone()[0] == 1


def test_ensure_roles_skips_roles_without_a_password(owner_conn):
    from db.roles import ensure_roles

    assert ensure_roles(owner_conn, {}) == []


def test_migration_0004_unlinks_accounts_from_seed_staff_and_changes_nothing_else(owner_conn, tmp_path):
    import shutil

    owner_conn.execute("DROP SCHEMA IF EXISTS company CASCADE")
    owner_conn.execute("DROP TABLE IF EXISTS public.schema_migrations")
    for path in sorted(MIGRATIONS_DIR.glob("000[123]_*.sql")):  # the database as it was before 0004
        shutil.copy(path, tmp_path / path.name)
    apply_migrations(owner_conn, tmp_path)
    owner_conn.execute("INSERT INTO company.departments VALUES (1, 'Sales')")
    owner_conn.execute(
        "INSERT INTO company.employees (id, department_id, name, title, role, salary, hired_at, user_id) VALUES "
        "(1, 1, 'Linked Seed', 'Account Executive', 'employee', 50000, '2020-01-01', 'some-account'),"
        "(2, 1, 'Unlinked Seed', 'Account Executive', 'employee', 50000, '2020-01-01', NULL)")
    owner_conn.execute(
        "INSERT INTO company.employees (id, department_id, name, title, role, salary, hired_at, user_id, origin) "
        "VALUES (3, 1, 'A Visitor', 'Account Executive', 'employee', 50000, '2020-01-01', 'visitor-account', 'visitor')")

    assert apply_migrations(owner_conn, MIGRATIONS_DIR) == ["0004"]

    rows = dict(owner_conn.execute("SELECT id, user_id FROM company.employees").fetchall())
    assert rows == {1: None, 2: None, 3: "visitor-account"}  # the seed link is gone; a visitor keeps theirs
