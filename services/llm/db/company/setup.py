"""Create the `company` schema, its read-only query role, and deterministic sample data.

Usage (from the repo root, see `make company-db` / `make company-link`):
    python services/llm/db/company/setup.py                      # (re)create schema + data
    python services/llm/db/company/setup.py --link EMAIL --as manager
                                                                 # make an app account act as a persona

Reads DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME (owner connection) and
QUERY_DB_USER, QUERY_DB_PASSWORD (the read-only role the LLM tool uses) from the environment.
Re-running recreates the schema, which drops any links; pass --link again.
"""

import argparse
import os
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg
from psycopg import sql

SCHEMA_SQL = Path(__file__).with_name("schema.sql")
SEED = 42

# Which employee an app account becomes for each role (see --as).
PERSONAS = {
    "admin": "Chief Executive Officer",
    "manager": "Sales Manager, EMEA",
    "hr": "Head of People",
    "employee": "Account Executive",
}

FIRST = ["Ava", "Liam", "Noah", "Mia", "Leo", "Zara", "Omar", "Sara", "Arash", "Nika", "Lucas", "Emma",
         "Kian", "Yara", "Elias", "Ines", "Darius", "Lena", "Hugo", "Maya", "Reza", "Chloe", "Ivan", "Anya"]
LAST = ["Karimi", "Smith", "Rossi", "Müller", "Tanaka", "Haddad", "Novak", "Silva", "Moradi", "Dubois",
        "Kowalski", "Jensen", "Ahmadi", "Lopez", "Berg", "Nasser", "Costa", "Fischer"]
COUNTRIES = ["Germany", "France", "Netherlands", "Sweden", "Italy", "United States", "Canada", "Brazil",
             "United Kingdom", "Spain", "Iran", "Turkey", "Japan"]
COMPANY_WORDS = (["Blue", "North", "Bright", "Iron", "Green", "Swift", "Silver", "Atlas", "Nova", "Crest"],
                 ["Labs", "Systems", "Logistics", "Foods", "Health", "Media", "Energy", "Retail", "Bank", "Motors"])
PRODUCTS = {
    "Software": [("Analytics Suite", 1200), ("CRM Cloud", 900), ("Security Shield", 650), ("Data Pipeline", 1500),
                 ("Mobile SDK", 400), ("AI Assistant", 2000), ("Backup Pro", 300), ("Workflow Builder", 750)],
    "Hardware": [("Edge Gateway", 850), ("Sensor Kit", 220), ("Rack Server", 4800), ("Smart Display", 640),
                 ("Network Switch", 1300), ("Rugged Tablet", 980), ("Storage Array", 7200)],
    "Services": [("Onboarding Package", 2500), ("Premium Support", 1800), ("Custom Integration", 6000),
                 ("Cloud Migration", 9500), ("Security Audit", 4200), ("Managed Hosting", 1100)],
    "Training": [("Admin Course", 700), ("Developer Bootcamp", 2200), ("Analytics Workshop", 950),
                 ("Security Awareness", 300), ("Certification Exam", 450)],
}


def connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        dbname=os.environ.get("DB_NAME", "chattie"),
    )


def ensure_query_role(cur: psycopg.Cursor) -> None:
    user, password = os.environ.get("QUERY_DB_USER", "chattie_query"), os.environ["QUERY_DB_PASSWORD"]
    exists = cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (user,)).fetchone()
    verb = "ALTER" if exists else "CREATE"
    # NOINHERIT and no memberships: there is no other role this login could switch to.
    cur.execute(sql.SQL("{} ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD {}").format(
        sql.SQL(verb), sql.Identifier(user), sql.Literal(password)))
    cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
        sql.Identifier(os.environ.get("DB_NAME", "chattie")), sql.Identifier(user)))


def build_employees(rng: random.Random) -> list[tuple]:
    names = iter(rng.sample([f"{f} {l}" for f in FIRST for l in LAST], 60))
    rows: list[tuple] = []

    def add(dept: int, manager: int | None, title: str, role: str, salary: tuple[int, int]) -> int:
        emp_id = len(rows) + 1
        hired = date(2016, 1, 1) + timedelta(days=rng.randrange(0, 3650))
        rows.append((emp_id, dept, manager, next(names), title, role, rng.randrange(*salary, 500), hired))
        return emp_id

    ceo = add(1, None, "Chief Executive Officer", "admin", (240_000, 260_000))
    for region in ("EMEA", "Americas"):
        head = add(2, ceo, f"Sales Manager, {region}", "manager", (120_000, 140_000))
        for _ in range(6):
            add(2, head, "Account Executive", "employee", (60_000, 90_000))
    for dept, title, staff, count in ((3, "Engineering Manager", "Software Engineer", 6),
                                      (4, "Marketing Manager", "Marketing Specialist", 3),
                                      (6, "Support Manager", "Support Engineer", 4)):
        head = add(dept, ceo, title, "manager", (110_000, 135_000))
        for _ in range(count):
            add(dept, head, staff, "employee", (55_000, 110_000))
    hr_head = add(5, ceo, "Head of People", "hr", (105_000, 120_000))
    add(5, hr_head, "HR Specialist", "hr", (55_000, 70_000))
    return rows


def seed(cur: psycopg.Cursor) -> None:
    rng = random.Random(SEED)
    cur.executemany("INSERT INTO company.departments VALUES (%s, %s)", list(enumerate(
        ["Executive", "Sales", "Engineering", "Marketing", "Human Resources", "Customer Support"], start=1)))

    employees = build_employees(rng)
    cur.executemany("INSERT INTO company.employees (id, department_id, manager_id, name, title, role, salary, hired_at)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", employees)
    reps = [e[0] for e in employees if e[4] == "Account Executive"]

    products = [(i, name, category, price) for i, (category, name, price) in enumerate(
        ((c, n, p) for c, items in PRODUCTS.items() for n, p in items), start=1)]
    cur.executemany("INSERT INTO company.products VALUES (%s, %s, %s, %s)", products)

    company_names = rng.sample([f"{a} {b}" for a in COMPANY_WORDS[0] for b in COMPANY_WORDS[1]], 60)
    customers = [(i, name, rng.choice(COUNTRIES), rng.choice(reps)) for i, name in enumerate(company_names, start=1)]
    cur.executemany("INSERT INTO company.customers VALUES (%s, %s, %s, %s)", customers)

    now = datetime.now(timezone.utc)
    orders = []
    for order_id in range(1, 601):
        customer = rng.choice(customers)
        product = rng.choice(products)
        quantity = rng.randint(1, 20)
        age_days = rng.uniform(0, 540)
        status = ("cancelled" if rng.random() < 0.05 else "pending" if age_days < 7
                  else "shipped" if age_days < 21 else "delivered")
        orders.append((order_id, customer[0], product[0], customer[3], quantity,
                       quantity * product[3], status, now - timedelta(days=age_days)))
    cur.executemany("INSERT INTO company.orders VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", orders)
    print(f"seeded {len(employees)} employees, {len(customers)} customers, "
          f"{len(products)} products, {len(orders)} orders")


def link(cur: psycopg.Cursor, email: str, role: str) -> None:
    user = cur.execute('SELECT id FROM auth."user" WHERE email = %s', (email,)).fetchone()
    if not user:
        raise SystemExit(f"no app account with email {email!r}; sign up first")
    title = PERSONAS[role]
    employee = cur.execute("SELECT id, name FROM company.employees WHERE title = %s ORDER BY id LIMIT 1",
                           (title,)).fetchone()
    cur.execute("UPDATE company.employees SET user_id = NULL WHERE user_id = %s", (user[0],))
    cur.execute("UPDATE company.employees SET user_id = %s WHERE id = %s", (user[0], employee[0]))
    print(f"{email} now acts as {employee[1]} ({title}, role={role})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--link", metavar="EMAIL", help="link this app account to a persona (keeps the data)")
    parser.add_argument("--as", dest="role", choices=PERSONAS, default="manager", help="persona role for --link")
    args = parser.parse_args()

    with connect() as conn, conn.cursor() as cur:
        if args.link:
            link(cur, args.link, args.role)
            return
        ensure_query_role(cur)
        cur.execute(SCHEMA_SQL.read_text())
        seed(cur)


if __name__ == "__main__":
    main()
