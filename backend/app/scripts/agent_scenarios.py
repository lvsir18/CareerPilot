"""Agent 场景回归探针：意图路由、多轮上下文、多 agent 协作、HITL、取消。

这不是单元测试，而是打真实服务（API + worker + LLM）的端到端脚本，用来回答
"agent 到底能不能处理好这些场景"。默认以只读方式借用指定账号：新建一条临时会话
（不改密码），跑完可选择保留会话，方便在 Web 上回看。

用法（容器内执行）::

    # 只跑某一组
    docker compose exec -T api python -m app.scripts.agent_scenarios --group routing

    # 指定账号，并保留会话便于回看
    docker compose exec -T api python -m app.scripts.agent_scenarios \\
        --email you@example.com --group context --keep

可用分组：``routing`` ``context`` ``multitask`` ``hitl`` ``cancel`` ``all``。
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import select

from app.auth.session import generate_session_token, hash_session_token
from app.core.config import Settings, get_settings
from app.db.models.user import User, UserSession
from app.db.session import session_scope

TERMINAL = {"completed", "partial", "failed", "cancelled", "timed_out", "waiting_for_user"}


# --------------------------------------------------------------------------- api


class Probe:
    """Thin HTTP client around the running API, authenticated as one user."""

    def __init__(self, settings: Settings, email: str) -> None:
        self.settings = settings
        self.base = "http://127.0.0.1:8000/api/v1"
        self.origin = "http://localhost:3000"
        self.email = email
        self.user_id = self._borrow_session()
        self.client = httpx.Client(
            base_url=self.base, cookies={"careerpilot_session": self.token}, timeout=60
        )
        self.csrf = self.client.get("/auth/csrf").json()["data"]["csrf_token"]
        self.headers = {"X-CSRF-Token": self.csrf, "Origin": self.origin}

    def _borrow_session(self) -> str:
        self.token = generate_session_token()
        with session_scope() as session:
            user = session.scalar(select(User).where(User.email == self.email))
            if user is None:
                raise SystemExit(f"账号不存在：{self.email}")
            session.add(
                UserSession(
                    user_id=user.id,
                    token_hash=hash_session_token(self.token),
                    # Short-lived: this session exists only for the probe run.
                    expires_at=datetime.now(UTC) + timedelta(hours=2),
                )
            )
            return str(user.id)

    def new_thread(self) -> str:
        thread = self.client.post("/agent/threads", headers=self.headers).json()["data"]
        return thread["id"]

    def ask(
        self, thread_id: str, message: str, *, timeout: int = 240, cancel_after: float | None = None
    ) -> dict[str, Any]:
        started = time.time()
        created = self.client.post(
            "/agent/runs",
            json={"thread_id": thread_id, "request_id": str(uuid4()), "message": message},
            headers=self.headers,
        )
        if created.status_code != 202:
            return {"message": message, "status": "http_error", "detail": created.text[:200]}
        run_id = created.json()["data"]["id"]
        if cancel_after is not None:
            deadline = started + cancel_after
            while time.time() < deadline:
                time.sleep(1)
            self.client.post(f"/agent/runs/{run_id}/cancel", headers=self.headers)
        data: dict[str, Any] = {}
        while time.time() - started < timeout:
            data = self.client.get(f"/agent/runs/{run_id}", headers=self.headers).json()["data"]
            if data["status"] in TERMINAL:
                break
            time.sleep(2)
        result = data.get("result") or {}
        events = self.client.get(f"/agent/runs/{run_id}/events", headers=self.headers).json()[
            "data"
        ]
        return {
            "message": message,
            "run_id": run_id,
            "status": data.get("status"),
            "intent": result.get("intent"),
            "plan": result.get("plan") or [],
            "agents": sorted((result.get("agent_results") or {}).keys()),
            "errors": result.get("errors") or [],
            "answer": (result.get("final_answer") or "").strip(),
            "cards": len((result.get("structured") or {}).get("jobs") or []),
            "events": [event["event_type"] for event in events],
            "seconds": round(time.time() - started, 1),
        }


# ----------------------------------------------------------------------- scenarios


@dataclass
class Case:
    key: str
    group: str
    message: str
    check: Callable[[dict[str, Any]], str | None]
    multi_turn: bool = False
    cancel_after: float | None = None
    timeout: int = 240


@dataclass
class Outcome:
    case: Case
    results: list[dict[str, Any]] = field(default_factory=list)
    failure: str | None = None


def _intent(expected: str) -> Callable[[dict[str, Any]], str | None]:
    def check(run: dict[str, Any]) -> str | None:
        if run["intent"] != expected:
            return f"intent={run['intent']} 期望 {expected}"
        return None

    return check


def _agents_at_least(*names: str) -> Callable[[dict[str, Any]], str | None]:
    def check(run: dict[str, Any]) -> str | None:
        missing = [name for name in names if name not in run["agents"]]
        return f"缺少子 agent：{missing}（实际 {run['agents']}）" if missing else None

    return check


def _no_agents(run: dict[str, Any]) -> str | None:
    return f"chitchat 不应启动子 agent，实际 {run['agents']}" if run["agents"] else None


def _has_answer(run: dict[str, Any]) -> str | None:
    return "没有产出回答" if not run["answer"] else None


ROUTING = [
    Case("chitchat", "routing", "你好，你能帮我做什么？", _no_agents),
    Case("profile_query", "routing", "我的画像里都有哪些内容？", _intent("profile_query")),
    Case(
        "progress_query",
        "routing",
        "帮我看看我最近的申请进度",
        _intent("progress_query"),
    ),
    Case("job_search", "routing", "帮我找北京的大模型实习", _intent("job_search")),
    Case(
        "job_match",
        "routing",
        "哪些岗位更适合我的简历？",
        _intent("job_match"),
    ),
    Case(
        "empty_result",
        "routing",
        "帮我找火星基地的量子岗位",
        # 没结果必须给出解释，而不是崩溃或空回答。
        _has_answer,
    ),
]

CONTEXT = [
    Case(
        "turn1_beijing",
        "context",
        "帮我找北京的大模型实习",
        _intent("job_search"),
        multi_turn=True,
    ),
    Case(
        "turn2_hangzhou_followup",
        "context",
        "那杭州呢",
        _intent("job_search"),
        multi_turn=True,
    ),
    Case(
        "turn3_recall",
        "context",
        "刚才杭州那边你找到几个岗位？",
        _has_answer,
        multi_turn=True,
    ),
    Case(
        "turn4_refer",
        "context",
        "把第一个岗位的完整 JD 发给我",
        _has_answer,
        multi_turn=True,
    ),
    Case(
        "fresh_thread_no_context",
        "context",
        "那杭州呢",
        # 新会话里 "那" 没有指代对象，不能凭空继承上一个会话的城市。
        _has_answer,
    ),
]

MULTITASK = [
    Case(
        "combined",
        "multitask",
        "帮我找杭州的大模型实习，并看看我最近的申请进度",
        _agents_at_least("job_search", "progress"),
    ),
]

HITL = [
    Case(
        "hitl_confirm",
        "hitl",
        "帮我匹配一下最适合我的岗位",
        _has_answer,
    ),
]


def _cancelled(run: dict[str, Any]) -> str | None:
    if run["status"] == "cancelled":
        return None
    return f"status={run['status']} 期望 cancelled"


CANCEL = [
    Case(
        "cancel_midway",
        "cancel",
        "帮我找成都的大模型实习",
        _cancelled,
        cancel_after=4.0,
    ),
]

GROUPS = {
    "routing": ROUTING,
    "context": CONTEXT,
    "multitask": MULTITASK,
    "hitl": HITL,
    "cancel": CANCEL,
}


def run_cases(probe: Probe, cases: list[Case], keep: bool) -> list[Outcome]:
    outcomes: list[Outcome] = []
    thread_for_multiturn: str | None = None
    for case in cases:
        if case.multi_turn:
            if thread_for_multiturn is None:
                thread_for_multiturn = probe.new_thread()
            thread_id = thread_for_multiturn
        else:
            thread_id = probe.new_thread()
        result = probe.ask(
            thread_id, case.message, timeout=case.timeout, cancel_after=case.cancel_after
        )
        outcome = Outcome(case=case, results=[result])
        outcome.failure = case.check(result)
        outcomes.append(outcome)
        mark = "PASS" if outcome.failure is None else "FAIL"
        print(
            f"[{mark}] {case.key}: {result['status']} · intent={result['intent']} "
            f"· agents={result['agents']} · {result['seconds']}s"
        )
        if outcome.failure:
            print(f"        {outcome.failure}")
        print(f"        answer: {result['answer'][:120]!r}")
        if keep and not case.multi_turn:
            print(f"        thread: {thread_id}")
    if keep and thread_for_multiturn:
        print(f"        多轮会话 thread: {thread_for_multiturn}")
    return outcomes


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent 场景回归探针")
    parser.add_argument("--email", default="demo@example.com")
    parser.add_argument("--group", default="routing", choices=[*GROUPS, "all"])
    parser.add_argument("--keep", action="store_true", help="保留会话，便于在 Web 回看")
    args = parser.parse_args()

    settings = get_settings()
    probe = Probe(settings, args.email)
    groups = list(GROUPS) if args.group == "all" else [args.group]

    outcomes: list[Outcome] = []
    for name in groups:
        print(f"\n=== {name} ===")
        outcomes.extend(run_cases(probe, GROUPS[name], args.keep))

    failures = [item for item in outcomes if item.failure]
    print("\n=== 汇总 ===")
    passed = len(outcomes) - len(failures)
    print(f"用例 {len(outcomes)} 个，通过 {passed} 个，失败 {len(failures)} 个")
    if failures:
        for item in failures:
            print(f"  失败 {item.case.key}: {item.failure}")
        print("\n失败明细：")
        detail = json.dumps([item.results[0] for item in failures], ensure_ascii=False, indent=2)
        print(detail[:2000])


if __name__ == "__main__":
    main()
