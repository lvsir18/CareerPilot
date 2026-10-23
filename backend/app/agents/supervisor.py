"""Supervisor StateGraph: intent, planning, routing, aggregation and HITL."""

from __future__ import annotations

import json
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from app.agents.runtime import CareerAgentState, RuntimeContext
from app.services.profile_service import ProfileService

_INTENT_SYSTEM = """你是求职任务理解器。解析用户输入为结构化意图，并调用 Intent 工具返回。
- intent 取值：job_search / job_match / progress_query / profile_query / combined / chitchat。
- chitchat 用于打招呼、询问你的能力、闲聊或与求职数据无关的问题；这类输入不需要调用任何求职工具。
- 提取关键词、公司、城市、求职类型、是否排除已申请、TopK。
- required_agents 从 {job_search, job_match, progress, profile} 中按任务需要选择。
- 不要编造约束；信息缺失时使用空列表或默认值。"""

# Deterministic routing fallback: required_agents is derived from intent when
# the model leaves it empty, keeping agent selection explainable.
_REQUIRED_AGENTS: dict[str, list[str]] = {
    "job_search": ["job_search"],
    "job_match": ["profile", "job_match"],
    "progress_query": ["progress"],
    "profile_query": ["profile"],
    "combined": ["job_search", "profile", "job_match", "progress"],
    "chitchat": [],
}


class Intent(BaseModel):
    intent: Literal[
        "job_search",
        "job_match",
        "progress_query",
        "profile_query",
        "combined",
        "chitchat",
    ]
    keywords: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    cities: list[str] = Field(default_factory=list)
    job_types: list[str] = Field(default_factory=list)
    exclude_applied: bool = False
    top_k: int = Field(default=10, ge=1, le=30)
    required_agents: list[str] = Field(default_factory=list)


_AGGREGATE_SYSTEM = """你是求职 Agent 结果汇总器。基于工具返回的结构化结果生成简洁、可验证的回答。
- 只陈述结果中有依据的事实，不编造分数、状态或来源。
- 完整 JD 岗位与只有摘要的 JobLead 要分开展示。
- 若结果不足，明确说明信息不足，不要补齐虚构岗位。
- 用自然中文直接回答用户，不要输出「检索结果汇总」这类标题。
- 不要提及工具名称、查询数量、JSON 字段或内部执行告警。
- 岗位用项目符号列出，每行形如「公司 · 岗位（城市）」；只使用结果中存在的字段。
- 搜索结果带发布时间时按新到旧排列；不确定的信息不要写成确定的。
- 不要自行添加时效或免责声明，系统会在需要时统一追加。
- 检索失败或结果为空时，用一到两句话说明，并给出下一步建议（补充关键词、城市或岗位类型）。"""

# Appended verbatim when the tools report that no new outbound search happened,
# so the freshness caveat never depends on the model following instructions.
_LEAD_NOTICE = "以上线索来自历史检索记录，发布时间与在招状态需核实。"

_CHAT_SYSTEM = """你是 CareerPilot 求职助手。用简洁自然的中文直接回答。
- 你能做：岗位检索、岗位匹配、申请进度查询、候选人画像查询，以及把结果整理成可执行的求职建议。
- 不要编造岗位、分数、申请状态或用户画像中没有的信息。
- 不要提及内部工具、模型或报错细节。"""


def _understand(model: BaseChatModel):
    bound = model.bind_tools([convert_to_openai_tool(Intent)])

    def node(state: CareerAgentState) -> dict[str, Any]:
        last = state["messages"][-1]
        text = last.content if hasattr(last, "content") else str(last)
        message = bound.invoke([SystemMessage(_INTENT_SYSTEM), HumanMessage(content=text)])
        if message.tool_calls:
            intent = Intent.model_validate(message.tool_calls[0]["args"])
        else:
            intent = Intent(intent="job_search")
        # Routing is deterministic: derived from intent, never from free text.
        intent.required_agents = list(_REQUIRED_AGENTS.get(intent.intent, ["job_search"]))
        return {
            "intent": intent.intent,
            "constraints": intent.model_dump(),
            "plan": [
                {"step": i + 1, "agent": name, "status": "pending"}
                for i, name in enumerate(intent.required_agents)
            ],
            "current_step": 0,
        }

    return node


def _execute(ctx: RuntimeContext, agents: dict[str, object]):
    def node(state: CareerAgentState) -> dict[str, Any]:
        constraints = state.get("constraints", {})
        required = constraints.get("required_agents", []) or []

        # Human-in-the-loop: full matching requires a confirmed profile.
        profile_summary: dict[str, Any] | None = None
        if "job_match" in required:
            profile = ProfileService(ctx.session).get(ctx.user)
            if not profile.verified_by_user:
                interrupt(
                    {
                        "action": "confirm_profile",
                        "message": "完整岗位匹配需要已确认画像，请先前往 /profile 确认",
                    }
                )
            profile_summary = {
                "skills": profile.skills,
                "education": [
                    {
                        "school": e.school,
                        "degree": e.degree,
                        "major": e.major,
                        "graduation_year": e.graduation_year,
                    }
                    for e in profile.education
                ],
                "preferences": profile.preferences.model_dump(),
                "version": profile.version,
                "confirmed": True,
            }

        agent_results: dict[str, Any] = dict(state.get("agent_results", {}) or {})
        tool_results: list[dict[str, Any]] = list(state.get("tool_results", []) or [])
        for name in required:
            agent = agents.get(name)
            if agent is None:
                continue
            emit = getattr(ctx, "on_event", None)
            if emit:
                emit("agent.started", {"agent": name})
            payload: dict[str, Any] = {"constraints": constraints}
            if name == "job_match" and profile_summary:
                payload["profile"] = profile_summary
            task_text = json.dumps(payload, ensure_ascii=False)
            result = agent.invoke({"messages": [HumanMessage(content=task_text)]})
            messages = result.get("messages", [])
            answer = messages[-1].content if messages else ""
            agent_results[name] = answer
            if emit:
                emit("agent.completed", {"agent": name})
            for message in messages:
                if not isinstance(message, ToolMessage):
                    continue
                payload: Any = message.content
                # Tool content may arrive as content blocks, not a raw string.
                if isinstance(payload, list):
                    payload = "".join(
                        str(part.get("text") or "") if isinstance(part, dict) else str(part)
                        for part in payload
                    )
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except (TypeError, ValueError):
                        continue
                if isinstance(payload, dict):
                    tool_results.append({"agent": name, "tool": message.name, "data": payload})

        return {
            "agent_results": agent_results,
            "tool_results": tool_results,
            "status": "completed",
        }

    return node


def _chat(model: BaseChatModel):
    def node(state: CareerAgentState) -> dict[str, Any]:
        last = state["messages"][-1]
        text = last.content if hasattr(last, "content") else str(last)
        reply = model.invoke([SystemMessage(_CHAT_SYSTEM), HumanMessage(content=str(text))])
        return {
            "final_answer": reply.content if hasattr(reply, "content") else str(reply),
            "status": "completed",
        }

    return node


def _lead_notice_needed(state: CareerAgentState) -> bool:
    for entry in state.get("tool_results", []) or []:
        data = entry.get("data") if isinstance(entry, dict) else None
        if isinstance(data, dict) and data.get("leads_notice"):
            return True
    return False


def _aggregate(model: BaseChatModel):
    def node(state: CareerAgentState) -> dict[str, Any]:
        results = state.get("agent_results", {}) or {}
        final = model.invoke(
            [
                SystemMessage(_AGGREGATE_SYSTEM),
                HumanMessage(content=json.dumps(results, ensure_ascii=False)),
            ]
        )
        answer = final.content if hasattr(final, "content") else str(final)
        if isinstance(answer, str) and _lead_notice_needed(state) and _LEAD_NOTICE not in answer:
            answer = f"{answer.rstrip()}\n\n{_LEAD_NOTICE}"
        return {"final_answer": answer, "status": "completed"}

    return node


def build_supervisor(ctx: RuntimeContext, model: BaseChatModel, agents: dict[str, object]):
    graph = StateGraph(CareerAgentState)
    graph.add_node("understand", _understand(model))
    graph.add_node("chat", _chat(model))
    graph.add_node("execute", _execute(ctx, agents))
    graph.add_node("aggregate", _aggregate(model))
    graph.add_edge(START, "understand")
    graph.add_conditional_edges(
        "understand",
        lambda state: "chat" if state.get("intent") == "chitchat" else "execute",
        {"chat": "chat", "execute": "execute"},
    )
    graph.add_edge("chat", END)
    graph.add_edge("execute", "aggregate")
    graph.add_edge("aggregate", END)
    return graph
