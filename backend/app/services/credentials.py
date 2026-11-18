"""Credential storage with encryption at rest and secret-safe serialization."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.core.security import decrypt_json, encrypt_json
from app.models.credential import CREDENTIAL_TYPES, Credential

TYPE_FIELDS: dict[str, dict[str, bool]] = {
    "http_bearer": {"token": True},
    "http_basic": {"username": False, "password": True},
    "api_key": {"api_key": True},
    "discord_webhook": {"url": True},
    "telegram_bot": {"bot_token": True, "chat_id": False},
    "smtp": {"host": False, "port": False, "username": False, "password": True, "from_address": False},
    "google_service_account": {
        "client_email": False,
        "private_key": True,
        "project_id": False,
        "scopes": False,
    },
}

TYPE_LABELS = {
    "http_bearer": "Token Bearer (HTTP)",
    "http_basic": "Usuário e senha (HTTP Basic)",
    "api_key": "Chave de API",
    "discord_webhook": "Webhook do Discord",
    "telegram_bot": "Bot do Telegram",
    "smtp": "Servidor SMTP",
    "google_service_account": "Conta de serviço Google",
}


def credential_types() -> list[dict[str, Any]]:
    return [
        {
            "type": key,
            "label": TYPE_LABELS.get(key, key),
            "fields": [
                {"name": field, "secret": is_secret}
                for field, is_secret in TYPE_FIELDS.get(key, {}).items()
            ],
        }
        for key in CREDENTIAL_TYPES
    ]


def _validate_payload(credential_type: str, data: dict[str, Any]) -> dict[str, Any]:
    if credential_type not in TYPE_FIELDS:
        raise ValidationError(f"Tipo de credencial inválido: {credential_type}")
    expected = TYPE_FIELDS[credential_type]
    cleaned: dict[str, Any] = {}
    for field_name in expected:
        value = data.get(field_name)
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValidationError(f"O campo '{field_name}' é obrigatório para este tipo.")
        cleaned[field_name] = str(value).strip() if not isinstance(value, (int, float)) else value
    return cleaned


def create_credential(
    db: Session, *, user_id: int, name: str, credential_type: str, data: dict[str, Any]
) -> Credential:
    cleaned = _validate_payload(credential_type, data)
    credential = Credential(
        user_id=user_id,
        name=name.strip(),
        type=credential_type,
        encrypted_data=encrypt_json(json.dumps(cleaned).encode("utf-8")),
        metadata_json={"fields": list(cleaned.keys())},
    )
    db.add(credential)
    db.commit()
    db.refresh(credential)
    return credential


def update_credential(
    db: Session, *, user_id: int, credential_id: int, name: str | None, data: dict[str, Any] | None
) -> Credential:
    credential = get_credential(db, user_id=user_id, credential_id=credential_id)
    if name:
        credential.name = name.strip()
    if data is not None:
        merged = {**decrypt_credential(credential), **data}
        cleaned = _validate_payload(credential.type, merged)
        credential.encrypted_data = encrypt_json(json.dumps(cleaned).encode("utf-8"))
        credential.metadata_json = {"fields": list(cleaned.keys())}
    db.commit()
    db.refresh(credential)
    return credential


def get_credential(db: Session, *, user_id: int, credential_id: int) -> Credential:
    credential = db.scalar(
        select(Credential).where(Credential.id == credential_id, Credential.user_id == user_id)
    )
    if credential is None:
        raise NotFoundError("Credencial não encontrada.")
    return credential


def delete_credential(db: Session, *, user_id: int, credential_id: int) -> None:
    credential = get_credential(db, user_id=user_id, credential_id=credential_id)
    db.delete(credential)
    db.commit()


def list_credentials(db: Session, *, user_id: int) -> list[Credential]:
    return list(
        db.scalars(
            select(Credential).where(Credential.user_id == user_id).order_by(Credential.created_at.desc())
        ).all()
    )


def decrypt_credential(credential: Credential) -> dict[str, Any]:
    return json.loads(decrypt_json(credential.encrypted_data).decode("utf-8"))


def resolve_credential_data(
    db: Session, *, user_id: int, credential_id: int, expected_type: str | None = None
) -> dict[str, Any]:
    credential = get_credential(db, user_id=user_id, credential_id=credential_id)
    if expected_type and credential.type != expected_type:
        raise ValidationError(
            f"A credencial selecionada é do tipo '{credential.type}', esperado '{expected_type}'."
        )
    return decrypt_credential(credential)


def serialize_credential(credential: Credential) -> dict[str, Any]:
    fields = sorted((credential.metadata_json or {}).get("fields", []))
    return {
        "id": credential.id,
        "name": credential.name,
        "type": credential.type,
        "fields": fields,
        "metadata": {"type_label": TYPE_LABELS.get(credential.type, credential.type)},
        "created_at": credential.created_at,
        "updated_at": credential.updated_at,
    }
