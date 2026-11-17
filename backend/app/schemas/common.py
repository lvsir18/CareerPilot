"""Shared response envelopes."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DataResponse[T](BaseModel):
    data: T


class PageMeta(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)


class Page[T](BaseModel):
    data: list[T]
    meta: PageMeta
