"""Nexus AI — FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401  (register ORM metadata)
from app.api import (
    ai,
    auth,
    credentials,
    dashboard,
    executions,
    health,
    nodes,
    notifications,
    webhooks,
    workflows,
)
from app.core.config import settings
from app.core.database import Base, engine
from app.core.errors import install_exception_handlers
from app.core.logging import RequestContextMiddleware, configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)
        logger.info("database_tables_ensured")
    yield


app = FastAPI(
    title=settings.app_name,
    description="Plataforma de automação de workflows com inteligência artificial.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

install_exception_handlers(app)

app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(auth.router, prefix=f"{settings.api_v1_prefix}/auth", tags=["Auth"])
app.include_router(workflows.router, prefix=f"{settings.api_v1_prefix}/workflows", tags=["Workflows"])
app.include_router(executions.router, prefix=f"{settings.api_v1_prefix}/executions", tags=["Executions"])
app.include_router(credentials.router, prefix=f"{settings.api_v1_prefix}/credentials", tags=["Credentials"])
app.include_router(webhooks.router, prefix=f"{settings.api_v1_prefix}/webhooks", tags=["Webhooks"])
app.include_router(nodes.router, prefix=f"{settings.api_v1_prefix}/nodes", tags=["Nodes"])
app.include_router(ai.router, prefix=f"{settings.api_v1_prefix}/ai", tags=["AI"])
app.include_router(
    notifications.router, prefix=f"{settings.api_v1_prefix}/notifications", tags=["Notifications"]
)
app.include_router(dashboard.router, prefix=f"{settings.api_v1_prefix}/dashboard", tags=["Dashboard"])


@app.get("/", tags=["Health"])
def root():
    return {
        "name": settings.app_name,
        "status": "online",
        "docs": "/docs",
        "version": "1.0.0",
    }
