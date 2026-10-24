"""Specialized agent construction on top of LangGraph prebuilt react agents."""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage

from app.agents.runtime import RuntimeContext
from app.agents.tools import (
    build_job_tools,
    build_match_tools,
    build_profile_tools,
    build_progress_tools,
)

JOB_SEARCH_PROMPT = """你是招聘岗位搜索助手。职责：
- 调用 search_jobs / get_job_detail / get_job_leads 获取真实岗位。
- 只有摘要的 JobLead 不能当作完整 JD。
- 无官方发布日期时标记"未知"，"最近发现"不等于"最近发布"。
- 搜索不到不代表企业没有招聘；不伪造职位数量或开放状态。
- 返回岗位时附带来源链接、来源类型和核验状态。"""

JOB_MATCH_PROMPT = """你是岗位匹配助手。职责：
- 只调用 recommend_jobs / match_job 获取匹配结果。
- 匹配分数必须来自系统 MatchingService，禁止自行编造 85%、93% 等分数。
- 只有摘要的 JobLead 只能做基础匹配，不能给完整技能评分。
- 若输入中已提供画像数据（profile），直接基于它调用 recommend_jobs；不要编造用户履历。
- 工具返回 PROFILE_NOT_CONFIRMED 时，请用户先去 /profile 确认画像，
  不要给出任何分数或「大致匹配」。"""

PROFILE_PROMPT = """你是个人画像助手（只读）。职责：
- 调用 get_profile_summary 读取已确认画像。
- 不修改画像，不编造技能/经历。
- 若画像未确认（confirmed=false），明确提示用户前往 /profile 确认。"""

PROGRESS_PROMPT = """你是招聘进度助手（只读）。职责：
- 调用 list_applications / get_application_timeline / check_job_application_status。
- 不要把 planned 解释为已申请，不要把 unknown 解释为拒绝。
- 区分邮件确认和用户手动记录；不声称平台自动同步成功。
- 不修改申请状态。
- 时间字段已由工具换算成「北京时间」并带标签，照抄即可，不要自行加减时区。
- next_appointment 有值即代表已有明确预约：不要说「还没有具体时间」，
  要给出公司、岗位与 starts_at_label。
- 区分预约时间（starts_at_label）与记录时间（recorded_at）。
- 查询岗位状态只用 list_applications 返回的 application_id / job_id / job_no；
  查不到就说明编号无法识别，不要说成「未申请」。"""


def build_specialized_agents(
    ctx: RuntimeContext,
    model: BaseChatModel,
) -> dict[str, object]:
    return {
        "job_search": create_agent(
            model,
            build_job_tools(ctx),
            system_prompt=SystemMessage(JOB_SEARCH_PROMPT),
            name="job_search",
        ),
        "job_match": create_agent(
            model,
            build_match_tools(ctx),
            system_prompt=SystemMessage(JOB_MATCH_PROMPT),
            name="job_match",
        ),
        "profile": create_agent(
            model,
            build_profile_tools(ctx),
            system_prompt=SystemMessage(PROFILE_PROMPT),
            name="profile",
        ),
        "progress": create_agent(
            model,
            build_progress_tools(ctx),
            system_prompt=SystemMessage(PROGRESS_PROMPT),
            name="progress",
        ),
    }
