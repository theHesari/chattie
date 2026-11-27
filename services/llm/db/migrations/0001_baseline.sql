-- Baseline: the company schema as created by db/company/schema.sql before migrations existed.
-- The DROP SCHEMA line is removed on purpose: migrations never drop data. An existing
-- database that already has company.employees adopts this version without running it.

-- Company workspace: sample business data the LLM can query with read-only SQL.
--
-- Authorization is enforced by Postgres, not by the model:
--   * the query tool connects as `chattie_query` (created by setup.py), which can only SELECT here;
--   * row-level security policies decide which rows each signed-in user sees;
--   * the API sets `app.user_id` (the verified JWT subject) per read-only transaction, and
--     `chattie_query` cannot change it (no SET statements; set_config() revoked below).
--
-- Roles (employees.role): employee | manager | hr | admin
--   employees (directory: name, title, role, department, manager): every linked employee sees everyone
--   salaries:  self; hr/admin see everyone           (column-protected, via employee_salaries)
--   customers/orders: own; managers also their reports'; admin everything
-- company.my_access describes the caller's scope in words, so answers can state it;
-- keep it in sync with the policies below.
--
-- Idempotent: drops and recreates the schema. Run as the database owner (see setup.py).

CREATE SCHEMA company;

CREATE TABLE company.departments (
    id   integer PRIMARY KEY,
    name text NOT NULL UNIQUE
);

CREATE TABLE company.employees (
    id            integer PRIMARY KEY,
    user_id       text UNIQUE,                         -- Better Auth user id (auth."user".id), if linked
    department_id integer NOT NULL REFERENCES company.departments,
    manager_id    integer REFERENCES company.employees,
    name          text NOT NULL,
    title         text NOT NULL,
    role          text NOT NULL CHECK (role IN ('employee', 'manager', 'hr', 'admin')),
    salary        numeric(10, 2) NOT NULL,
    hired_at      date NOT NULL
);

CREATE TABLE company.customers (
    id                 integer PRIMARY KEY,
    name               text NOT NULL,
    country            text NOT NULL,
    account_manager_id integer NOT NULL REFERENCES company.employees
);

CREATE TABLE company.products (
    id       integer PRIMARY KEY,
    name     text NOT NULL,
    category text NOT NULL,
    price    numeric(10, 2) NOT NULL
);

CREATE TABLE company.orders (
    id           integer PRIMARY KEY,
    customer_id  integer NOT NULL REFERENCES company.customers,
    product_id   integer NOT NULL REFERENCES company.products,
    sales_rep_id integer NOT NULL REFERENCES company.employees,
    quantity     integer NOT NULL CHECK (quantity > 0),
    total        numeric(12, 2) NOT NULL,
    status       text NOT NULL CHECK (status IN ('pending', 'shipped', 'delivered', 'cancelled')),
    ordered_at   timestamptz NOT NULL
);

CREATE INDEX ON company.employees (manager_id);
CREATE INDEX ON company.customers (account_manager_id);
CREATE INDEX ON company.orders (sales_rep_id);
CREATE INDEX ON company.orders (ordered_at);

-- ---------------------------------------------------------------------------
-- Identity and access helpers. SECURITY DEFINER so they can read `employees`
-- without being filtered by its own policy; search_path pinned against hijacking.
-- ---------------------------------------------------------------------------

CREATE FUNCTION company.current_employee_id() RETURNS integer
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = company, pg_temp AS $$
    SELECT id FROM employees WHERE user_id = nullif(current_setting('app.user_id', true), '')
$$;

CREATE FUNCTION company.current_role_name() RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = company, pg_temp AS $$
    SELECT role FROM employees WHERE id = current_employee_id()
$$;

CREATE FUNCTION company.is_direct_report(emp_id integer) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = company, pg_temp AS $$
    SELECT EXISTS (SELECT 1 FROM employees WHERE id = emp_id AND manager_id = current_employee_id())
$$;

CREATE FUNCTION company.can_see_salary(emp_id integer) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = company, pg_temp AS $$
    SELECT emp_id = current_employee_id() OR current_role_name() IN ('hr', 'admin')
$$;

CREATE FUNCTION company.can_see_sales_of(rep_id integer) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = company, pg_temp AS $$
    SELECT rep_id = current_employee_id()
        OR current_role_name() = 'admin'
        OR (current_role_name() = 'manager' AND is_direct_report(rep_id))
$$;

-- ---------------------------------------------------------------------------
-- Row-level security
-- ---------------------------------------------------------------------------

ALTER TABLE company.employees ENABLE ROW LEVEL SECURITY;
ALTER TABLE company.customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE company.orders    ENABLE ROW LEVEL SECURITY;

-- The directory is company-wide for anyone linked to an employee; sensitive data
-- (salaries, customers, orders) stays restricted below and in employee_salaries.
CREATE POLICY employees_visible ON company.employees FOR SELECT USING (company.current_employee_id() IS NOT NULL);
CREATE POLICY customers_visible ON company.customers FOR SELECT USING (company.can_see_sales_of(account_manager_id));
CREATE POLICY orders_visible    ON company.orders    FOR SELECT USING (company.can_see_sales_of(sales_rep_id));

-- ---------------------------------------------------------------------------
-- Views for the model
-- ---------------------------------------------------------------------------

-- The caller's own employee record ("me", "my team", "my orders").
CREATE VIEW company.me AS
    SELECT e.id, e.name, e.title, e.role, d.name AS department
    FROM company.employees e JOIN company.departments d ON d.id = e.department_id
    WHERE e.id = company.current_employee_id();

-- Salaries are column-protected: chattie_query can't select employees.salary;
-- this view (run with its owner's rights) applies the salary rule instead.
CREATE VIEW company.employee_salaries AS
    SELECT id AS employee_id, salary
    FROM company.employees
    WHERE company.can_see_salary(id);

-- What the caller can see, in words, per dataset. The query tool attaches this to every
-- result so a scoped count (e.g. "your team's orders") is never reported as a company total.
CREATE VIEW company.my_access AS
    SELECT dataset, visible
    FROM (VALUES
        ('departments, products', 'all of them'),
        ('employees (directory)', 'everyone in the company'),
        ('salaries', CASE WHEN company.current_role_name() IN ('hr', 'admin')
                          THEN 'everyone' ELSE 'only your own' END),
        ('customers, orders', CASE company.current_role_name()
                                  WHEN 'admin' THEN 'the whole company'
                                  WHEN 'manager' THEN 'only your own and your direct reports'''
                                  ELSE 'only your own' END)
    ) AS access (dataset, visible)
    WHERE company.current_employee_id() IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Privileges for the query role (created by setup.py before this file runs)
-- ---------------------------------------------------------------------------

GRANT USAGE ON SCHEMA company TO chattie_query;
GRANT SELECT ON company.departments, company.customers, company.products, company.orders TO chattie_query;
GRANT SELECT (id, department_id, manager_id, name, title, role, hired_at) ON company.employees TO chattie_query;
GRANT SELECT ON company.me, company.employee_salaries, company.my_access TO chattie_query;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA company TO chattie_query;

-- Identity must not be changeable from a query: without set_config(), the only way to
-- change app.user_id is a SET statement, which the query tool never lets through.
REVOKE EXECUTE ON FUNCTION pg_catalog.set_config(text, text, boolean) FROM PUBLIC;
