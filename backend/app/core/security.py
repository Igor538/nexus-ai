"""Password hashing, JWT issuance and encryption helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.fernet import Fernet, InvalidToken
from pwdlib import PasswordHash

from app.core.config import settings

password_hash = PasswordHash.recommended()

SECRET_KEY = settings.jwt_secret_key
ALGORITHM = settings.jwt_algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes


class EncryptionError(RuntimeError):
    pass


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return password_hash.verify(password, hashed_password)
    except Exception:
        return False


def create_access_token(user_id: int, token_type: str = "access") -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_secret(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def constant_time_compare(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def sign_payload(secret: str, timestamp: str, body: bytes) -> str:
    message = timestamp.encode("utf-8") + b"." + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_signature(secret: str, timestamp: str, body: bytes, signature: str) -> bool:
    expected = sign_payload(secret, timestamp, body)
    provided = signature.strip()
    if provided.startswith("sha256="):
        provided = provided[len("sha256=") :]
    return constant_time_compare(expected, provided)


def _fernet() -> Fernet:
    raw_key = settings.credentials_encryption_key
    if not raw_key:
        raise EncryptionError(
            "CREDENTIALS_ENCRYPTION_KEY is not configured. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"`."
        )
    key = raw_key.encode("utf-8")
    try:
        return Fernet(key)
    except (ValueError, TypeError) as exc:  # pragma: no cover - config error path
        raise EncryptionError("CREDENTIALS_ENCRYPTION_KEY is not a valid Fernet key.") from exc


def encrypt_json(payload: bytes) -> str:
    return _fernet().encrypt(payload).decode("utf-8")


def decrypt_json(token: str) -> bytes:
    try:
        return _fernet().decrypt(token.encode("utf-8"))
    except InvalidToken as exc:
        raise EncryptionError("Stored credential could not be decrypted.") from exc


def generate_encryption_key() -> str:
    return Fernet.generate_key().decode("utf-8")


def b64_sha256(value: bytes) -> str:
    return base64.b64encode(hashlib.sha256(value).digest()).decode("utf-8")
