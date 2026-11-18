"""Credential management endpoints (secrets are write-only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.credential import CredentialCreate, CredentialResponse, CredentialUpdate
from app.services.credentials import (
    create_credential,
    credential_types,
    delete_credential,
    list_credentials,
    serialize_credential,
    update_credential,
)

router = APIRouter()


@router.get("/types")
def get_credential_types(current_user: User = Depends(get_current_user)):
    return {"types": credential_types()}


@router.get("", response_model=list[CredentialResponse])
def get_credentials(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [serialize_credential(item) for item in list_credentials(db, user_id=current_user.id)]


@router.post("", response_model=CredentialResponse, status_code=status.HTTP_201_CREATED)
def create(
    payload: CredentialCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    credential = create_credential(
        db,
        user_id=current_user.id,
        name=payload.name,
        credential_type=payload.type,
        data=payload.data,
    )
    return serialize_credential(credential)


@router.patch("/{credential_id}", response_model=CredentialResponse)
def update(
    credential_id: int,
    payload: CredentialUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    credential = update_credential(
        db,
        user_id=current_user.id,
        credential_id=credential_id,
        name=payload.name,
        data=payload.data,
    )
    return serialize_credential(credential)


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove(
    credential_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    delete_credential(db, user_id=current_user.id, credential_id=credential_id)
    return None
