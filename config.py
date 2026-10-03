from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    OPENROUTER_API_KEY: str
    LLM_BASE_URL: str
    LLM_MODEL: str
    LLM_TEMPERATURE: float

    LANGFUSE_PUBLIC_KEY: str
    LANGFUSE_SECRET_KEY: str
    LANGFUSE_BASE_URL: str

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def get_settings() -> Settings:
    return Settings()
