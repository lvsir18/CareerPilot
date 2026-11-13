"""Authentication request/response contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: Password = Field(description="至少 8 个字符")

    @field_validator("password")
    @classmethod
    def _password_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("密码不能全为空白字符")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


def _ensure_not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("密码不能全为空白字符")
    return value


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: Password

    @field_validator("new_password")
    @classmethod
    def _new_password_not_blank(cls, value: str) -> str:
        return _ensure_not_blank(value)


class PasswordResetRequest(BaseModel):
    email: EmailStr
    new_password: Password

    @field_validator("new_password")
    @classmethod
    def _new_password_not_blank(cls, value: str) -> str:
        return _ensure_not_blank(value)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    created_at: datetime
    # Only the /auth/me response fills this: the UI hides library-wide archive
    # actions from non-admins instead of letting them click into a 403.
    is_admin: bool = False
