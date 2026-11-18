"""Shared pytest fixtures for API and service tests."""

from __future__ import annotations

import os
import tempfile
import time
import uuid
from pathlib import Path

from cryptography.fernet import Fernet

_TEST_DIR = Path(tempfile.mkdtemp(prefix="nexus-tests-"))
_TEST_DB = _TEST_DIR / "nexus.db"

os.environ.update(
    {
        "APP_ENV": "test",
        "DEBUG": "false",
        "DATABASE_URL": f"sqlite:///{_TEST_DB.as_posix()}",
        "REDIS_URL": "redis://localhost:6379/15",
        "JWT_SECRET_KEY": "test-secret-key-with-at-least-thirty-two-characters",
        "JWT_ALGORITHM": "HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
        "CREDENTIALS_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "EXECUTION_MODE": "inline",
        "EXECUTION_TIMEOUT_SECONDS": "60",
        "MAX_ACTIVE_EXECUTIONS_PER_WORKFLOW": "1",
        "AUTO_CREATE_TABLES": "true",
        "RATE_LIMIT_ENABLED": "false",
        "AI_DAILY_TOKEN_LIMIT": "100000",
        "WEBHOOK_BASE_URL": "http://testserver",
        "SMTP_HOST": "",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

API = "/api/v1"
TERMINAL_STATUSES = {"success", "failed", "cancelled"}


@pytest.fixture(scope="session", autouse=True)
def _database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def user(client):
    email = f"user-{uuid.uuid4().hex[:10]}@nexustest.com"
    password = "SenhaSegura123!"
    response = client.post(
        f"{API}/auth/register",
        json={"name": "Usuário de Teste", "email": email, "password": password},
    )
    assert response.status_code == 201, response.text
    login = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {
        "email": email,
        "password": password,
        "id": response.json()["id"],
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def make_workflow(client, user):
    def _make(graph: dict | None = None, *, name: str | None = None, active: bool = True):
        payload = {"name": name or f"Fluxo {uuid.uuid4().hex[:6]}"}
        if graph is not None:
            payload["graph"] = graph
        response = client.post(
            f"{API}/workflows", json=payload, headers=user["headers"]
        )
        assert response.status_code == 201, response.text
        workflow = response.json()
        if not active:
            updated = client.patch(
                f"{API}/workflows/{workflow['id']}",
                json={"is_active": False},
                headers=user["headers"],
            )
            assert updated.status_code == 200, updated.text
            workflow = updated.json()
        return workflow

    return _make


@pytest.fixture
def wait_execution(client, user):
    def _wait(execution_id: int, timeout: float = 15.0) -> dict:
        deadline = time.time() + timeout
        last: dict = {}
        while time.time() < deadline:
            response = client.get(
                f"{API}/executions/{execution_id}", headers=user["headers"]
            )
            assert response.status_code == 200, response.text
            last = response.json()
            if last["status"] in TERMINAL_STATUSES:
                return last
            time.sleep(0.1)
        raise AssertionError(f"Execução {execution_id} não terminou: {last}")

    return _wait

