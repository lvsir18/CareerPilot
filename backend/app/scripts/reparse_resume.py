"""Re-parse already-uploaded resumes after a parser change.

There is no HTTP endpoint for re-parsing, so this one-off script re-reads the
stored file, refreshes ``resumes.parsed_json`` and (unless told otherwise)
re-applies the result to the owner's profile snapshot. The profile stays
``verified_by_user = false``, so the user still has to review and confirm it.

``./backend`` is bind-mounted into the containers, so no image rebuild needed:

    docker compose exec api python -m app.scripts.reparse_resume --last
    docker compose exec api python -m app.scripts.reparse_resume --resume-id <uuid>
    docker compose exec api python -m app.scripts.reparse_resume --email you@example.com --all
    docker compose exec api python -m app.scripts.reparse_resume --last --dry-run

Without arguments the newest resume is re-parsed.
"""

from __future__ import annotations

import argparse
import json
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models.resume import Resume
from app.db.models.user import User
from app.db.session import session_scope
from app.services.profile_service import ProfileService
from app.services.resume_parser import (
    EmptyResumeText,
    ResumeParseError,
    UnsupportedResumeFormat,
    extract_text,
    parse_resume_text,
)
from app.storage import LocalFileStorage


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.scripts.reparse_resume",
        description="重新解析已上传的简历并刷新画像快照",
    )
    parser.add_argument("--resume-id", help="只处理指定的简历 ID")
    parser.add_argument("--email", help="只处理该用户的简历")
    parser.add_argument(
        "--all",
        action="store_true",
        help="处理全部匹配的简历（默认只处理最新一份）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印重解析结果，不写数据库")
    parser.add_argument(
        "--skip-profile",
        action="store_true",
        help="只更新 parsed_json，不刷新画像（不会覆盖用户已编辑的画像）",
    )
    return parser


def _select_resumes(
    session: Session,
    *,
    resume_id: UUID | None,
    email: str | None,
    all_resumes: bool,
) -> list[Resume]:
    query = select(Resume).order_by(Resume.created_at.desc())
    if resume_id is not None:
        query = query.where(Resume.id == resume_id)
    if email is not None:
        user_id = session.scalar(
            select(User.id).where(func.lower(User.email) == email.strip().lower())
        )
        if user_id is None:
            raise SystemExit(f"未找到邮箱为 {email} 的用户")
        query = query.where(Resume.user_id == user_id)
    if not all_resumes and resume_id is None:
        query = query.limit(1)
    return list(session.scalars(query))


def _reparse_one(
    session: Session,
    storage: LocalFileStorage,
    resume: Resume,
    *,
    dry_run: bool,
    refresh_profile: bool,
) -> dict[str, Any]:
    before = (resume.parsed_json or {}).get("education") or []
    summary: dict[str, Any] = {
        "resume_id": str(resume.id),
        "filename": resume.filename,
        "previous_status": resume.parse_status,
    }

    try:
        content = storage.read(resume.storage_key)
    except FileNotFoundError:
        summary["status"] = "missing_file"
        summary["storage_key"] = resume.storage_key
        return summary

    try:
        text = extract_text(content, resume.filename)
        parsed = parse_resume_text(text)
    except (EmptyResumeText, ResumeParseError, UnsupportedResumeFormat) as exc:
        summary["status"] = "failed"
        summary["error"] = str(exc)
        if not dry_run:
            resume.parse_status = "failed"
            resume.error = str(exc)
        return summary

    payload = parsed.as_dict()
    summary["status"] = "success"
    summary["education_before"] = before
    summary["education_after"] = payload["education"]
    summary["education_changed"] = before != payload["education"]

    if dry_run:
        return summary

    resume.text = text
    resume.parsed_json = payload
    resume.parse_status = "success"
    resume.error = None
    session.flush()

    if refresh_profile:
        user = session.get(User, resume.user_id)
        if user is None:  # pragma: no cover - FK keeps this impossible
            summary["profile"] = "user_missing"
        else:
            profile = ProfileService(session).apply_resume(user, resume)
            summary["profile"] = {
                "education_count": len(profile.education),
                "verified_by_user": False,
            }
    return summary


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)

    resume_id: UUID | None = None
    if args.resume_id:
        try:
            resume_id = UUID(args.resume_id)
        except ValueError:
            raise SystemExit(f"--resume-id 不是合法的 UUID：{args.resume_id}") from None

    settings = get_settings()
    storage = LocalFileStorage(settings.file_storage_dir)

    with session_scope() as session:
        resumes = _select_resumes(
            session,
            resume_id=resume_id,
            email=args.email,
            all_resumes=args.all,
        )
        if not resumes:
            raise SystemExit("没有匹配的简历记录")
        results = [
            _reparse_one(
                session,
                storage,
                resume,
                dry_run=args.dry_run,
                refresh_profile=not args.skip_profile,
            )
            for resume in resumes
        ]

    print(json.dumps({"dry_run": args.dry_run, "resumes": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
