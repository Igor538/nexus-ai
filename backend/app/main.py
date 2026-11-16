
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import router as auth_router
from app.api.workflows import router as workflows_router
from app.core.database import Base, engine
from app.models.user import User
from app.models.workflow import Workflow


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Nexus AI",
    description="Intelligent Workflow Automation Platform",
    version="0.1.0",
    lifespan=lifespan,
)


app.include_router(
    auth_router,
    prefix="/api/v1/auth",
    tags=["Authentication"],
)


app.include_router(
    workflows_router,
    prefix="/api/v1/workflows",
    tags=["Workflows"],
)


@app.get("/", tags=["Home"])
async def home():
    return {
        "message": "Welcome to Nexus AI!",
        "version": "0.1.0",
        "status": "online",
    }


@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "healthy",
        "service": "nexus-ai-api",
    }


@app.get("/health/database", tags=["Database"])
def database_health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "database": "postgresql",
            "message": "Database connection successful",
        }

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed",
        )
