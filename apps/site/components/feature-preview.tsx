"use client";
import Image from "next/image";
import { ArrowUpRight, Bot, Briefcase, CalendarDays, FileText, LayoutDashboard, Target } from "lucide-react";
import { useState } from "react";
const VIEWS = [
  { id: "jobs", name: "岗位库", icon: Briefcase, title: "先核验来源，再决定要不要投", body: "组合筛选城市、方向与招聘类型，打开完整 JD 查看职位描述和要求。" },
  { id: "profile", name: "个人画像", icon: FileText, title: "你的经历，由你核对与确认", body: "简历解析只生成草稿，核对技能、教育和项目后再参与匹配。" },
  { id: "matches", name: "可解释匹配", icon: Target, title: "不只看分数，也看依据与资格", body: "技能命中、暂未体现的能力和硬性资格分开呈现，帮助你判断是否适合。" },
  { id: "agent", name: "Agent 助手", icon: Bot, title: "从一个问题，继续追问下一步", body: "查看多轮会话与结构化结果。此图为预置演示对话，未调用模型。" },
  { id: "applications", name: "投递看板", icon: LayoutDashboard, title: "把申请进度留在一条时间线上", body: "申请由本人在官网完成；在工作台记录阶段、证据和下一步安排。" },
  { id: "calendar", name: "面试日程", icon: CalendarDays, title: "明确的预约，才进入日历", body: "区分申请状态与预约时间，集中查看面试、测评和需要跟进的安排。" },
];
export function FeaturePreview() {
  const [selected, setSelected] = useState(VIEWS[0]!);
  const base = process.env.NEXT_PUBLIC_SITE_BASE_PATH ?? "/CareerPilot";
  const image = `${base}/guide/${selected.id}.png`;
  return <div>
    <div aria-label="选择功能截图" className="mb-5 flex flex-wrap gap-2">{VIEWS.map((view) => <button type="button" key={view.id} aria-pressed={view.id === selected.id} onClick={() => setSelected(view)} className={`inline-flex items-center gap-2 rounded-xl border px-3 py-2.5 text-xs font-medium transition-colors sm:px-4 ${selected.id === view.id ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white text-slate-600 hover:border-sky-300 hover:text-sky-700"}`}><view.icon className="size-4" aria-hidden />{view.name}</button>)}</div>
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl shadow-slate-200/40">
      <div className="flex flex-col gap-2 border-b border-slate-100 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6"><div aria-live="polite"><h3 className="font-semibold text-slate-900">{selected.title}</h3><p className="mt-2 max-w-2xl text-xs leading-6 text-slate-500">{selected.body}</p></div><a href={image} target="_blank" rel="noreferrer" className="inline-flex shrink-0 items-center gap-1 text-xs text-sky-700 hover:underline">查看原图 <ArrowUpRight className="size-3" aria-hidden /></a></div>
      <a href={image} target="_blank" rel="noreferrer" aria-label={`查看${selected.name}原图`} className="block bg-slate-100 p-1.5 sm:p-3"><Image src={image} alt={`${selected.name}界面，虚构演示数据`} width={1600} height={1050} unoptimized className="h-auto w-full rounded-lg" /></a>
    </div>
    <p className="mt-4 text-xs leading-6 text-slate-500">所有人物、企业、岗位与预约均为虚构演示数据。这里展示功能截图；完整功能需在自己的部署环境中使用。</p>
  </div>;
}
