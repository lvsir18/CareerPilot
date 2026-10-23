"""Resume upload, parsing, listing and deletion."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.resume import Resume
from app.db.models.user import User
from app.repositories.resumes import ResumeRepository
from app.services.resume_parser import (
    EmptyResumeText,
    ResumeParseError,
    UnsupportedResumeFormat,
    extract_text,
    parse_resume_text,
)
from app.storage import FileStorage, LocalFileStorage

_ALLOWED_EXTENSIONS = {"pdf", "docx"}
_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class ResumeService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        storage: FileStorage | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._repository = ResumeRepository(session)
        self._storage = storage or LocalFileStorage(settings.file_storage_dir)

    @staticmethod
    def _extension(filename: str) -> str:
        if "." not in filename:
            return ""
        return filename.rsplit(".", 1)[-1].lower()

    def upload(self, user: User, *, filename: str, raw: bytes, content_type: str | None) -> Resume:
        extension = self._extension(filename)
        if extension not in _ALLOWED_EXTENSIONS:
            raise AppError(
                code="UNSUPPORTED_RESUME_FORMAT",
                message="仅支持 PDF 或 DOCX 简历",
                status_code=422,
            )
        max_bytes = self._settings.max_resume_mb * 1024 * 1024
        if len(raw) > max_bytes:
            raise AppError(
                code="RESUME_TOO_LARGE",
                message=f"简历文件不能超过 {self._settings.max_resume_mb} MB",
                status_code=413,
            )

        resume_id = uuid4()
        storage_key = f"resumes/{user.id}/{resume_id}.{extension}"
        resolved_content_type = content_type or _CONTENT_TYPES[extension]

        try:
            text = extract_text(raw, filename)
        except UnsupportedResumeFormat as exc:
            raise AppError(
                code="UNSUPPORTED_RESUME_FORMAT", message=str(exc), status_code=422
            ) from exc
        except (EmptyResumeText, ResumeParseError) as exc:
            # Save the file so the user can inspect/delete it, but keep it unparsed.
            self._storage.save(
                storage_key=storage_key, content=raw, content_type=resolved_content_type
            )
            resume = Resume(
                id=resume_id,
                user_id=user.id,
                filename=filename[:255],
                storage_key=storage_key,
                content_type=resolved_content_type,
                size=len(raw),
                text=None,
                parse_status="failed",
                parsed_json={},
                error=str(exc),
                is_primary=self._repository.count(user.id) == 0,
            )
            self._repository.add(resume)
            self._session.commit()
            self._session.refresh(resume)
            return resume

        parsed = parse_resume_text(text)
        self._storage.save(storage_key=storage_key, content=raw, content_type=resolved_content_type)
        resume = Resume(
            id=resume_id,
            user_id=user.id,
            filename=filename[:255],
            storage_key=storage_key,
            content_type=resolved_content_type,
            size=len(raw),
            text=text,
            parse_status="success",
            parsed_json=parsed.as_dict(),
            error=None,
            is_primary=self._repository.count(user.id) == 0,
        )
        self._repository.add(resume)
        self._session.commit()
        self._session.refresh(resume)
        return resume

    def list(self, user: User, *, limit: int) -> list[Resume]:
        return self._repository.list(user.id, limit=limit)

    def get(self, user: User, resume_id: UUID) -> Resume:
        resume = self._repository.get(user.id, resume_id)
        if resume is None:
            raise AppError(code="RESUME_NOT_FOUND", message="简历不存在", status_code=404)
        return resume

    def delete(self, user: User, resume_id: UUID) -> None:
        resume = self.get(user, resume_id)
        self._repository.delete(resume)
        self._session.flush()
        self._storage.delete(resume.storage_key)
        # If the primary was removed, promote the newest remaining resume.
        if resume.is_primary:
            remaining = self._repository.list(user.id, limit=1)
            if remaining:
                remaining[0].is_primary = True
        self._session.commit()

    def set_primary(self, user: User, resume_id: UUID) -> Resume:
        resume = self.get(user, resume_id)
        self._repository.set_primary_false(user.id)
        resume.is_primary = True
        self._session.commit()
        self._session.refresh(resume)
        return resume
