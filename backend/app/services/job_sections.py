"""Split an intact rendered JD into editable fields without inventing content."""

from __future__ import annotations

import re
from dataclasses import dataclass

_DESCRIPTION_HEADINGS = {
    "职位描述",
    "岗位描述",
    "岗位职责",
    "工作职责",
    "工作内容",
    "jobdescription",
    "responsibilities",
    "你将会负责",
}
_REQUIREMENT_HEADINGS = {
    "职位要求",
    "岗位要求",
    "任职要求",
    "任职资格",
    "工作要求",
    "任职条件",
    "requirements",
    "qualifications",
    "我们期望你",
}
_ADDITIONAL_HEADINGS = {
    "在招业务",
    "福利待遇",
    "加入我们的理由",
    "工作地点",
    "工作城市",
    "面试城市",
    "部门意向",
}


@dataclass
class JobSections:
    description: str
    requirements: list[str]
    additional_info: str


def _heading(line: str) -> str:
    return re.sub(r"[\s：:【】\[\]]", "", line).lower()


def split_job_sections(text: str | None) -> JobSections:
    """Only standalone labels split fields; ordinary sentences stay untouched.

    Each multi-direction requirement keeps its original direction label so
    reordering editable fields cannot associate it with another direction.
    """
    buckets: dict[str, list[str]] = {"description": [], "requirements": [], "additional_info": []}
    category = "description"
    context: str | None = None
    last_context: dict[str, str | None] = dict.fromkeys(buckets)
    for line in (text or "").splitlines():
        label = _heading(line)
        if re.fullmatch(r"【岗位方向：.+】", line.strip()) or (
            len(line.strip()) < 40
            and line.strip().endswith("方向")
            and re.fullmatch(r"[\w /+\-]+方向", line.strip())
        ):
            context = line.strip()
            category = "description"
            continue
        if label in _DESCRIPTION_HEADINGS:
            category = "description"
        elif label in _REQUIREMENT_HEADINGS:
            category = "requirements"
            continue
        elif label == "加分项":
            category = "requirements"
        elif label in _ADDITIONAL_HEADINGS:
            category = "additional_info"
        if context and last_context[category] != context:
            buckets[category].append(context)
            last_context[category] = context
        buckets[category].append(line)
    return JobSections(
        description="\n".join(buckets["description"]).strip(),
        requirements=[line.strip() for line in buckets["requirements"] if line.strip()],
        additional_info="\n".join(buckets["additional_info"]).strip(),
    )
