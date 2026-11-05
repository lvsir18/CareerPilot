"""Supervisor StateGraph: intent, planning, routing, aggregation and HITL."""

from __future__ import annotations

import json
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, RemoveMessage, SystemMessage, ToolMessage
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
- 不要编造约束；信息缺失时使用空列表或默认值。
- 输入是多轮对话：question 可能省略上文条件（「那杭州呢」「第一个岗位」「刚才那几个」）。
  先读 previous.question / previous.answer / previous.constraints 再补全：
  用户只换了城市就只改 cities，keywords、job_types（例如「实习」）、companies 保持不变；
  用户说「第一个岗位」「那个 JD」时，沿用上一轮的公司与方向，不要切换城市或岗位类型。
- 纯回指且不需要新的数据检索（「刚才你找到几个」「上一轮说了什么」）时，用 chitchat。
- user_preferences 是该用户已确认画像里的长期偏好
  （cities / job_types / keywords / excluded_keywords）。
  本轮和上一轮都没有指定这个维度时，采用偏好；用户本轮明确给了别的值或说「不限」时以用户为准。"""

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
- 用户限定了求职类型（如「实习」）时，不得把校招/社招岗位列入推荐列表；
  确有重叠可在末尾用一句话说明「另有 N 个校招岗位未列入」。
- matches 里 source=official 或 verification_status=verified 的岗位代表已读到官方 JD，可直接推荐；
  verification_status=search_snippet_only 的只能作为「仅摘要线索」列出，并提示需到官网核实。
- matches 为空时明确说明「没有符合条件的岗位」，不要改写成「最接近的岗位」并逐条推荐；
  可用一句话说明 excluded_count 个候选因企业/城市/方向不符被排除，并提示可以放宽条件。
- matches 里的岗位没有 match_score 时，不要因此说「匹配结果为空」或「没找到」，
  按检索结果正常列出即可；不得引入 matches 之外的新岗位。
- agent_results 可以补充岗位门槛、方向分布等细节，但其中的岗位必须已在 matches 中。"""

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
- 不要提及内部工具、模型或报错细节。
- 输入可能是 {"question": ..., "previous_results": {...}}。
  previous_results 是上一轮检索的真实统计：jobs 岗位数、verified_jobs 已核验数、
  leads 仅摘要数、cities、keywords、job_types、answer。
  用户问「刚才找到几个」「上一轮是哪个城市」时直接引用这些数字与字段，不要回答「没有保留记录」。
  只有 previous_results 为空时，才说明上一轮没有检索结果。"""


_CARRY_OVER_INTENTS = frozenset({"job_search", "job_match", "combined"})
_CARRY_OVER_FIELDS = ("cities", "keywords", "companies", "job_types", "exclude_applied")

# Long conversations keep appending to ``messages`` forever (DeepSeek Harness
# solves the same problem with automatic compaction). Only the tail matters for
# follow-ups, and ``last_scope`` already carries the durable search context, so
# older turns can be dropped instead of growing the checkpoint without bound.
_KEEP_RECENT_MESSAGES = 10
_TRIM_THRESHOLD = 12


def _trim_messages(messages: list[Any]) -> list[Any]:
    """Drop the oldest turns once a conversation gets long.

    ``last_scope`` keeps the search context across the cut, and follow-ups only
    look at the last two messages, so this loses history without losing scope.
    """
    if len(messages) <= _TRIM_THRESHOLD:
        return []
    removed = messages[:-_KEEP_RECENT_MESSAGES]
    return [RemoveMessage(id=message.id) for message in removed if getattr(message, "id", None)]


def _previous_question(messages: list[Any]) -> str:
    """The question before the current one, used to resolve follow-ups."""
    humans = [message for message in messages if getattr(message, "type", None) == "human"]
    if len(humans) < 2:
        return ""
    content = humans[-2].content
    return content if isinstance(content, str) else str(content)


def _carry_over(intent: Intent, previous: dict[str, Any], previous_intent: str | None) -> None:
    """Follow-ups restate one dimension; the rest of the scope is kept.

    "那杭州呢" only mentions the city, so without this the search silently drops
    "实习" and "大模型" and starts returning 校招 postings. "把第一个岗位的 JD
    发我" mentions nothing at all, so it needs the previous city too. The model
    wins whenever it does provide a value; this is only a fill-in.
    """
    if not previous:
        return
    if intent.intent not in _CARRY_OVER_INTENTS or previous_intent not in _CARRY_OVER_INTENTS:
        return
    for field in _CARRY_OVER_FIELDS:
        if getattr(intent, field):
            continue
        value = previous.get(field)
        if value:
            setattr(intent, field, value)


def _preferences(ctx: RuntimeContext | None) -> dict[str, Any]:
    """Confirmed profile preferences act as long-term memory for this user.

    LangGraph's short-term memory (checkpointer) only survives inside one
    thread; a preference like "只要实习 / 优先成都" has to come from the durable
    profile, otherwise every new conversation starts from zero.
    """
    if ctx is None:
        return {}
    try:
        profile = ProfileService(ctx.session).get(ctx.user)
    except Exception:  # pragma: no cover - a broken profile must not block intent
        return {}
    if not profile.verified_by_user:
        return {}
    prefs = profile.preferences
    return {
        "cities": list(prefs.cities),
        "job_types": list(prefs.job_types),
        "keywords": list(prefs.keywords),
        "excluded_keywords": list(prefs.excluded_keywords),
        "target_companies": list(prefs.target_companies),
    }


def _understand(model: BaseChatModel, ctx: RuntimeContext | None = None):
    bound = model.bind_tools([convert_to_openai_tool(Intent)])

    def node(state: CareerAgentState) -> dict[str, Any]:
        messages = state.get("messages") or []
        last = messages[-1]
        text = last.content if hasattr(last, "content") else str(last)
        previous_constraints = dict(state.get("constraints") or {})
        previous_intent = state.get("intent")
        previous_answer = state.get("final_answer") or ""
        previous_question = _previous_question(messages)
        last_scope = dict(state.get("last_scope") or {})
        # A chit-chat or progress turn carries no search scope, so a follow-up
        # like "把第一个岗位的 JD 发我" must fall back to the last turn that
        # actually searched instead of losing the city entirely.
        if previous_intent in _CARRY_OVER_INTENTS:
            scope, scope_intent = previous_constraints, previous_intent
        else:
            scope, scope_intent = last_scope, last_scope.get("intent")

        preferences = _preferences(ctx)

        # The intent model used to see only the new sentence, so "那杭州呢" lost
        # the job type/keywords and "第一个岗位" lost the city entirely.
        context = {
            "question": text,
            "user_preferences": preferences,
            "previous": {
                "question": previous_question,
                "answer": previous_answer[:600],
                "constraints": {
                    key: previous_constraints.get(key)
                    for key in (
                        "intent",
                        "keywords",
                        "companies",
                        "cities",
                        "job_types",
                        "exclude_applied",
                    )
                },
                "last_search_scope": last_scope,
            },
        }
        message = bound.invoke(
            [
                SystemMessage(_INTENT_SYSTEM),
                HumanMessage(content=json.dumps(context, ensure_ascii=False)),
            ]
        )
        if message.tool_calls:
            intent = Intent.model_validate(message.tool_calls[0]["args"])
        else:
            intent = Intent(intent="job_search")
        _carry_over(intent, scope, scope_intent)
        # Routing is deterministic: derived from intent, never from free text.
        intent.required_agents = list(_REQUIRED_AGENTS.get(intent.intent, ["job_search"]))
        next_scope = last_scope
        if intent.intent in _CARRY_OVER_INTENTS:
            next_scope = {
                "intent": intent.intent,
                "keywords": intent.keywords,
                "companies": intent.companies,
                "cities": intent.cities,
                "job_types": intent.job_types,
                "exclude_applied": intent.exclude_applied,
            }
        return {
            "previous_intent": previous_intent or "",
            "previous_question": previous_question,
            "previous_answer": previous_answer,
            "previous_constraints": previous_constraints,
            "last_scope": next_scope,
            "messages": _trim_messages(messages),
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
                # Keep the readable reason next to the code: a bare "TOOL_FAILED"
                # tells neither the user nor the next debugging session anything.
                detail = data.get("message")
                if isinstance(detail, str):
                    detail = detail.strip()
                    if detail and detail != data["error"]:
                        message = f"{message}（{detail[:120]}）"
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
        previous = (state.get("last_scope") or {}).get("result_summary")
        if previous:
            # "刚才你找到几个" must be answered from the last search summary:
            # tool_results are cleared every turn, so the chat model otherwise
            # honestly (and uselessly) says it keeps no records.
            content = json.dumps(
                {"question": str(text), "previous_results": previous},
                ensure_ascii=False,
            )
        else:
            content = str(text)
        reply = model.invoke([SystemMessage(_CHAT_SYSTEM), HumanMessage(content=content)])
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


_JOB_TYPE_ALIASES = {
    "实习": "internship",
    "校招": "campus",
    "秋招": "campus",
    "春招": "campus",
    "社招": "experienced",
    "全职": "experienced",
}


def _wanted_job_types(constraints: dict[str, Any]) -> set[str]:
    """Normalise the user's 求职类型 ("实习") into the stored enum."""
    wanted: set[str] = set()
    for value in constraints.get("job_types") or []:
        text = str(value).strip().lower()
        if not text:
            continue
        wanted.add(_JOB_TYPE_ALIASES.get(text, text))
    return wanted


def _match_mismatch(
    entry: dict[str, Any],
    companies: list[str],
    cities: list[str],
    keywords: list[str],
    wanted_types: set[str] | None = None,
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
    job_type = str(job.get("job_type") or "").strip().lower()
    if wanted_types and job_type and job_type not in wanted_types:
        return "不在本轮限定的求职类型"
    return None


def _search_entry(
    job: dict[str, Any],
    *,
    company: str | None = None,
    default_status: str | None = None,
    source: str,
) -> dict[str, Any]:
    """Normalise a search/official-import posting for the summarizer.

    URLs are left out on purpose: the answer's links come from ``agent_results``,
    and carrying them here only inflates the summarizer prompt (which then hit
    the 30s model timeout once the search results were actually included).
    """
    return {
        "company": job.get("company") or company,
        "title": job.get("title"),
        "city": job.get("city"),
        "job_type": job.get("job_type"),
        "verification_status": job.get("verification_status") or default_status,
        "match_score": None,
        "eligibility_status": None,
        "source": source,
    }


def _search_scope_mismatch(
    entry: dict[str, Any],
    companies: list[str],
    cities: list[str],
    wanted_types: set[str] | None = None,
) -> str | None:
    """Search hits are already keyword-filtered upstream; only scope is checked.

    A missing city/company is kept on purpose: dropping it would hide a real
    posting just because the source omitted the field.
    """
    company = str(entry.get("company") or "")
    city = str(entry.get("city") or "")
    if companies and company and not any(name and name in company for name in companies):
        return "不在本轮限定的企业范围"
    if cities and city and not any(name and name in city for name in cities):
        return "不在本轮限定的城市范围"
    job_type = str(entry.get("job_type") or "").strip().lower()
    if wanted_types and job_type and job_type not in wanted_types:
        # "实习" asks must not surface 校招 postings, which is what made a
        # 杭州实习 answer list 校招正式岗.
        return "不在本轮限定的求职类型"
    return None


def _match_summary(
    tool_results: list[dict[str, Any]],
    constraints: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Flatten the filtered results into what the summarizer may recommend.

    Search/import tools must be included: a pure ``job_search`` intent never
    calls the matching tools, so an empty ``matches`` made the answer claim
    "no jobs found" while 31 verified postings sat in the result cards.
    """
    companies = [str(item) for item in (constraints or {}).get("companies") or [] if item]
    cities = [str(item) for item in (constraints or {}).get("cities") or [] if item]
    wanted_types = _wanted_job_types(constraints or {})
    included: list[dict[str, Any]] = []
    excluded = 0
    for item in tool_results:
        data = item.get("data")
        if not isinstance(data, dict):
            continue
        tool = item.get("tool")
        # The card builder accepts both contracts; the answer must do so too.
        if tool == "match_job":
            entries = [data] if isinstance(data.get("job"), dict) else []
        elif tool == "recommend_jobs":
            entries = data.get("items") or []
        else:
            if tool == "search_jobs":
                postings = [
                    _search_entry(job, source="search") for job in data.get("jobs") or []
                ] + [
                    _search_entry(lead, default_status="search_snippet_only", source="search")
                    for lead in data.get("leads") or []
                ]
            elif tool == "import_official_jobs":
                postings = [
                    _search_entry(
                        job,
                        company=data.get("company"),
                        default_status="verified",
                        source="official",
                    )
                    for job in data.get("jobs") or []
                ]
            else:
                continue
            included.extend(
                entry
                for entry in postings
                if not _search_scope_mismatch(entry, companies, cities, wanted_types)
            )
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
    # The same posting often arrives from several tools (search hit + official
    # import). De-duplicate and bound the list: an unbounded match list made the
    # summarizer prompt slow enough to time out.
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for entry in included:
        key = (str(entry.get("company") or ""), str(entry.get("title") or ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(entry)
    return unique[:40], excluded


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
    wanted_types = _wanted_job_types(constraints)
    if not (companies or cities or keywords or wanted_types):
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
            reason = _match_mismatch(data, companies, cities, keywords, wanted_types)
            if reason:
                parked.append({**data, "selection_reason": reason})
            else:
                output.append(item)
            continue
        if tool in {"search_jobs", "import_official_jobs"}:
            # Scope filtering must reach the cards too: a 杭州 search used to
            # render 75 cards (every city) next to an answer listing only杭州.
            company = data.get("company")
            if tool == "search_jobs":
                kept = {
                    "jobs": [
                        job
                        for job in data.get("jobs") or []
                        if not _search_scope_mismatch(
                            _search_entry(job, source="search"),
                            companies,
                            cities,
                            wanted_types,
                        )
                    ],
                    "leads": [
                        lead
                        for lead in data.get("leads") or []
                        if not _search_scope_mismatch(
                            _search_entry(
                                lead, default_status="search_snippet_only", source="search"
                            ),
                            companies,
                            cities,
                            wanted_types,
                        )
                    ],
                }
            else:
                kept = {
                    "jobs": [
                        job
                        for job in data.get("jobs") or []
                        if not _search_scope_mismatch(
                            _search_entry(
                                job,
                                company=company,
                                default_status="verified",
                                source="official",
                            ),
                            companies,
                            cities,
                            wanted_types,
                        )
                    ]
                }
            output.append({"tool": tool, "data": {**data, **kept}})
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
            reason = _match_mismatch(entry, companies, cities, keywords, wanted_types)
            if reason:
                extra.append({**entry, "selection_reason": reason})
            else:
                keep.append(entry)
        parked.extend(extra)
        output.append({"tool": "recommend_jobs", "data": {**data, "items": keep}})

    if parked:
        output.append({"tool": "recommend_jobs", "data": {"items": [], "extra_items": parked}})
    return output


def _search_summary(
    state: CareerAgentState, tool_results: list[dict[str, Any]], answer: str
) -> dict[str, Any] | None:
    """What this turn actually found, so a later turn can refer back to it."""
    if state.get("intent") not in _CARRY_OVER_INTENTS:
        return None
    jobs: list[dict[str, Any]] = []
    leads: list[dict[str, Any]] = []
    for item in tool_results:
        tool = item.get("tool")
        data = item.get("data")
        if not isinstance(data, dict):
            continue
        if tool == "search_jobs":
            jobs.extend(data.get("jobs") or [])
            leads.extend(data.get("leads") or [])
        elif tool == "import_official_jobs":
            # Official imports always carry a full JD and have no status field.
            jobs.extend(data.get("jobs") or [])
    constraints = state.get("constraints") or {}
    return {
        "intent": state.get("intent"),
        "cities": constraints.get("cities") or [],
        "keywords": constraints.get("keywords") or [],
        "job_types": constraints.get("job_types") or [],
        "jobs": len(jobs),
        "verified_jobs": sum(
            1 for job in jobs if str(job.get("verification_status") or "verified") == "verified"
        ),
        "leads": len(leads),
        "answer": (answer or "")[:240],
    }


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
        included, excluded = _match_summary(tool_results, state.get("constraints") or {})
        # Sub-agent prose can run to several KB each; the summarizer only needs
        # enough to describe the门槛, so truncation keeps the prompt fast.
        agent_results = {
            key: (value[:4000] if isinstance(value, str) else value)
            for key, value in results.items()
        }
        payload = {
            "question": _original_question(state),
            "intent": state.get("intent", ""),
            "agent_results": agent_results,
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
        scope = dict(state.get("last_scope") or {})
        summary = _search_summary(state, tool_results, answer)
        if summary:
            scope["result_summary"] = summary
        return {
            "final_answer": answer,
            "tool_results": tool_results,
            "status": "partial" if state.get("errors") else "completed",
            "last_scope": scope,
        }

    return node


def build_supervisor(ctx: RuntimeContext, model: BaseChatModel, agents: dict[str, object]):
    graph = StateGraph(CareerAgentState)
    graph.add_node("understand", _understand(model, ctx))
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
