"""Characterization tests: what each role may read and write through row-level security.

Expected sets are computed from owner-side queries, so the tests describe the rules
(own orders, own and direct reports' orders, everything) and not the sample data.
"""

import psycopg
import pytest


async def visible_ids(role_conn, apply_identity, user_id, query):
    async with role_conn("chattie_query") as conn, conn.transaction():
        await apply_identity(conn, user_id)
        return sorted(row[0] for row in await (await conn.execute(query)).fetchall())


def owner_ids(conn, query, params=()):
    return sorted(row[0] for row in conn.execute(query, params).fetchall())


async def test_employee_sees_only_own_orders(world_db, link_user, pick_employee, role_conn, apply_identity):
    rep = pick_employee(world_db, "title = 'Account Executive'")
    link_user(world_db, "u-rep", rep)
    expected = owner_ids(world_db, "SELECT id FROM company.orders WHERE sales_rep_id = %s", (rep,))
    assert expected  # the persona must have orders, or the test proves nothing
    assert await visible_ids(role_conn, apply_identity, "u-rep", "SELECT id FROM company.orders") == expected


async def test_manager_sees_own_and_direct_reports_orders(
    world_db, link_user, pick_employee, role_conn, apply_identity
):
    manager = pick_employee(world_db, "title LIKE 'Sales Manager%'")
    link_user(world_db, "u-mgr", manager)
    expected = owner_ids(
        world_db,
        "SELECT o.id FROM company.orders o JOIN company.employees e ON e.id = o.sales_rep_id "
        "WHERE e.id = %s OR e.manager_id = %s",
        (manager, manager),
    )
    assert expected
    assert await visible_ids(role_conn, apply_identity, "u-mgr", "SELECT id FROM company.orders") == expected
    total = world_db.execute("SELECT count(*) FROM company.orders").fetchone()[0]
    assert len(expected) < total  # a manager is scoped, not company-wide


async def test_admin_sees_all_orders(world_db, link_user, pick_employee, role_conn, apply_identity):
    link_user(world_db, "u-admin", pick_employee(world_db, "role = 'admin'"))
    expected = owner_ids(world_db, "SELECT id FROM company.orders")
    assert await visible_ids(role_conn, apply_identity, "u-admin", "SELECT id FROM company.orders") == expected


async def test_unlinked_user_sees_no_people_or_orders_but_sees_departments_and_products(
    world_db, role_conn, apply_identity
):
    for table in ("employees", "orders", "customers", "me"):
        assert await visible_ids(role_conn, apply_identity, "u-nobody", f"SELECT 1 FROM company.{table}") == []
    for table in ("departments", "products"):
        assert await visible_ids(role_conn, apply_identity, "u-nobody", f"SELECT id FROM company.{table}")


async def test_salary_visibility_by_role(world_db, link_user, pick_employee, role_conn, apply_identity):
    everyone = owner_ids(world_db, "SELECT id FROM company.employees")
    query = "SELECT employee_id FROM company.employee_salaries"

    rep = pick_employee(world_db, "role = 'employee'")
    link_user(world_db, "u-rep", rep)
    assert await visible_ids(role_conn, apply_identity, "u-rep", query) == [rep]

    for role, user in (("hr", "u-hr"), ("admin", "u-admin")):
        link_user(world_db, user, pick_employee(world_db, f"role = '{role}'"))
        assert await visible_ids(role_conn, apply_identity, user, query) == everyone


async def test_query_role_cannot_select_the_salary_column(world_db, role_conn):
    async with role_conn("chattie_query") as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await conn.execute("SELECT salary FROM company.employees")


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO company.products VALUES (999, 'x', 'x', 1)",
        "UPDATE company.products SET price = 1",
        "DELETE FROM company.orders",
        "TRUNCATE company.orders",
    ],
)
async def test_query_role_cannot_write(world_db, role_conn, statement):
    async with role_conn("chattie_query") as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await conn.execute(statement)


async def test_query_role_cannot_change_identity_with_set_config(world_db, role_conn):
    async with role_conn("chattie_query") as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await conn.execute("SELECT set_config('app.user_id', 'someone-else', true)")
