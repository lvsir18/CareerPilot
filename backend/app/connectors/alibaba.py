"""Alibaba Group official TOP API connector.

Uses the documented, free, no-user-authorization endpoint
``alibaba.recruit.position.pagesearch`` on the Alibaba/Taobao open platform.
An application key/secret and a ``tenant_id`` supplied by the partner are still
required; without them the connector reports "not configured" and never makes a
request.

Docs: https://developer.alibaba.com/docs/api.htm?apiId=61394 (retrieved 2026-10-21).
The API does not return a publish timestamp, so ``published_at`` stays ``None``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.connectors.errors import ConnectorAuthError, ConnectorNotConfigured, ConnectorParseError
from app.connectors.http import SafeHttpClient
from app.connectors.schemas import ConnectorHealth, RawJob
from app.core.config import Settings
from app.db.models.enums import JobSourceMethod, JobStatus, VerificationStatus

GATEWAY_URL = "https://eco.taobao.com/router/rest"
API_METHOD = "alibaba.recruit.position.pagesearch"
ALLOWED_HOSTS = {"eco.taobao.com"}


def _sign(params: dict[str, str], app_secret: str) -> str:
    base = "".join(f"{key}{value}" for key, value in sorted(params.items()) if key != "sign")
    return (
        hmac.new(app_secret.encode("utf-8"), base.encode("utf-8"), hashlib.md5).hexdigest().upper()
    )


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in (
            "official_position_detail_d_t_o",
            "position_detail_d_t_o",
            "string",
            "data",
        ):
            nested = value.get(key)
            if isinstance(nested, list):
                return nested
        return [value]
    return [value]


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


class AlibabaTopConnector:
    source_type = "alibaba_openapi"

    def __init__(self, settings: Settings, client: SafeHttpClient | None = None) -> None:
        self._settings = settings
        self._client = client or SafeHttpClient(
            allowed_hosts=ALLOWED_HOSTS,
            user_agent=settings.connector_user_agent,
            timeout_seconds=settings.connector_timeout_seconds,
            max_retries=settings.connector_max_retries,
            backoff_seconds=settings.connector_backoff_seconds,
            min_interval_seconds=settings.connector_min_interval_seconds,
            max_response_bytes=settings.connector_max_response_bytes,
        )

    def _resolve_config(self, source_config: dict[str, Any]) -> dict[str, str]:
        app_key = source_config.get("app_key") or self._settings.alibaba_app_key
        app_secret = source_config.get("app_secret") or self._settings.alibaba_app_secret
        tenant_id = source_config.get("tenant_id") or self._settings.alibaba_tenant_id
        url_template = source_config.get("position_url_template") or (
            self._settings.alibaba_position_url_template
        )
        missing = [
            name
            for name, value in (
                ("ALIBABA_APP_KEY", app_key),
                ("ALIBABA_APP_SECRET", app_secret),
                ("ALIBABA_TENANT_ID", tenant_id),
                ("ALIBABA_POSITION_URL_TEMPLATE", url_template),
            )
            if not value
        ]
        if missing:
            raise ConnectorNotConfigured("缺少阿里官方 API 配置: " + ", ".join(missing))
        return {
            "app_key": str(app_key),
            "app_secret": str(app_secret),
            "tenant_id": str(tenant_id),
            "position_url_template": str(url_template),
        }

    def _call_page(
        self,
        config: dict[str, str],
        *,
        page_index: int,
        page_size: int,
        keyword: str | None,
    ) -> dict[str, Any]:
        query: dict[str, Any] = {
            "page_index": page_index,
            "page_size": page_size,
            "tenant_id": config["tenant_id"],
        }
        if keyword:
            query["keywords"] = keyword

        params: dict[str, str] = {
            "method": API_METHOD,
            "app_key": config["app_key"],
            "sign_method": "hmac",
            "timestamp": datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S"),
            "format": "json",
            "v": "2.0",
            "simplify": "true",
            "partner_id": "careerpilot",
            "param_official_position_page_query_param": json.dumps(
                query, ensure_ascii=False, separators=(",", ":")
            ),
        }
        params["sign"] = _sign(params, config["app_secret"])

        payload = self._client.post_form(GATEWAY_URL, params)
        if "error_response" in payload:
            error = payload["error_response"]
            message = str(error.get("sub_msg") or error.get("msg") or "阿里 API 调用失败")
            sub_code = str(error.get("sub_code") or "")
            if "auth" in sub_code or "permission" in sub_code:
                raise ConnectorAuthError(message)
            raise ConnectorParseError(message)

        response = payload.get("alibaba_recruit_position_pagesearch_response")
        if not isinstance(response, dict):
            raise ConnectorParseError("阿里 API 响应缺少 pagesearch 对象")
        if response.get("result_code") not in (None, "success"):
            raise ConnectorParseError(str(response.get("result_message") or "阿里 API 返回失败"))
        data = response.get("data")
        if not isinstance(data, dict):
            raise ConnectorParseError("阿里 API 响应缺少 data")
        return data

    def fetch_jobs(self, source_config: dict[str, Any]) -> list[RawJob]:
        config = self._resolve_config(source_config)
        page_size = int(source_config.get("page_size", self._settings.connector_page_size))
        max_pages = int(source_config.get("max_pages", self._settings.connector_max_pages))
        keyword = source_config.get("keyword")
        source_key = str(source_config.get("source_key") or "alibaba-careers")

        jobs: list[RawJob] = []
        for page_index in range(1, max_pages + 1):
            data = self._call_page(
                config,
                page_index=page_index,
                page_size=page_size,
                keyword=str(keyword) if keyword else None,
            )
            records = _as_list(data.get("records"))
            if not records:
                break
            for record in records:
                if not isinstance(record, dict):
                    continue
                job = self._parse_record(record, config, source_key)
                if job is not None:
                    jobs.append(job)
            total_pages = data.get("total_page")
            if isinstance(total_pages, int) and page_index >= total_pages:
                break
        return jobs

    def _parse_record(
        self, record: dict[str, Any], config: dict[str, str], source_key: str
    ) -> RawJob | None:
        position_id = _text(record.get("position_id")) or _text(record.get("position_code"))
        title = _text(record.get("name"))
        if not position_id or not title:
            return None

        intro = record.get("position_intro")
        intro = intro if isinstance(intro, dict) else {}
        description_parts = [
            _text(intro.get("team_intro")),
            _text(intro.get("job_desc")),
        ]
        requirement_text = _text(intro.get("requirement_desc"))
        requirements = [
            line.strip() for line in (requirement_text or "").splitlines() if line.strip()
        ]

        work_areas = record.get("work_areas")
        work_areas = work_areas if isinstance(work_areas, dict) else {}
        city = _text(work_areas.get("name"))
        location_text = _text(work_areas.get("full_name")) or city

        position_code = _text(record.get("position_code")) or ""
        try:
            source_url = config["position_url_template"].format(
                position_id=position_id,
                position_code=position_code,
                source_job_id=position_id,
            )
        except (KeyError, IndexError) as exc:
            raise ConnectorParseError("ALIBABA_POSITION_URL_TEMPLATE 占位符无效") from exc

        return RawJob(
            source_type=self.source_type,
            source_key=source_key,
            source_job_id=position_id,
            company="阿里巴巴集团",
            title=title,
            source_url=source_url,
            description="\n".join(part for part in description_parts if part) or None,
            department=_text(record.get("department_name"))
            or _text(record.get("position_category")),
            location_text=location_text,
            city=city,
            job_type=None,
            recruitment_program=None,
            requirements=requirements,
            published_at=None,  # API does not expose a publish timestamp
            raw_payload=record,
            is_demo=False,
            status=JobStatus.UNKNOWN,
            source_method=JobSourceMethod.API,
            verification_status=VerificationStatus.VERIFIED,
            verified_at=datetime.now(ZoneInfo("UTC")),
        )

    def fetch_job_detail(self, source_job_id: str, source_config: dict[str, Any]) -> RawJob | None:
        # The list endpoint already returns full JD fields for each record.
        return next(
            (job for job in self.fetch_jobs(source_config) if job.source_job_id == source_job_id),
            None,
        )

    def health_check(self, source_config: dict[str, Any]) -> ConnectorHealth:
        try:
            self._resolve_config(source_config)
        except ConnectorNotConfigured as exc:
            return ConnectorHealth(configured=False, ok=False, message=exc.message)
        return ConnectorHealth(
            configured=True,
            ok=True,
            message="阿里官方 TOP API 配置完整（尚未执行在线校验）",
        )
