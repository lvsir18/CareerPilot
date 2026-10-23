"""Authentication domain service."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password, verify_password
from app.auth.session import generate_session_token, hash_session_token, session_expiry
from app.core.config import Settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.models.user import User, UserSession

logger = get_logger(__name__)


def normalize_email(email: str) -> str:
    return email.strip().lower()


class AuthService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def _find_by_email(self, email: str) -> User | None:
        return self._session.scalar(select(User).where(User.email == email))

    def _issue_session(self, user: User) -> str:
        token = generate_session_token()
        self._session.add(
            UserSession(
                user_id=user.id,
                token_hash=hash_session_token(token),
                expires_at=session_expiry(self._settings),
            )
        )
        return token

    def register(self, email: str, password: str) -> tuple[User, str]:
        normalized = normalize_email(email)
        if self._find_by_email(normalized) is not None:
            raise AppError(
                code="EMAIL_ALREADY_REGISTERED",
                message="该邮箱已注册，请直接登录",
                status_code=409,
            )

        user = User(email=normalized, password_hash=hash_password(password))
        self._session.add(user)
        try:
            self._session.flush()
        except IntegrityError as exc:  # concurrent registration
            self._session.rollback()
            raise AppError(
                code="EMAIL_ALREADY_REGISTERED",
                message="该邮箱已注册，请直接登录",
                status_code=409,
            ) from exc

        token = self._issue_session(user)
        self._session.commit()
        self._session.refresh(user)
        logger.info("user_registered", extra={"user_id": str(user.id)})
        return user, token

    def login(self, email: str, password: str) -> tuple[User, str]:
        user = self._find_by_email(normalize_email(email))
        # Same error for unknown email and wrong password (no account enumeration).
        if user is None or not verify_password(password, user.password_hash):
            raise AppError(
                code="INVALID_CREDENTIALS",
                message="邮箱或密码错误",
                status_code=401,
            )

        token = self._issue_session(user)
        self._session.commit()
        self._session.refresh(user)
        logger.info("user_logged_in", extra={"user_id": str(user.id)})
        return user, token

    def logout(self, token: str | None) -> None:
        if not token:
            return
        session_row = self._session.scalar(
            select(UserSession).where(UserSession.token_hash == hash_session_token(token))
        )
        if session_row is None or session_row.revoked_at is not None:
            return
        session_row.revoked_at = datetime.now(UTC)
        self._session.commit()

    def resolve_session(self, token: str | None) -> User | None:
        if not token:
            return None
        return self._session.scalar(
            select(User)
            .join(UserSession, UserSession.user_id == User.id)
            .where(
                UserSession.token_hash == hash_session_token(token),
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > datetime.now(UTC),
            )
        )
