"""Authentication, profile and password recovery flows."""

from __future__ import annotations

import uuid

from conftest import API


def _register(client, email: str | None = None, password: str = "SenhaSegura123!"):
    email = email or f"auth-{uuid.uuid4().hex[:10]}@nexustest.com"
    response = client.post(
        f"{API}/auth/register",
        json={"name": "Pessoa Teste", "email": email, "password": password},
    )
    return email, password, response


def test_register_and_login(client):
    email, password, response = _register(client)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == email
    assert "hashed_password" not in body

    duplicate = client.post(
        f"{API}/auth/register",
        json={"name": "Outra", "email": email, "password": password},
    )
    assert duplicate.status_code == 409

    login = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    token = login.json()
    assert token["token_type"] == "bearer"
    assert token["expires_in"] > 0

    wrong = client.post(
        f"{API}/auth/login", json={"email": email, "password": "senha-errada"}
    )
    assert wrong.status_code == 403


def test_me_profile_and_password_change(client):
    email, password, _ = _register(client)
    login = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    me = client.get(f"{API}/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == email

    updated = client.patch(
        f"{API}/auth/me", json={"name": "Nome Atualizado"}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Nome Atualizado"

    changed = client.post(
        f"{API}/auth/change-password",
        json={"current_password": password, "new_password": "NovaSenha456!"},
        headers=headers,
    )
    assert changed.status_code == 204

    assert (
        client.post(f"{API}/auth/login", json={"email": email, "password": password}).status_code
        == 403
    )
    assert (
        client.post(
            f"{API}/auth/login", json={"email": email, "password": "NovaSenha456!"}
        ).status_code
        == 200
    )


def test_password_reset_with_dev_token(client):
    email, password, _ = _register(client)
    forgot = client.post(f"{API}/auth/forgot-password", json={"email": email})
    assert forgot.status_code == 200
    token = forgot.json().get("dev_token")
    assert token

    reset = client.post(
        f"{API}/auth/reset-password",
        json={"token": token, "new_password": "Redefinida789!"},
    )
    assert reset.status_code == 200

    assert (
        client.post(
            f"{API}/auth/login", json={"email": email, "password": "Redefinida789!"}
        ).status_code
        == 200
    )
    repeated = client.post(
        f"{API}/auth/reset-password",
        json={"token": token, "new_password": "OutraSenha000!"},
    )
    assert repeated.status_code == 422 or repeated.status_code == 400


def test_requires_authentication(client):
    assert client.get(f"{API}/auth/me").status_code == 401
    assert client.get(f"{API}/workflows").status_code == 401
    bad = client.get(
        f"{API}/auth/me", headers={"Authorization": "Bearer token-invalido"}
    )
    assert bad.status_code == 401

