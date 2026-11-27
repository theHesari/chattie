from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import AsyncExitStack, asynccontextmanager
import logging
from langfuse import Langfuse

from config import Settings
from core_llm import threads
from core_llm.auth import build_jwks_client
from company.ratelimit import SlidingWindowLimiter
from company.routes import router as company_router
from core_llm.builder import build_app_pool, build_db_pool, build_generator_pool, build_llm, build_memory, build_query_pool
from core_llm.graph import build_graph
from core_llm.tools.company_sql import build_company_sql_tool

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
    async with AsyncExitStack() as stack:
        pool = await stack.enter_async_context(build_db_pool(settings))
        query_pool = await stack.enter_async_context(build_query_pool(settings))
        app.state.db_pool = pool
        app.state.query_pool = query_pool
        app.state.memory = await build_memory(pool)
        await threads.setup(pool)
        company_sql = await build_company_sql_tool(query_pool)
        app.state.graph = build_graph(settings, app.state.memory, [company_sql])
        if settings.company_roles_configured:
            app.state.app_pool = await stack.enter_async_context(build_app_pool(settings))
            app.state.generator_pool = build_generator_pool(settings)
            stack.callback(app.state.generator_pool.close)
        else:
            logging.getLogger(__name__).warning(
                "APP_DB_PASSWORD / GENERATOR_DB_PASSWORD are not set: the company endpoints will answer 503")
        yield


def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(title="Chattie API", lifespan=lifespan)
    app.state.settings = settings
    app.state.jwks = build_jwks_client(settings)
    app.state.app_pool = None
    app.state.generator_pool = None
    app.state.request_limiter = SlidingWindowLimiter(limit=20, window_seconds=3600)  # requests per user per hour
    app.state.character_limiter = SlidingWindowLimiter(limit=10, window_seconds=3600)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    @app.exception_handler(RequestValidationError)
    async def validation_failed(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # The default response echoes the rejected input back, which cannot be encoded for values such as
        # NaN (a hostile body then caused a 500). Say where and why, without repeating the input.
        errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    app.include_router(health_router)
    app.include_router(llm_router)
    app.include_router(chat_router)
    app.include_router(company_router)
    return app


app = create_app()
