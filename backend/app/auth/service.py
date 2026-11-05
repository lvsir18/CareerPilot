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

    def change_password(
        self,
        user: User,
        current_password: str,
        new_password: str,
        *,
        keep_token: str | None = None,
    ) -> None:
        """Rotate the password after proving knowledge of the current one."""
        if not verify_password(current_password, user.password_hash):
            raise AppError(
                code="INVALID_CREDENTIALS",
                message="当前密码不正确",
                status_code=400,
            )
        self._replace_password(user, new_password, keep_token=keep_token)
        logger.info("password_changed", extra={"user_id": str(user.id)})

    def reset_password(self, email: str, new_password: str) -> User:
        """Forgotten-password path; the API gates it behind a config flag."""
        user = self._find_by_email(normalize_email(email))
        if user is None:
            raise AppError(
                code="ACCOUNT_NOT_FOUND",
                message="该邮箱尚未注册",
                status_code=404,
            )
        self._replace_password(user, new_password)
        logger.info("password_reset", extra={"user_id": str(user.id)})
        return user

    def _replace_password(
        self, user: User, new_password: str, *, keep_token: str | None = None
    ) -> None:
        user.password_hash = hash_password(new_password)
        # Other devices must not keep working with the old password's sessions;
        # the caller's own session stays valid so the UI is not kicked out.
        keep_hash = hash_session_token(keep_token) if keep_token else None
        now = datetime.now(UTC)
        sessions = self._session.scalars(
            select(UserSession).where(
                UserSession.user_id == user.id,
                UserSession.revoked_at.is_(None),
            )
        ).all()
        for row in sessions:
            if keep_hash is not None and row.token_hash == keep_hash:
                continue
            row.revoked_at = now
        self._session.commit()
