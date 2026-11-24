"""Read-only SQL over the `company` schema, as the signed-in user.

Authorization lives in Postgres (db/company/schema.sql): this tool connects as the
read-only `chattie_query` role, and row-level security filters every table by the
`app.user_id` set here from the verified JWT subject. The model never sees or picks
the user id; it is injected from the run config.
"""

import json
import logging
import re

import psycopg
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool
from psycopg import sql
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)

MAX_ROWS = 50
STATEMENT_TIMEOUT_MS = 5_000

DESCRIPTION = """Run ONE read-only PostgreSQL SELECT over the company's business data and get rows back as JSON.

Rows are filtered by the current user's access (row-level security), so write queries as if for the
whole company and do NOT filter by the current user yourself; only use company.me when the question
is explicitly about the user ("my orders", "my team"). Every result has a `viewer`
field with `access`: what this user can see per dataset. Use it when answering:
- If the data the question needs is fully visible (e.g. the employee directory), answer normally.
- If it is scoped (e.g. orders: "only your own"), state the scope in the answer ("you had 3 orders in
  the last 30 days") and, for a company-wide question, say the company-wide figure isn't available to
  them. Never present a scoped number as a company total, and never report an empty scoped result as
  "none exist".
Always schema-qualify tables with `company.`. Use aggregates (count, sum, date_trunc) instead of
fetching raw rows; at most 50 rows are returned.

Text values must match what is stored; never guess spellings or abbreviations:
- Use the exact values listed under "Stored values" below.
- Countries are stored as full English names ('United States', 'United Kingdom'), never codes or
  abbreviations ('US', 'UK').
- For names (customers, products, employees) match case-insensitively: name ILIKE '%acme%'.
- If a filtered query returns 0 rows, look at the actual values first (e.g. SELECT DISTINCT country
  FROM company.customers) and retry before concluding there are none.

Tables:
- company.me(id, name, title, role, department): the current user's own employee record (empty if
  their account isn't linked to an employee). Use it for "me", "my team", "my orders".
- company.departments(id, name)
- company.employees(id, department_id, manager_id, name, title, role, hired_at): the company directory.
  role is one of employee | manager | hr | admin; a manager's team = employees with manager_id = their id.
- company.employee_salaries(employee_id, salary): salaries the user may see (salary is not in employees).
- company.customers(id, name, country, account_manager_id -> employees.id)
- company.products(id, name, category, price)
- company.orders(id, customer_id, product_id, sales_rep_id -> employees.id, quantity, total, status,
  ordered_at timestamptz); status is pending | shipped | delivered | cancelled. Revenue = sum(total)
  excluding cancelled orders.
All money amounts (price, total, salary) are in US dollars."""


UNLINKED_VIEWER = (
    "This account is not linked to an employee, so it can only see departments and products; "
    "employees, salaries, customers and orders are hidden from it, not empty."
)


# Restricted datasets (keys of company.my_access) and the relations that hold them.
RESTRICTED = {
    "customers, orders": re.compile(r"\bcompany\.(orders|customers)\b", re.IGNORECASE),
    "salaries": re.compile(r"\bcompany\.employee_salaries\b", re.IGNORECASE),
}
FULL_ACCESS = {"the whole company", "everyone"}


def _scope_note(sql_query: str, access: dict[str, str]) -> str | None:
    """A plain warning when the query read a dataset the user only partly sees."""
    partial = [
        f"{dataset}: {access[dataset]}"
        for dataset, pattern in RESTRICTED.items()
        if pattern.search(sql_query) and access.get(dataset) not in FULL_ACCESS
    ]
    if not partial:
        return None
    return (
        "This result is NOT company-wide. It only includes " + "; ".join(partial) + ". "
        "Say so in the answer; the company-wide figure is not available to this user."
    )


def _viewer(me: tuple | None, access: list[tuple]) -> dict | str:
    """Whose access applied and what it covers (from company.my_access), so a scoped
    result is never mistaken for a company-wide one."""
    if me is None:
        return UNLINKED_VIEWER
    name, title, role = me
    return {"name": name, "title": title, "role": role, "access": dict(access)}


def _as_json(viewer: dict | str, scope_note: str | None, columns: list[str], rows: list[tuple]) -> str:
    return json.dumps(
        {
            "viewer": viewer,
            **({"scope_note": scope_note} if scope_note else {}),
            "columns": columns,
            "rows": [list(row) for row in rows[:MAX_ROWS]],
            "truncated": len(rows) > MAX_ROWS,
        },
        default=str,  # Decimal, datetime, date
        ensure_ascii=False,
    )


# Lookup values the model must match exactly. Only tables without row-level security, so the
# list is the same for every user and reveals nothing they couldn't query themselves.
STORED_VALUES = {
    "company.departments.name": "SELECT name FROM company.departments ORDER BY name",
    "company.products.category": "SELECT DISTINCT category FROM company.products ORDER BY category",
}


async def _stored_values(pool: AsyncConnectionPool) -> str:
    """'Stored values' section of the description, read from the database so it can't drift."""
    lines = []
    try:
        async with pool.connection() as conn, conn.transaction():
            await conn.execute("SET TRANSACTION READ ONLY")
            for column, query in STORED_VALUES.items():
                values = [row[0] for row in await (await conn.execute(query)).fetchall()]
                lines.append(f"- {column}: " + " | ".join(f"'{value}'" for value in values))
    except psycopg.Error as exc:
        # The company schema isn't set up (make company-db); the tool still works, minus the list.
        logger.warning("could not load stored values for the company SQL tool: %s", exc)
        return ""
    return "\n\nStored values:\n" + "\n".join(lines)


async def build_company_sql_tool(pool: AsyncConnectionPool) -> BaseTool:
    """The query_company_data tool, with current lookup values in its description."""
    description = DESCRIPTION + await _stored_values(pool)

    @tool("query_company_data", description=description)
    async def query_company_data(sql_query: str, config: RunnableConfig) -> str:
        user_id = config.get("configurable", {}).get("user_id")
        if not user_id:
            return "Not available: no signed-in user."

        # Wrapping the model's text as a subquery admits exactly one SELECT/WITH query:
        # a second statement, SET, or any other command is a syntax error here.
        query = sql.SQL("SELECT * FROM ({}) AS q LIMIT {}").format(
            sql.SQL(sql_query.strip().rstrip(";")), sql.Literal(MAX_ROWS + 1)
        )
        try:
            async with pool.connection() as conn, conn.transaction():
                await conn.execute("SET TRANSACTION READ ONLY")
                await conn.execute(sql.SQL("SET LOCAL statement_timeout = {}").format(sql.Literal(STATEMENT_TIMEOUT_MS)))
                await conn.execute(sql.SQL("SET LOCAL app.user_id = {}").format(sql.Literal(user_id)))
                me = await (await conn.execute("SELECT name, title, role FROM company.me")).fetchone()
                access = await (await conn.execute("SELECT dataset, visible FROM company.my_access")).fetchall()
                cursor = await conn.execute(query)
                columns = [column.name for column in cursor.description or []]
                rows = await cursor.fetchall()
        except psycopg.Error as exc:
            # Returned to the model so it can fix its query; contains no data.
            message = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
            logger.info("company query rejected: %s", message)
            return f"Query failed: {message}"

        scope_note = _scope_note(sql_query, dict(access)) if me else None
        return _as_json(_viewer(me, access), scope_note, columns, rows)

    return query_company_data
