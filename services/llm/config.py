import warnings

from psycopg.conninfo import make_conninfo
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    OPENROUTER_API_KEY: str
    LLM_BASE_URL: str
    LLM_MODEL: str
    LLM_TEMPERATURE: float

    LANGFUSE_PUBLIC_KEY: str
    LANGFUSE_SECRET_KEY: str
    LANGFUSE_BASE_URL: str

    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str = "chattie"

    # Read-only role for the company SQL tool (created by `make company-db`); same host/port/database.
    QUERY_DB_USER: str = "chattie_query"
    QUERY_DB_PASSWORD: str

    # Roles for the company features (see db/roles.py). Optional so an API started before they exist keeps
    # working; the company endpoints answer 503 until both passwords are set. The usernames are fixed by the
    # database migrations: a different value is ignored with a warning, so the request role can never be the
    # generator role and a stale .env cannot take the API down.
    APP_DB_USERNAME: str = "chattie_app"
    APP_DB_PASSWORD: str | None = None
    GENERATOR_DB_USERNAME: str = "chattie_generator"
    GENERATOR_DB_PASSWORD: str | None = None
    COMPANY_TIMEZONE: str = "UTC"

    # Browser origins allowed to call the API, as a JSON list, e.g. ["http://localhost:3001"].
    CORS_ORIGINS: list[str] = []

    # Bearer tokens are signed by the web app (Better Auth JWT plugin) and verified with its public keys.
    AUTH_JWKS_URL: str
    AUTH_ISSUER: str
    AUTH_AUDIENCE: str

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def _company_roles(self) -> "Settings":
        for field, expected in (("APP_DB_USERNAME", "chattie_app"), ("GENERATOR_DB_USERNAME", "chattie_generator")):
            value = getattr(self, field)
            if not value:
                setattr(self, field, expected)
            elif value != expected:
                warnings.warn(f"{field} is {value!r} in the environment but the role is fixed as {expected!r}; "
                              f"using {expected!r}. Fix the value in .env.", stacklevel=2)
                setattr(self, field, expected)
        for field in ("APP_DB_PASSWORD", "GENERATOR_DB_PASSWORD"):
            if not getattr(self, field):
                setattr(self, field, None)
        return self

    @property
    def company_roles_configured(self) -> bool:
        return bool(self.APP_DB_PASSWORD and self.GENERATOR_DB_PASSWORD)

    @property
    def APP_DATABASE_CONNINFO(self) -> str:
        return make_conninfo(host=self.DB_HOST, port=self.DB_PORT, user=self.APP_DB_USERNAME,
                             password=self.APP_DB_PASSWORD, dbname=self.DB_NAME)

    @property
    def GENERATOR_DATABASE_CONNINFO(self) -> str:
        return make_conninfo(host=self.DB_HOST, port=self.DB_PORT, user=self.GENERATOR_DB_USERNAME,
                             password=self.GENERATOR_DB_PASSWORD, dbname=self.DB_NAME)

    @property
    def DATABASE_CONNINFO(self) -> str:
        return make_conninfo(
            host=self.DB_HOST,
            port=self.DB_PORT,
            user=self.DB_USER,
            password=self.DB_PASSWORD,
            dbname=self.DB_NAME,
        )

    @property
    def QUERY_DATABASE_CONNINFO(self) -> str:
        return make_conninfo(
            host=self.DB_HOST,
            port=self.DB_PORT,
            user=self.QUERY_DB_USER,
            password=self.QUERY_DB_PASSWORD,
            dbname=self.DB_NAME,
        )


def get_settings() -> Settings:
    return Settings()
