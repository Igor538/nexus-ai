"""Security primitives: password hashing, tokens, encryption and signatures."""

from __future__ import annotations

import time

import pytest

from app.core.security import (
    EncryptionError,
    constant_time_compare,
    create_access_token,
    decode_token,
    decrypt_json,
    encrypt_json,
    generate_encryption_key,
    generate_secret,
    hash_password,
    hash_token,
    sign_payload,
    verify_password,
    verify_signature,
)


def test_password_hash_roundtrip():
    hashed = hash_password("SenhaSegura123!")
    assert hashed != "SenhaSegura123!"
    assert verify_password("SenhaSegura123!", hashed)
    assert not verify_password("outra", hashed)


def test_access_token_roundtrip_and_type():
    token = create_access_token(42)
    payload = decode_token(token)
    assert payload["sub"] == "42"
    assert payload["type"] == "access"

    reset = create_access_token(42, token_type="reset")
    assert decode_token(reset)["type"] == "reset"


def test_token_hash_and_secret_generation():
    token = generate_secret(24)
    assert len(token) >= 24
    assert hash_token(token) == hash_token(token)
    assert hash_token(token) != token
    assert constant_time_compare("abc", "abc")
    assert not constant_time_compare("abc", "abd")


def test_fernet_encryption_roundtrip():
    token = encrypt_json(b'{"api_key": "segredo"}')
    assert "segredo" not in token
    assert decrypt_json(token) == b'{"api_key": "segredo"}'


def test_fernet_requires_valid_key(monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "credentials_encryption_key", None)
    with pytest.raises(EncryptionError):
        encrypt_json(b"x")
    assert generate_encryption_key()


def test_hmac_signature_verification():
    secret = generate_secret(24)
    body = b'{"evento": "teste"}'
    timestamp = str(int(time.time()))
    signature = sign_payload(secret, timestamp, body)
    assert verify_signature(secret, timestamp, body, signature)
    assert verify_signature(secret, timestamp, body, f"sha256={signature}")
    assert not verify_signature(secret, timestamp, b"outro", signature)
    assert not verify_signature("outro-segredo", timestamp, body, signature)
