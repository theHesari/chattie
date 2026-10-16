from psycopg.conninfo import make_conninfo
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

    # Browser origins allowed to call the API, as a JSON list, e.g. ["http://localhost:3001"].
    CORS_ORIGINS: list[str] = []

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def DATABASE_CONNINFO(self) -> str:
        return make_conninfo(
            host=self.DB_HOST,
            port=self.DB_PORT,
            user=self.DB_USER,
            password=self.DB_PASSWORD,
            dbname=self.DB_NAME,
        )


def get_settings() -> Settings:
    return Settings()
