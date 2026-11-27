-- People tables: generated characters, requests, work hours and history, with row-level
-- security and least-privilege roles. Additive: no existing data is changed or dropped.
-- Roles chattie_query, chattie_app and chattie_generator must already exist (see db/roles.py).

CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ---------------------------------------------------------------------------
-- employees: who owns a row, and whether it is currently visible
-- ---------------------------------------------------------------------------

ALTER TABLE company.employees
    ADD COLUMN origin         text        NOT NULL DEFAULT 'seed'
        CHECK (origin IN ('seed', 'simulated', 'visitor')),
    ADD COLUMN created_at     timestamptz NOT NULL DEFAULT now(),
    ADD COLUMN is_active      boolean     NOT NULL DEFAULT true,
    ADD COLUMN archived_at    timestamptz,
    ADD COLUMN last_active_at timestamptz;

-- Generated rows take their ids from sequences far above the seeded ids.
CREATE SEQUENCE company.employees_id_seq START 1000 OWNED BY company.employees.id;
CREATE SEQUENCE company.customers_id_seq START 10000 OWNED BY company.customers.id;
CREATE SEQUENCE company.orders_id_seq    START 100000 OWNED BY company.orders.id;
ALTER TABLE company.employees ALTER COLUMN id SET DEFAULT nextval('company.employees_id_seq');
ALTER TABLE company.customers ALTER COLUMN id SET DEFAULT nextval('company.customers_id_seq');
ALTER TABLE company.orders    ALTER COLUMN id SET DEFAULT nextval('company.orders_id_seq');

-- ---------------------------------------------------------------------------
-- Small tables: world settings, holidays, leave policy
-- ---------------------------------------------------------------------------

CREATE TABLE company.meta (key text PRIMARY KEY, value text NOT NULL);

CREATE TABLE company.holidays (day date PRIMARY KEY, name text NOT NULL);

CREATE TABLE company.leave_policy (
    singleton   boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    annual_days integer NOT NULL DEFAULT 20 CHECK (annual_days >= 0)
);
INSERT INTO company.leave_policy DEFAULT VALUES;

-- ---------------------------------------------------------------------------
-- Person tables
-- ---------------------------------------------------------------------------

CREATE TABLE company.employee_requests (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id     integer NOT NULL REFERENCES company.employees ON DELETE CASCADE,
    kind            text NOT NULL CHECK (kind IN ('day_off', 'sick_day', 'remote_day', 'schedule_change', 'overtime')),
    starts_on       date NOT NULL,
    ends_on         date NOT NULL,
    start_time      time,
    end_time        time,
    hours           numeric(4, 2),
    reason          text,
    status          text NOT NULL CHECK (status IN ('approved', 'rejected', 'cancelled')),
    decision_reason text NOT NULL DEFAULT '',
    request_key     uuid NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    decided_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (employee_id, request_key),
    CHECK (ends_on >= starts_on),
    CHECK (kind <> 'sick_day' OR reason IS NULL),  -- sick reasons are never stored
    -- An employee cannot be on two approved leaves at once.
    EXCLUDE USING gist (employee_id WITH =, daterange(starts_on, ends_on, '[]') WITH &&)
        WHERE (status = 'approved' AND kind IN ('day_off', 'sick_day'))
);
CREATE INDEX ON company.employee_requests (employee_id, starts_on);

CREATE TABLE company.work_days (
    employee_id integer NOT NULL REFERENCES company.employees ON DELETE CASCADE,
    day         date NOT NULL,
    hours       numeric(4, 2) NOT NULL,
    kind        text NOT NULL CHECK (kind IN ('office', 'remote', 'leave', 'sick', 'holiday')),
    PRIMARY KEY (employee_id, day)
);

CREATE TABLE company.employee_events (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id integer NOT NULL REFERENCES company.employees ON DELETE CASCADE,
    happened_at timestamptz NOT NULL,
    kind        text NOT NULL,
    title       text NOT NULL,
    details     jsonb NOT NULL DEFAULT '{}',
    -- The timeline is shown to anyone who can see the person; amounts live behind the salary rule.
    CONSTRAINT employee_events_no_salary CHECK (details::text !~* 'salary')
);
CREATE INDEX ON company.employee_events (employee_id, happened_at DESC);

-- ---------------------------------------------------------------------------
-- Identity and access: inactive (archived) characters act like unlinked accounts
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION company.current_employee_id() RETURNS integer
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = company, pg_temp AS $$
    SELECT id FROM employees
    WHERE user_id = nullif(current_setting('app.user_id', true), '') AND is_active
$$;

-- The people the caller may see, as a set. Policies use it as `employee_id IN (SELECT ...)`, which
-- Postgres evaluates once per query; a per-row function call made large reads take seconds.
CREATE FUNCTION company.visible_people() RETURNS SETOF integer
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = company, pg_temp AS $$
    SELECT e.id FROM employees e
    WHERE e.is_active
      AND (e.id = current_employee_id()
           OR current_role_name() IN ('hr', 'admin')
           OR (current_role_name() = 'manager' AND e.manager_id = current_employee_id()))
$$;

ALTER POLICY employees_visible ON company.employees
    USING (company.current_employee_id() IS NOT NULL AND is_active);

ALTER TABLE company.employee_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE company.work_days         ENABLE ROW LEVEL SECURITY;
ALTER TABLE company.employee_events   ENABLE ROW LEVEL SECURITY;

CREATE POLICY requests_visible ON company.employee_requests FOR SELECT USING (employee_id IN (SELECT company.visible_people()));
CREATE POLICY work_days_visible ON company.work_days        FOR SELECT USING (employee_id IN (SELECT company.visible_people()));
CREATE POLICY events_visible ON company.employee_events     FOR SELECT USING (employee_id IN (SELECT company.visible_people()));

-- The API role may write requests, and touch the activity time, only for the caller's own employee.
CREATE POLICY requests_insert_own ON company.employee_requests
    FOR INSERT WITH CHECK (employee_id = company.current_employee_id());
CREATE POLICY requests_update_own ON company.employee_requests
    FOR UPDATE USING (employee_id = company.current_employee_id())
    WITH CHECK (employee_id = company.current_employee_id());
CREATE POLICY employees_touch_own ON company.employees
    FOR UPDATE USING (id = company.current_employee_id())
    WITH CHECK (id = company.current_employee_id());

-- ---------------------------------------------------------------------------
-- Views
-- ---------------------------------------------------------------------------

-- Day-off allowance, working days used and days left, this year, for the caller.
CREATE VIEW company.my_leave_balance AS
WITH me AS (
    SELECT id, hired_at, extract(year FROM current_date)::int AS y
    FROM company.employees WHERE id = company.current_employee_id()
), allowance AS (
    SELECT me.id, me.y,
           CASE WHEN me.y < extract(year FROM me.hired_at) THEN 0
                WHEN me.y > extract(year FROM me.hired_at) THEN (SELECT annual_days FROM company.leave_policy)
                ELSE floor((SELECT annual_days FROM company.leave_policy)
                           * (12 - extract(month FROM me.hired_at) + 1) / 12.0 + 0.5)::int
           END AS allowance
    FROM me
), used AS (
    SELECT a.id, count(*)::int AS used
    FROM allowance a
    JOIN company.employee_requests r
      ON r.employee_id = a.id AND r.kind = 'day_off' AND r.status = 'approved'
    CROSS JOIN LATERAL generate_series(
        greatest(r.starts_on, make_date(a.y, 1, 1))::timestamp,
        least(r.ends_on, make_date(a.y, 12, 31))::timestamp,
        interval '1 day') AS d
    WHERE extract(isodow FROM d) < 6
      AND NOT EXISTS (SELECT 1 FROM company.holidays h WHERE h.day = d::date)
    GROUP BY a.id
)
SELECT 'day_off'::text AS kind, a.allowance, coalesce(u.used, 0) AS used,
       a.allowance - coalesce(u.used, 0) AS remaining
FROM allowance a LEFT JOIN used u ON u.id = a.id;

-- Same view as before plus requests/hours/history. (The manager text lost a stray quote.)
CREATE OR REPLACE VIEW company.my_access AS
    SELECT dataset, visible
    FROM (VALUES
        ('departments, products', 'all of them'),
        ('employees (directory)', 'everyone in the company'),
        ('salaries', CASE WHEN company.current_role_name() IN ('hr', 'admin')
                          THEN 'everyone' ELSE 'only your own' END),
        ('customers, orders', CASE company.current_role_name()
                                  WHEN 'admin' THEN 'the whole company'
                                  WHEN 'manager' THEN 'only your own and your direct reports'
                                  ELSE 'only your own' END),
        ('requests, work hours, history', CASE company.current_role_name()
                                  WHEN 'hr' THEN 'everyone'
                                  WHEN 'admin' THEN 'everyone'
                                  WHEN 'manager' THEN 'only your own and your direct reports'
                                  ELSE 'only your own' END)
    ) AS access (dataset, visible)
    WHERE company.current_employee_id() IS NOT NULL;

-- ---------------------------------------------------------------------------
-- The generator may not rewrite shared (seed) data
-- ---------------------------------------------------------------------------

CREATE FUNCTION company.protect_seed_rows() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF current_user = 'chattie_generator' THEN
        IF TG_OP IN ('UPDATE', 'DELETE') THEN
            IF OLD.origin = 'seed' THEN
                RAISE EXCEPTION 'chattie_generator may not change seed employees' USING ERRCODE = '42501';
            END IF;
        END IF;
        IF TG_OP IN ('INSERT', 'UPDATE') THEN
            IF NEW.origin = 'seed' THEN
                RAISE EXCEPTION 'chattie_generator may not write seed employees' USING ERRCODE = '42501';
            END IF;
        END IF;
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$;

CREATE TRIGGER protect_seed_rows BEFORE INSERT OR UPDATE OR DELETE ON company.employees
    FOR EACH ROW EXECUTE FUNCTION company.protect_seed_rows();

-- History of seed staff is append-only for the generator: new days and orders may be added
-- (world catch-up), existing rows may not be changed or removed. TG_ARGV[0] names the
-- column that points at the employee.
CREATE FUNCTION company.protect_seed_history() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner_origin text;
BEGIN
    IF current_user = 'chattie_generator' THEN
        EXECUTE format('SELECT origin FROM company.employees WHERE id = ($1).%I', TG_ARGV[0])
            INTO owner_origin USING OLD;
        IF owner_origin = 'seed' THEN
            RAISE EXCEPTION 'chattie_generator may not change the history of seed staff' USING ERRCODE = '42501';
        END IF;
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$;

CREATE TRIGGER protect_seed_history BEFORE UPDATE OR DELETE ON company.employee_requests
    FOR EACH ROW EXECUTE FUNCTION company.protect_seed_history('employee_id');
CREATE TRIGGER protect_seed_history BEFORE UPDATE OR DELETE ON company.work_days
    FOR EACH ROW EXECUTE FUNCTION company.protect_seed_history('employee_id');
CREATE TRIGGER protect_seed_history BEFORE UPDATE OR DELETE ON company.employee_events
    FOR EACH ROW EXECUTE FUNCTION company.protect_seed_history('employee_id');
CREATE TRIGGER protect_seed_history BEFORE UPDATE OR DELETE ON company.orders
    FOR EACH ROW EXECUTE FUNCTION company.protect_seed_history('sales_rep_id');
CREATE TRIGGER protect_seed_history BEFORE UPDATE OR DELETE ON company.customers
    FOR EACH ROW EXECUTE FUNCTION company.protect_seed_history('account_manager_id');

-- ---------------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------------

DO $$ BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO chattie_app, chattie_generator', current_database());
END $$;
GRANT USAGE ON SCHEMA company TO chattie_app, chattie_generator;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA company TO chattie_app, chattie_generator;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA company TO chattie_app, chattie_query;

-- chattie_query (read-only, used by the chat SQL tool and the dashboard reads)
GRANT SELECT ON company.employee_requests, company.work_days, company.employee_events,
                company.holidays, company.meta, company.leave_policy, company.my_leave_balance
    TO chattie_query;
GRANT SELECT (origin, is_active) ON company.employees TO chattie_query;

-- chattie_app: reads what it needs, writes requests for the caller only, never deletes
GRANT SELECT ON company.employee_requests, company.work_days, company.employee_events,
                company.holidays, company.leave_policy, company.departments TO chattie_app;
GRANT SELECT (id, department_id, manager_id, name, title, role, hired_at, origin, is_active, last_active_at)
    ON company.employees TO chattie_app;
GRANT INSERT, UPDATE ON company.employee_requests TO chattie_app;
GRANT UPDATE (last_active_at) ON company.employees TO chattie_app;

-- chattie_generator: writes generated rows (bypasses RLS; the triggers above protect seed data)
GRANT SELECT, INSERT, UPDATE, DELETE ON company.employees, company.customers, company.orders,
    company.work_days, company.employee_requests, company.employee_events TO chattie_generator;
GRANT SELECT, INSERT, UPDATE ON company.meta TO chattie_generator;
GRANT SELECT, INSERT ON company.holidays TO chattie_generator;
GRANT SELECT ON company.departments, company.products, company.leave_policy TO chattie_generator;
