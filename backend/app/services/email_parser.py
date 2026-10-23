"""Safe .eml parsing for recruitment notifications.

The parser never renders HTML, fetches external resources, executes scripts or
treats email content as instructions. It extracts a small structured preview;
the user must explicitly confirm any application update.
"""

from __future__ import annotations

import email
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email import policy
from email.header import decode_header
from email.message import Message
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

from app.db.models.enums import ApplicationStatus
from app.search.domains import COMPANY_DOMAINS, COMPANY_NAMES

MAX_SUBJECT = 500
MAX_BODY_EXCERPT = 2_000
MAX_PARSE_TEXT = 30_000

_KNOWN_COMPANIES = set(COMPANY_NAMES.values()) | {
    "字节跳动",
    "腾讯",
    "阿里巴巴",
    "美团",
    "百度",
    "快手",
    "小红书",
    "拼多多",
    "华为",
    "京东",
    "网易",
    "滴滴",
    "小米",
    "哔哩哔哩",
    "DeepSeek",
    "深度求索",
    "月之暗面",
    "智谱",
}
_TITLE_PATTERNS = (
    re.compile(r"(?:应聘|申请|投递)?(?:岗位|职位)[:：]\s*([^\n\r，。；;]{2,80})"),
    re.compile(r"(?:position|role)[:：]\s*([^\n\r,;]{2,80})", re.IGNORECASE),
)
_DATE_PATTERNS = (
    re.compile(r"(20\d{2})[年/-](\d{1,2})[月/-](\d{1,2})日?(?:\s*(\d{1,2})[:：](\d{2}))?"),
)

_STATUS_RULES: tuple[tuple[ApplicationStatus, tuple[str, ...]], ...] = (
    (
        ApplicationStatus.OFFER,
        (
            "录用通知",
            "录用offer",
            "offer letter",
            "发放offer",
            "发放录用通知",
            "已录用",
            "录取通知",
            "恭喜您被录用",
            "正式录用",
        ),
    ),
    (
        ApplicationStatus.REJECTED,
        ("未通过", "不匹配", "不再推进", "流程终止", "遗憾地通知", "感谢信"),
    ),
    (
        ApplicationStatus.INTERVIEW,
        ("面试邀请", "进入面试", "安排面试", "面试通知", "面试时间"),
    ),
    (
        ApplicationStatus.ASSESSMENT,
        ("笔试", "在线测评", "测评邀请", "在线考试"),
    ),
    (
        ApplicationStatus.SCREENING,
        ("简历筛选中", "正在筛选"),
    ),
    (
        ApplicationStatus.APPLIED,
        ("申请已提交", "投递成功", "已收到您的申请", "申请已收到"),
    ),
)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style"}:
            self._skip_depth += 1
        elif tag.lower() in {"p", "div", "br", "li", "tr", "h1", "h2", "h3"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


@dataclass(frozen=True)
class ParsedEmail:
    subject: str | None
    sender: str | None
    received_at: datetime | None
    company: str | None
    title: str | None
    status: ApplicationStatus | None
    event_time: datetime | None
    confidence: float
    evidence_summary: str
    body_excerpt: str | None
    warnings: list[str] = field(default_factory=list)


def _decode_header(value: str | None) -> str | None:
    if not value:
        return None
    parts: list[str] = []
    try:
        for chunk, charset in decode_header(value):
            if isinstance(chunk, bytes):
                parts.append(chunk.decode(charset or "utf-8", errors="replace"))
            else:
                parts.append(chunk)
    except Exception:
        return value.strip()[:MAX_SUBJECT]
    cleaned = re.sub(r"\s+", " ", "".join(parts)).strip()
    return cleaned[:MAX_SUBJECT] or None


def _part_text(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _body_text(message: Message) -> str:
    plain: list[str] = []
    html: list[str] = []
    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type == "text/plain":
            plain.append(_part_text(part))
        elif content_type == "text/html":
            html.append(_part_text(part))
    if plain:
        return "\n".join(plain)
    if html:
        extractor = _HTMLTextExtractor()
        for document in html:
            try:
                extractor.feed(document)
            except Exception:
                continue
        return extractor.text()
    payload = message.get_payload(decode=True)
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="replace")
    return ""


def _clean_text(value: str) -> str:
    value = value.replace("\x00", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()[:MAX_PARSE_TEXT]


_RECRUIT_CONTEXT = (
    "招聘",
    "岗位",
    "职位",
    "面试",
    "笔试",
    "测评",
    "简历",
    "投递",
    "申请",
    "实习",
    "校招",
    "校园招聘",
    "录用",
    "录取",
    "面试邀请",
    "笔试邀请",
)


def _company_from_sender(sender: str | None) -> str | None:
    """Resolve a company from the sender domain (e.g. hr@bytedance.com)."""
    if not sender:
        return None
    match = re.search(r"@([A-Za-z0-9.-]+)", sender)
    if not match:
        return None
    host = match.group(1).lower().rstrip(".")
    parts = host.split(".")
    root = ".".join(parts[-2:]) if len(parts) >= 2 else host
    for company_key, domains in COMPANY_DOMAINS.items():
        for domain in domains:
            if domain == root or domain.endswith(f".{root}") or root.endswith(f".{domain}"):
                return COMPANY_NAMES.get(company_key, company_key)
    return None


def _extract_company(text: str) -> str | None:
    """Only attribute a company when the mail carries recruiting context.

    Prevents marketing/notification mail (e.g. NVIDIA newsletters mentioning
    "360", or Tencent account-security alerts) from being mapped to a company.
    """
    if not any(word in text for word in _RECRUIT_CONTEXT):
        return None
    for company in sorted(_KNOWN_COMPANIES, key=len, reverse=True):
        if company and company.casefold() in text.casefold():
            return company
    return None


def _extract_title(subject: str | None, body: str) -> str | None:
    haystack = f"{subject or ''}\n{body}"
    for pattern in _TITLE_PATTERNS:
        match = pattern.search(haystack)
        if match:
            return match.group(1).strip()[:300]
    return None


def _extract_status(text: str) -> tuple[ApplicationStatus | None, str | None]:
    lowered = text.casefold()
    for status, keywords in _STATUS_RULES:
        if any(keyword.casefold() in lowered for keyword in keywords):
            return status, None
    if any(phrase in text for phrase in ("简历已收到", "简历已接收", "已收到您的简历")):
        return None, "邮件只确认收到简历，不能推断通过筛选或进入下一阶段"
    return None, "未发现足够明确的状态表述，需要人工确认"


def _extract_event_time(subject: str | None, body: str) -> datetime | None:
    haystack = f"{subject or ''}\n{body}"
    for pattern in _DATE_PATTERNS:
        match = pattern.search(haystack)
        if not match:
            continue
        year, month, day, hour, minute = match.groups()
        try:
            return datetime(
                int(year),
                int(month),
                int(day),
                int(hour or 0),
                int(minute or 0),
                tzinfo=UTC,
            )
        except ValueError:
            continue
    return None


def parse_eml(raw: bytes) -> ParsedEmail:
    message = email_message_from_bytes(raw)
    subject = _decode_header(message.get("Subject"))
    sender = _decode_header(message.get("From"))
    received_at = parse_email_date(message)
    body = _clean_text(_body_text(message))
    if not subject and not body:
        raise ValueError("邮件缺少主题和正文")
    status, status_warning = _extract_status(f"{subject or ''}\n{body}")
    company = _company_from_sender(sender) or _extract_company(f"{subject or ''}\n{body}")
    title = _extract_title(subject, body)
    event_time = _extract_event_time(subject, body) or received_at
    warnings: list[str] = []
    if status_warning:
        warnings.append(status_warning)
    if not company:
        warnings.append("未能识别企业，请人工选择申请记录")
    if not title:
        warnings.append("未能识别岗位名称，将根据已有申请匹配")
    if not event_time:
        warnings.append("邮件未提供可解析日期")
    confidence = 0.2
    if status is not None:
        confidence += 0.4
    if company:
        confidence += 0.2
    if title:
        confidence += 0.2
    summary_parts = [part for part in (subject, sender) if part]
    summary = " | ".join(summary_parts)
    if body:
        summary = f"{summary} | {body[:400]}".strip(" |")
    return ParsedEmail(
        subject=subject,
        sender=sender,
        received_at=received_at,
        company=company,
        title=title,
        status=status,
        event_time=event_time,
        confidence=min(confidence, 1.0),
        evidence_summary=summary[:1_000],
        body_excerpt=body[:MAX_BODY_EXCERPT] if body else None,
        warnings=warnings,
    )


def email_message_from_bytes(raw: bytes) -> Message:
    try:
        message = email.message_from_bytes(raw, policy=policy.default)
    except Exception as exc:  # malformed MIME is user-visible, not a 500
        raise ValueError("无法解析 .eml 邮件格式") from exc
    if not any(message.get(header) for header in ("Subject", "From", "Date")):
        raise ValueError("邮件缺少必要头部")
    return message


def parse_email_date(message: Message) -> datetime | None:
    value = message.get("Date")
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(str(value))
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
