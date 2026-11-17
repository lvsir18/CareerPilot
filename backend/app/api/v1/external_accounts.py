"""External account connection metadata API (no credential use yet)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.auth.dependencies import AppSettings, CurrentUser, DbSession
from app.schemas.common import DataResponse
from app.schemas.external_accounts import (
    ExternalAccountCreate,
    ExternalAccountRead,
    connection_to_read,
)
from app.security.csrf import require_csrf
from app.services.external_account_service import ExternalAccountService

router = APIRouter(
    prefix="/external-accounts",
    tags=["external-accounts"],
    dependencies=[Depends(require_csrf)],
)


@router.get(
    "",
    response_model=DataResponse[list[ExternalAccountRead]],
    summary="当前用户的外部账号连接（不返回密钥引用）",
)
def list_connections(
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[list[ExternalAccountRead]]:
    connections = ExternalAccountService(session, settings).list_for_user(user.id)
    return DataResponse(data=[connection_to_read(item) for item in connections])


@router.post(
    "",
    response_model=DataResponse[ExternalAccountRead],
    status_code=status.HTTP_201_CREATED,
    summary="登记授权连接（仅密钥引用，不接收密码）",
)
def create_connection(
    payload: ExternalAccountCreate,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[ExternalAccountRead]:
    connection = ExternalAccountService(session, settings).create_or_update(
        user.id,
        provider=payload.provider,
        auth_mode=payload.auth_mode,
        secret_reference=payload.secret_reference,
        scopes=payload.scopes,
        expires_at=payload.expires_at,
    )
    return DataResponse(data=connection_to_read(connection))


@router.delete(
    "/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="撤销连接并清除密钥引用",
)
def revoke_connection(
    connection_id: UUID,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> None:
    ExternalAccountService(session, settings).revoke(user.id, connection_id)
