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


def _tool_key(item: dict[str, Any]) -> tuple[str, str]:
    """Identity of a tool result, used to de-duplicate the two collection paths."""
    return (
        str(item.get("tool")),
        json.dumps(item.get("data"), ensure_ascii=False, sort_keys=True, default=str),
    )


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


_AGGREGATE_SYSTEM = """你是求职 Agent 结果汇总器。第一原则：回答用户提出的问题（question）。
不要套用岗位列表模板。
- 先判断 intent：profile_query 只回答画像；progress_query 只回答申请进度；
  job_search / job_match 才列岗位；combined 按问题顺序分点回答。
- 只陈述结果中有依据的事实，不编造分数、状态或来源。
- 完整 JD 岗位与只有摘要的 JobLead 要分开展示。
- 若结果不足，说明缺少什么，不要补齐虚构岗位。
- 用户没有要求岗位时，不要写「没有拿到可展示的岗位结果」，也不要建议补关键词或城市。
- 有 facts 时以 facts 为准；agent_results 的措辞与 facts 冲突时忽略 agent_results。
- 面试/笔试时间直接照抄 facts 里的「YYYY-MM-DD HH:MM（北京时间）」，不要自行换算时区。
- 区分预约时间（starts_at_label）与记录时间（recorded_at）：预约在将来时，确认动作发生在过去。
- facts 里存在已排期的面试/笔试时，不能回答「还没有具体时间」；要给出公司、岗位与时间。
- 时间线中 appointment=false 或 appointment_state=inactive 的事件只作历史，
  不得列为有效预约；superseded_at 非空表示已被改期或取消，不要要求用户重新判断其是否有效。
- 用自然中文直接回答用户，不要输出「检索结果汇总」这类标题。
- 不要提及工具名称、查询数量、JSON 字段或内部执行告警。
- 岗位用项目符号列出，每行形如「公司 · 岗位（城市）」；只使用结果中存在的字段。
- 搜索结果带发布时间时按新到旧排列；不确定的信息不要写成确定的。
- 不要自行添加时效或免责声明，系统会在需要时统一追加。
- 只有确实执行了检索且结果为空时，才用一到两句话说明，并给出下一步建议。
- 只能推荐 payload.matches 里的岗位，不得列出其中的职位以外的岗位。
- matches 为空时明确说明「没有符合条件的岗位」，不要改写成「最接近的岗位」并逐条推荐；
  可用一句话说明 excluded_count 个候选因企业/城市/方向不符被排除，并提示可以放宽条件。
- agent_results 里可能出现不在 matches 中的岗位描述，一律忽略，不要当作推荐。"""

# Appended verbatim when the tools report that no new outbound search happened,
# so the freshness caveat never depends on the model following instructions.
_LEAD_NOTICE = "以上线索来自历史检索记录，发布时间与在招状态需核实。"

# Tools whose output is a factual answer on its own (no interpretation needed).
_ANSWER_FACT_TOOLS = frozenset(
    {"list_applications", "get_application_timeline", "check_job_application_status"}
)

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
            # Per-turn isolation. The checkpoint keeps conversation history in
            # ``messages``; structured results belong to the turn that produced
            # them, otherwise a skills question renders last turn's job cards.
            "tool_results": [],
            "agent_results": {},
            "errors": [],
            "final_answer": None,
        }

    return node


def _execute(ctx: RuntimeContext, agents: dict[str, object]):
    def node(state: CareerAgentState) -> dict[str, Any]:
        # Node boundary is the natural cancellation point for a multi-agent run.
        ctx.ensure_active()
        constraints = state.get("constraints", {})
        required = constraints.get("required_agents", []) or []

        agent_results: dict[str, Any] = dict(state.get("agent_results", {}) or {})

        # Human-in-the-loop: full matching requires a confirmed profile.
        profile_summary: dict[str, Any] | None = None
        if "job_match" in required:
            profile = ProfileService(ctx.session).get(ctx.user)
            approved = ctx.resume_approval
            while not profile.verified_by_user and approved is not False:
                approved = interrupt(
                    {
                        "action": "confirm_profile",
                        "message": "完整岗位匹配需要已确认画像，请先前往 /profile 确认",
                    }
                )
                # The node re-runs from the top on resume, so the snapshot above
                # may predate the confirmation. Re-read it instead of trusting
                # the client's "已确认，继续" button.
                ctx.session.expire_all()
                profile = ProfileService(ctx.session).get(ctx.user)
            if approved is False:
                required = [name for name in required if name != "job_match"]
                agent_results["job_match"] = {
                    "status": "declined",
                    "message": "用户已拒绝本次岗位匹配，已跳过岗位匹配",
                }
            if "job_match" in required:
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

        tool_results: list[dict[str, Any]] = list(state.get("tool_results", []) or [])
        recorded = {_tool_key(item) for item in tool_results}
        for name in required:
            agent = agents.get(name)
            if agent is None:
                continue
            emit = getattr(ctx, "on_event", None)
            if emit:
                emit("agent.started", {"agent": name})
            # The sub-agent must see what the user asked, otherwise it answers a
            # generic "list everything" and the summarizer has to guess intent.
            payload: dict[str, Any] = {
                "question": _original_question(state),
                "constraints": constraints,
            }
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
                    item = {"agent": name, "tool": message.name, "data": payload}
                    key = _tool_key(item)
                    if key not in recorded:
                        recorded.add(key)
                        tool_results.append(item)

        # The runtime context saw every tool call directly, so it can fill the
        # gaps whenever a ToolMessage could not be parsed (that is what made the
        # structured cards come back empty while the text answer was fine).
        for item in ctx.tool_results:
            key = _tool_key(item)
            if key not in recorded:
                recorded.add(key)
                tool_results.append(item)

        # A tool error means the business task did not actually succeed: report
        # the run as partial so "completed" never masks a failed lookup.
        errors = list(state.get("errors", []) or [])
        for item in tool_results:
            data = item.get("data")
            if isinstance(data, dict) and data.get("error"):
                message = f"{item.get('tool')}: {data['error']}"
                if message not in errors:
                    errors.append(message)

        return {
            "agent_results": agent_results,
            "tool_results": tool_results,
            "errors": errors,
            "status": "partial" if errors else "completed",
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


def _original_question(state: CareerAgentState) -> str:
    # Checkpointed messages accumulate across turns. The summarizer must answer
    # the current user turn, even when tool/AI messages follow it.
    for message in reversed(state.get("messages", []) or []):
        if getattr(message, "type", "") == "human":
            content = getattr(message, "content", "")
            return content if isinstance(content, str) else str(content)
    return ""


def _answer_facts(tool_results: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Deterministic progress facts handed to the summarizer verbatim.

    The assistant once denied an appointment that the tool had returned with a
    concrete time, so the summarizer receives the raw facts (already localised
    by the tool) instead of relying on an agent's prose.
    """
    facts: list[dict[str, Any]] = []
    for item in tool_results or []:
        if not isinstance(item, dict):
            continue
        if item.get("tool") not in _ANSWER_FACT_TOOLS:
            continue
        facts.append({"tool": item.get("tool"), "data": item.get("data")})
    return facts


def _match_mismatch(
    entry: dict[str, Any],
    companies: list[str],
    cities: list[str],
    keywords: list[str],
) -> str | None:
    """Why a match does not belong to the current ask (None means it does).

    Eligibility answers "can I apply"; this answers "did the user ask for this
    direction". A 运营 job can be perfectly eligible and still be out of scope
    when the user asked for 后端/测试开发 only.
    """
    job = entry.get("job") or {}
    company = str(job.get("company") or "")
    city = str(job.get("city") or "")
    haystack = " ".join(
        str(part or "")
        for part in (
            job.get("title"),
            job.get("summary"),
            " ".join(job.get("tags") or []),
        )
    )

    if companies and not any(name and name in company for name in companies):
        return "不在本轮限定的企业范围"
    if cities and not any(name and name in city for name in cities):
        return "不在本轮限定的城市范围"
    if keywords and not any(word and word in haystack for word in keywords):
        return "不在本轮限定的岗位方向"
    return None


def _match_summary(
    tool_results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Flatten the filtered results into what the summarizer may recommend."""
    included: list[dict[str, Any]] = []
    excluded = 0
    for item in tool_results:
        data = item.get("data")
        if not isinstance(data, dict):
            continue
        # The card builder accepts both contracts; the answer must do so too.
        if item.get("tool") == "match_job":
            entries = [data] if isinstance(data.get("job"), dict) else []
        elif item.get("tool") == "recommend_jobs":
            entries = data.get("items") or []
        else:
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            job = entry.get("job") or {}
            match = entry.get("match") or {}
            included.append(
                {
                    "company": job.get("company"),
                    "title": job.get("title"),
                    "city": job.get("city"),
                    "match_score": match.get("match_score"),
                    "eligibility_status": match.get("eligibility_status"),
                }
            )
        excluded += len(data.get("extra_items") or [])
    return included, excluded


def _split_matches(
    tool_results: list[dict[str, Any]], constraints: dict[str, Any]
) -> list[dict[str, Any]]:
    """Keep only the matches the user actually asked for; park the rest.

    Cards used to contradict the answer text: the model excluded 运营/数据仓库
    while the result list still showed them as recommendations.
    """
    companies = [str(item) for item in constraints.get("companies") or [] if item]
    cities = [str(item) for item in constraints.get("cities") or [] if item]
    keywords = [str(item) for item in constraints.get("keywords") or [] if item]
    if not (companies or cities or keywords):
        return tool_results

    output: list[dict[str, Any]] = []
    parked: list[Any] = []
    for item in tool_results:
        tool = item.get("tool")
        data = item.get("data")
        if not isinstance(data, dict):
            output.append(item)
            continue
        if tool == "match_job":
            # A single-job match the model ran on its own must obey the same
            # scope; otherwise it reappears as a recommended card.
            if not isinstance(data.get("job"), dict):
                output.append(item)
                continue
            reason = _match_mismatch(data, companies, cities, keywords)
            if reason:
                parked.append({**data, "selection_reason": reason})
            else:
                output.append(item)
            continue
        if tool != "recommend_jobs":
            output.append(item)
            continue
        keep: list[Any] = []
        extra: list[Any] = []
        for entry in data.get("items") or []:
            if not isinstance(entry, dict):
                keep.append(entry)
                continue
            reason = _match_mismatch(entry, companies, cities, keywords)
            if reason:
                extra.append({**entry, "selection_reason": reason})
            else:
                keep.append(entry)
        parked.extend(extra)
        output.append({"tool": "recommend_jobs", "data": {**data, "items": keep}})

    if parked:
        output.append({"tool": "recommend_jobs", "data": {"items": [], "extra_items": parked}})
    return output


def _aggregate(model: BaseChatModel):
    def node(state: CareerAgentState) -> dict[str, Any]:
        results = state.get("agent_results", {}) or {}
        # Cards must match the answer: filter the result list by the constraints
        # the user actually stated, keeping the remainder for an explicit
        # "other candidates" section instead of presenting them as picks.
        tool_results = _split_matches(
            list(state.get("tool_results") or []), state.get("constraints") or {}
        )
        # The summarizer used to receive only tool results, so a profile question
        # was answered as an empty job search. Pass the question and intent along.
        included, excluded = _match_summary(tool_results)
        payload = {
            "question": _original_question(state),
            "intent": state.get("intent", ""),
            "agent_results": results,
            "facts": _answer_facts(tool_results),
            # The answer may only list these; everything else was filtered out by
            # the user's own company/city/direction constraints.
            "matches": included,
            "excluded_count": excluded,
        }
        final = model.invoke(
            [
                SystemMessage(_AGGREGATE_SYSTEM),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
            ]
        )
        answer = final.content if hasattr(final, "content") else str(final)
        if isinstance(answer, str) and _lead_notice_needed(state) and _LEAD_NOTICE not in answer:
            answer = f"{answer.rstrip()}\n\n{_LEAD_NOTICE}"
        return {
            "final_answer": answer,
            "tool_results": tool_results,
            "status": "partial" if state.get("errors") else "completed",
        }

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
