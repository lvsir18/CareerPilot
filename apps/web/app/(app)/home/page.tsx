import Link from "next/link";
import {
  ArrowRight,
  Bot,
  CalendarCheck,
  FileSearch,
  ShieldCheck,
  Sparkles,
  Upload,
  UserRound,
} from "lucide-react";

export const dynamic = "force-dynamic";

const CAPABILITIES = [
  {
    icon: FileSearch,
    title: "官方核验的岗位库",
    body: "只收录读到官方详情页的岗位；「搜索命中」与「已核验 JD」分开标注，来源链接可回溯。",
    href: "/jobs",
    action: "浏览岗位库",
  },
  {
    icon: Sparkles,
    title: "可解释的画像匹配",
    body: "用已确认的画像做技能、方向与经历比对，给出分数、命中技能与缺口，资格判断单独输出。",
    href: "/matches",
    action: "查看推荐",
  },
  {
    icon: Bot,
    title: "能追问的求职 Agent",
    body: "多个子 Agent 协作完成检索、匹配、进度查询；支持多轮追问、后台执行与断线恢复。",
    href: "/agent",
    action: "打开工作台",
  },
  {
    icon: CalendarCheck,
    title: "投递与面试时间线",
    body: "记录状态流转与笔试面试预约，明确区分「预约时间」与「记录时间」，日历只显示确定日程。",
    href: "/applications",
    action: "进入看板",
  },
];

const STEPS = [
  {
    icon: Upload,
    title: "上传简历",
    body: "PDF / DOCX 解析成结构化信息，扫描版也能手动补全。",
  },
  {
    icon: UserRound,
    title: "确认画像",
    body: "核对教育、项目与偏好后点确认；未确认的画像不参与任何打分。",
  },
  {
    icon: FileSearch,
    title: "找岗位并跟进",
    body: "直连官网检索、收藏或登记投递，面试安排自动进入日历。",
  },
];

export default function HomePage() {
  return (
    <div className="space-y-10 pb-4">
      <section className="relative overflow-hidden rounded-3xl border border-slate-200 bg-gradient-to-br from-slate-900 via-slate-900 to-sky-950 px-6 py-10 text-white shadow-xl shadow-slate-900/10 sm:px-10 sm:py-14">
        <div className="pointer-events-none absolute -top-28 -right-20 size-72 rounded-full bg-sky-500/25 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-32 -left-16 size-72 rounded-full bg-indigo-500/20 blur-3xl" />

        <div className="relative max-w-3xl">
          <div className="flex items-center gap-3">
            {/* eslint-disable-next-line @next/next/no-img-element -- local SVG logo */}
            <img
              src="/careerpilot-avatar.svg"
              alt="CareerPilot"
              width={44}
              height={44}
              className="size-11 rounded-xl shadow-lg shadow-sky-500/30"
            />
            <div>
              <p className="text-sm font-semibold tracking-wide text-white">CareerPilot</p>
              <p className="text-[11px] tracking-[0.18em] text-sky-300/80 uppercase">
                Job search workbench
              </p>
            </div>
          </div>

          <h1 className="mt-6 text-2xl leading-tight font-semibold sm:text-4xl">
            把求职从「海投」变成
            <br className="hidden sm:block" />
            一条可核验的流程
          </h1>
          <p className="mt-4 max-w-2xl text-sm leading-relaxed text-slate-300 sm:text-base">
            官方招聘站直连检索、可解释的画像匹配、能追问的求职 Agent，以及从投递到面试的完整时间线 ——
            全部跑在你自己的机器上。
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              href="/jobs"
              className="inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-medium text-slate-900 transition hover:bg-slate-100"
            >
              进入岗位库
              <ArrowRight className="size-4" aria-hidden />
            </Link>
            <Link
              href="/agent"
              className="inline-flex items-center gap-2 rounded-xl border border-white/25 px-4 py-2.5 text-sm font-medium text-white transition hover:border-white/50 hover:bg-white/10"
            >
              打开 Agent 工作台
            </Link>
          </div>

          <div className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-xs text-slate-400">
            <span className="inline-flex items-center gap-1.5">
              <ShieldCheck className="size-3.5 text-sky-400" aria-hidden />
              来源可核验
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Sparkles className="size-3.5 text-sky-400" aria-hidden />
              分数可解释
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Bot className="size-3.5 text-sky-400" aria-hidden />
              任务可恢复
            </span>
          </div>
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex items-end justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">四块核心能力</h2>
            <p className="mt-1 text-sm text-slate-500">各自独立，也可以由 Agent 串起来一次完成。</p>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          {CAPABILITIES.map((item) => (
            <Link
              key={item.title}
              href={item.href}
              className="group flex flex-col justify-between rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-sky-300 hover:shadow-md"
            >
              <div>
                <span className="inline-flex size-10 items-center justify-center rounded-xl bg-sky-50 text-sky-700 ring-1 ring-sky-100">
                  <item.icon className="size-5" aria-hidden />
                </span>
                <h3 className="mt-4 text-base font-semibold text-slate-900">{item.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-600">{item.body}</p>
              </div>
              <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-sky-700">
                {item.action}
                <ArrowRight className="size-3.5 transition group-hover:translate-x-0.5" aria-hidden />
              </span>
            </Link>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">三步开始</h2>
            <p className="mt-1 text-sm text-slate-500">第一次使用大约 5 分钟。</p>
          </div>
          <Link
            href="/resumes"
            className="text-sm font-medium text-sky-700 hover:underline"
          >
            从上传简历开始 →
          </Link>
        </div>

        <ol className="mt-6 grid gap-4 sm:grid-cols-3">
          {STEPS.map((step, index) => (
            <li key={step.title} className="relative rounded-xl bg-slate-50 p-4">
              <div className="flex items-center gap-2">
                <span className="inline-flex size-7 items-center justify-center rounded-lg bg-white text-xs font-semibold text-slate-700 ring-1 ring-slate-200">
                  {index + 1}
                </span>
                <step.icon className="size-4 text-slate-500" aria-hidden />
              </div>
              <p className="mt-3 text-sm font-medium text-slate-900">{step.title}</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">{step.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="grid gap-4 rounded-2xl border border-slate-200 bg-slate-900 p-6 text-slate-300 sm:grid-cols-[1.2fr_1fr]">
        <div>
          <h2 className="text-base font-semibold text-white">边界写在这里，而不是藏在设置里</h2>
          <ul className="mt-3 space-y-2 text-sm leading-relaxed">
            <li>不自动投递、不自动填表，也不代你登录招聘平台。</li>
            <li>不保存招聘平台密码；邮箱凭据只存加密后的密文。</li>
            <li>搜索摘要不等于完整 JD，只有读到官方详情页才会进入岗位库。</li>
          </ul>
        </div>
        <div className="flex items-end justify-start sm:justify-end">
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 rounded-xl border border-white/20 px-4 py-2.5 text-sm text-white transition hover:bg-white/10"
          >
            查看我的概览
            <ArrowRight className="size-4" aria-hidden />
          </Link>
        </div>
      </section>
    </div>
  );
}
