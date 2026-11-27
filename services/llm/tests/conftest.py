"""Shared fixtures: a throwaway Postgres database per test session and per-role connections.

Tests run against the local Postgres named by DB_* (owner credentials, as in .env) and
never touch the real DB_NAME database: everything happens in `chattie_test_<random>`.
"""

import os
import secrets
from pathlib import Path
from contextlib import asynccontextmanager

import psycopg
import pytest
from dotenv import load_dotenv
from psycopg import sql

# The repo-root .env holds JSON values (e.g. CORS_ORIGINS) that a shell `source` would mangle,
# so it is parsed here. Variables already in the environment (CI) win.
load_dotenv(Path(__file__).resolve().parents[3] / ".env")
# The role names are fixed by the migrations; Settings refuses anything else (see test_settings.py). Tests pin
# them so a mistyped *_USERNAME in a developer's .env cannot break the suite or, worse, be trusted.
os.environ["APP_DB_USERNAME"] = "chattie_app"
os.environ["GENERATOR_DB_USERNAME"] = "chattie_generator"

ROLE_PASSWORD_ENV = {
    "chattie_query": "QUERY_DB_PASSWORD",
    "chattie_app": "APP_DB_PASSWORD",
    "chattie_generator": "GENERATOR_DB_PASSWORD",
}


def _connect_kwargs(dbname: str, **extra) -> dict:
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": os.environ.get("DB_PORT", "5432"),
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
        "dbname": dbname,
        **extra,
    }


@pytest.fixture(scope="session")
def test_db_name():
    name = f"chattie_test_{secrets.token_hex(4)}"
    with psycopg.connect(**_connect_kwargs("postgres"), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            yield name
        finally:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s", (name,)
            )
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))


@pytest.fixture
def owner_conn(test_db_name):
    """A connection to the test database as the owner (autocommit)."""
    with psycopg.connect(**_connect_kwargs(test_db_name), autocommit=True) as conn:
        yield conn


_current_db: dict[str, str | None] = {"name": None}  # set by world_db while a cloned world is in use


@pytest.fixture
def role_conn(test_db_name):
    """`role_conn("chattie_query")` -> async context manager yielding a connection as that role."""

    @asynccontextmanager
    async def connect(role: str):
        password = os.environ[ROLE_PASSWORD_ENV[role]]
        async with await psycopg.AsyncConnection.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=os.environ.get("DB_PORT", "5432"),
            user=role,
            password=password,
            dbname=_current_db["name"] or test_db_name,
        ) as conn:
            yield conn

    return connect


@pytest.fixture
def apply_identity():
    """`await apply_identity(conn, user_id)` sets app.user_id for the current transaction,
    the same way the API does (SET LOCAL with a literal). Call it inside `conn.transaction()`."""

    async def apply(conn, user_id: str | None) -> None:
        await conn.execute(
            sql.SQL("SET LOCAL app.user_id = {}").format(sql.Literal(user_id or ""))
        )

    return apply


# ---------------------------------------------------------------------------
# The company world: built once per session into a template database, cloned per test.
# ---------------------------------------------------------------------------

import datetime as _dt

WORLD_AS_OF = _dt.date(2026, 11, 27)
WORLD_SEED = 42


def _drop_database(admin, name: str) -> None:
    admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s", (name,))
    admin.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))


@pytest.fixture(scope="session")
def world_template(test_db_name):
    """A migrated database holding the generated world; tests get cheap clones of it."""
    from company.generator import build_world
    from db.migrate import apply_migrations

    name = f"{test_db_name}_tpl"
    with psycopg.connect(**_connect_kwargs("postgres"), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            with psycopg.connect(**_connect_kwargs(name), autocommit=True) as conn:
                apply_migrations(conn)
                build_world(conn, seed=WORLD_SEED, as_of=WORLD_AS_OF)
            yield name
        finally:
            _drop_database(admin, name)


@pytest.fixture
def world_db(world_template):
    """Owner connection to a private clone of the generated world (role_conn follows it)."""
    clone = f"chattie_test_{secrets.token_hex(4)}"
    with psycopg.connect(**_connect_kwargs("postgres"), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(sql.Identifier(clone), sql.Identifier(world_template)))
        _current_db["name"] = clone
        conn = psycopg.connect(**_connect_kwargs(clone), autocommit=True)
        try:
            yield conn
        finally:
            conn.close()
            _current_db["name"] = None
            _drop_database(admin, clone)


@pytest.fixture
def link_user():
    """`link_user(owner_conn, user_id, employee_id)`: make an account act as that employee."""

    def link(conn, user_id: str, employee_id: int) -> None:
        conn.execute("UPDATE company.employees SET user_id = NULL WHERE user_id = %s", (user_id,))
        conn.execute("UPDATE company.employees SET user_id = %s WHERE id = %s", (user_id, employee_id))

    return link


@pytest.fixture
def pick_employee():
    """`pick_employee(conn, "role = 'hr'")` -> id of the first employee matching the condition."""

    def pick(conn, condition: str) -> int:
        row = conn.execute(f"SELECT id FROM company.employees WHERE {condition} ORDER BY id LIMIT 1").fetchone()
        assert row, f"no employee matches {condition}"
        return row[0]

    return pick


# ---------------------------------------------------------------------------
# API: the FastAPI app wired to the test database, with a test JWT signing key.
# ---------------------------------------------------------------------------

import time
from types import SimpleNamespace

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


@pytest.fixture(scope="session")
def jwt_private_key():
    return Ed25519PrivateKey.generate()


class _StubJWKS:
    """Stands in for PyJWKClient: always returns the test public key."""

    def __init__(self, public_key):
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token: str):
        return SimpleNamespace(key=self._public_key)


@pytest.fixture
def make_token(jwt_private_key):
    """`make_token("user-1", exp_in=300, aud=..., iss=..., key=...)` -> signed EdDSA bearer token.
    aud/iss default to the app's configured values; the other keyword arguments override claims."""
    from config import Settings

    settings = Settings()

    def make(sub: str, *, exp_in: int = 300, aud: str | None = None, iss: str | None = None, key=None) -> str:
        claims = {
            "sub": sub,
            "aud": aud or settings.AUTH_AUDIENCE,
            "iss": iss or settings.AUTH_ISSUER,
            "exp": int(time.time()) + exp_in,
        }
        return jwt.encode(claims, key or jwt_private_key, algorithm="EdDSA")

    return make


@pytest.fixture
async def api_app(test_db_name, owner_conn, jwt_private_key):
    """The real FastAPI app (no lifespan) with the test DB pool and a stub JWKS."""
    from app import create_app
    from core_llm import threads

    app = create_app()
    app.state.jwks = _StubJWKS(jwt_private_key.public_key())
    conninfo = make_conninfo(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        dbname=test_db_name,
    )
    pool = AsyncConnectionPool(
        conninfo, kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}, open=False
    )
    async with pool:
        await threads.setup(pool)
        owner_conn.execute("TRUNCATE public.chat_threads")
        app.state.db_pool = pool
        yield app


@pytest.fixture
async def client(api_app):
    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture
def generator_conn(world_db):
    """Sync connection as chattie_generator (the runtime role for character generation) to the
    same private clone as world_db."""
    with psycopg.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
        user="chattie_generator",
        password=os.environ["GENERATOR_DB_PASSWORD"],
        dbname=world_db.info.dbname,
        autocommit=True,
    ) as conn:
        yield conn


@pytest.fixture
def db_params():
    """`db_params("name")` -> psycopg connection keyword arguments for that database (owner)."""
    return lambda dbname: _connect_kwargs(dbname)


@pytest.fixture
def scratch_db():
    """`scratch_db()` -> the name of a new empty database, dropped at the end of the test."""
    created: list[str] = []

    def make() -> str:
        name = f"chattie_test_{secrets.token_hex(4)}"
        with psycopg.connect(**_connect_kwargs("postgres"), autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        created.append(name)
        return name

    yield make
    with psycopg.connect(**_connect_kwargs("postgres"), autocommit=True) as admin:
        for name in created:
            _drop_database(admin, name)


# ---------------------------------------------------------------------------
# Company API: the app wired to a private clone of the world, with all four database roles.
# ---------------------------------------------------------------------------

COMPANY_TODAY = _dt.date(2026, 11, 27)


@pytest.fixture
async def company_app(world_db, jwt_private_key):
    """FastAPI app with the owner pool (threads), the read-only and app role pools, the generator
    pool and the stub JWKS, all on `world_db`'s clone. `today` is pinned to COMPANY_TODAY."""
    from app import create_app
    from company import routes
    from company.ratelimit import SlidingWindowLimiter
    from core_llm import threads
    from psycopg_pool import ConnectionPool

    dbname = world_db.info.dbname

    def conninfo(user: str, password: str) -> str:
        return make_conninfo(host=os.environ.get("DB_HOST", "localhost"), port=os.environ.get("DB_PORT", "5432"),
                             user=user, password=password, dbname=dbname)

    app = create_app()
    app.state.jwks = _StubJWKS(jwt_private_key.public_key())
    app.state.request_limiter = SlidingWindowLimiter(limit=20, window_seconds=3600)
    app.state.character_limiter = SlidingWindowLimiter(limit=10, window_seconds=3600)
    app.dependency_overrides[routes.get_today] = lambda: COMPANY_TODAY

    owner = AsyncConnectionPool(conninfo(os.environ["DB_USER"], os.environ["DB_PASSWORD"]),
                                kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}, open=False)
    query = AsyncConnectionPool(conninfo("chattie_query", os.environ["QUERY_DB_PASSWORD"]), kwargs={"prepare_threshold": 0}, open=False)
    writer = AsyncConnectionPool(conninfo("chattie_app", os.environ["APP_DB_PASSWORD"]), kwargs={"prepare_threshold": 0}, open=False)
    generator = ConnectionPool(conninfo("chattie_generator", os.environ["GENERATOR_DB_PASSWORD"]),
                               kwargs={"autocommit": True}, min_size=1, max_size=4, open=True)
    try:
        async with owner, query, writer:
            await threads.setup(owner)
            app.state.db_pool, app.state.query_pool, app.state.app_pool = owner, query, writer
            app.state.generator_pool = generator
            yield app
    finally:
        generator.close()


@pytest.fixture
async def company_client(company_app):
    transport = httpx.ASGITransport(app=company_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
