from fastapi import FastAPI
from contextlib import asynccontextmanager
from langfuse import Langfuse

from config import Settings
from core_llm.builder import build_llm, build_memory

from ops.health import router as health_router
from core_llm.chain import router as llm_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    app.state.settings = settings
    app.state.llm = build_llm(settings)
    app.state.memory = build_memory(settings)
    app.state.langfuse = Langfuse(
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY,
        host=settings.LANGFUSE_BASE_URL,
    )
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Chattie API", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(llm_router)
    return app


app = create_app()
