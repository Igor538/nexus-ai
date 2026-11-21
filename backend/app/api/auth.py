"""Authentication, profile and password recovery endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ConflictError, PermissionDeniedError, ValidationError
from app.core.rate_limit import limiter
from app.core.security import (
    constant_time_compare,
    create_access_token,
    generate_reset_code,
    generate_secret,
    hash_password,
    hash_reset_code,
    verify_password,
)
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.schemas.user import (
    PasswordChange,
    PasswordResetConfirm,
    PasswordResetRequest,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
    UserUpdate,
)
from app.services.email_templates import password_reset_code_email
from app.services.mailer import send_email

router = APIRouter()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(user_data: UserCreate, request: Request, db: Session = Depends(get_db)):
    limiter.hit("auth:register", _client_ip(request), settings.auth_rate_limit_per_minute)
    email = str(user_data.email).lower().strip()

    if db.scalar(select(User).where(User.email == email)):
        raise ConflictError("Este e-mail já está cadastrado.")

    user = User(
        name=user_data.name.strip(),
        email=email,
        hashed_password=hash_password(user_data.password),
    )
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("Este e-mail já está cadastrado.") from exc

    return user


@router.post("/login", response_model=TokenResponse)
def login_user(login_data: UserLogin, request: Request, db: Session = Depends(get_db)):
    limiter.hit("auth:login", _client_ip(request), settings.auth_rate_limit_per_minute)
    email = str(login_data.email).lower().strip()
    user = db.scalar(select(User).where(User.email == email))

    if not user or not verify_password(login_data.password, user.hashed_password):
        raise PermissionDeniedError("E-mail ou senha incorretos.")
    if not user.is_active:
        raise PermissionDeniedError("Esta conta está desativada.")

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    return TokenResponse(
        access_token=create_access_token(user.id),
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserResponse)
def update_me(
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.name is not None:
        current_user.name = payload.name.strip()
    if payload.email is not None:
        email = str(payload.email).lower().strip()
        if email != current_user.email and db.scalar(select(User).where(User.email == email)):
            raise ConflictError("Este e-mail já está cadastrado.")
        current_user.email = email
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChange,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    limiter.hit("auth:change-password", str(current_user.id), settings.auth_rate_limit_per_minute)
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise PermissionDeniedError("Senha atual incorreta.")
    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()
    return None


@router.post("/forgot-password")
def forgot_password(
    payload: PasswordResetRequest, request: Request, db: Session = Depends(get_db)
):
    limiter.hit(
        "auth:forgot-password", _client_ip(request), settings.auth_rate_limit_per_minute
    )
    email = str(payload.email).lower().strip()
    user = db.scalar(select(User).where(User.email == email))

    response: dict[str, str] = {
        "detail": "Se o e-mail existir, enviaremos instruções de recuperação."
    }
    if user is None:
        return response

    now = datetime.now(timezone.utc)
    code = generate_reset_code()
    salt = generate_secret(16)
    db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    reset = PasswordResetToken(
        user_id=user.id,
        token_hash=f"{salt}:{hash_reset_code(salt, code)}",
        expires_at=now + timedelta(minutes=settings.password_reset_expire_minutes),
    )
    db.add(reset)
    db.commit()

    content = password_reset_code_email(
        code=code,
        expire_minutes=settings.password_reset_expire_minutes,
        app_name=settings.app_name,
    )
    send_email(
        to=user.email,
        subject=content["subject"],
        text=content["text"],
        html=content["html"],
    )
    return response


@router.post("/reset-password")
def reset_password(
    payload: PasswordResetConfirm, request: Request, db: Session = Depends(get_db)
):
    limiter.hit(
        "auth:reset-password", _client_ip(request), settings.auth_rate_limit_per_minute
    )
    email = str(payload.email).lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    now = datetime.now(timezone.utc)
    reset = None
    if user is not None:
        candidates = db.scalars(
            select(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
            .order_by(PasswordResetToken.created_at.desc())
        ).all()
        for candidate in candidates:
            expires_at = candidate.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < now:
                continue
            try:
                salt, stored = candidate.token_hash.split(":", 1)
            except ValueError:
                continue
            if constant_time_compare(stored, hash_reset_code(salt, payload.code)):
                reset = candidate
                break
    if reset is None or user is None:
        raise ValidationError("Código inválido ou expirado.")

    user.hashed_password = hash_password(payload.new_password)
    reset.used_at = now
    db.commit()
    return {"detail": "Senha redefinida com sucesso."}
