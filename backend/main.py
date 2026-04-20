from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.db.session import init_db
from backend.api.routes import router
from backend.api.dependencies import get_retriever, get_reranker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Admin Assistant API…")

    # Init database
    await init_db()
    logger.info("PostgreSQL tables ready.")

    # Warm up singletons (loads models from disk/network once)
    get_retriever()
    logger.info(f"Embedding model loaded: {settings.embedding_model}")
    get_reranker()
    logger.info(f"Reranker model loaded: {settings.reranker_model}")

    logger.info("API ready — listening on %s:%d", settings.api_host, settings.api_port)
    yield

    logger.info("Shutting down.")


app = FastAPI(
    title="Admin Assistant API",
    description=(
        "AI-powered assistant for navigating administrative procedures "
        "(passport renewal, official documents, etc.) "
        "with zero-hallucination RAG and SSE streaming."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        log_level="info",
        loop="asyncio",
    )
