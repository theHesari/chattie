from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from langfuse import Langfuse

from config import Settings
from core_llm import threads
from core_llm.builder import build_db_pool, build_llm, build_memory
from core_llm.graph import build_graph

from ops.health import router as health_router
from core_llm.routes import router as llm_router
from core_llm.chat import router as chat_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = app.state.settings
    app.state.llm = build_llm(settings)
    app.state.langfuse = Langfuse(
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY,
        host=settings.LANGFUSE_BASE_URL,
    )
    async with build_db_pool(settings) as pool:
        app.state.db_pool = pool
        app.state.memory = await build_memory(pool)
        await threads.setup(pool)
        app.state.graph = build_graph(settings, app.state.memory)
        yield


def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(title="Chattie API", lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(health_router)
    app.include_router(llm_router)
    app.include_router(chat_router)
    return app


app = create_app()
