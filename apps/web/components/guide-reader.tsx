import Link from "next/link";
import Image from "next/image";
import { GuideNavigation } from "@/components/guide-navigation";
import {
  ArrowRight,
  BookOpen,
  Bot,
  Briefcase,
  CalendarDays,
  CheckCircle2,
  Compass,
  FileText,
  HelpCircle,
  Info,
  KeyRound,
  Link2,
  Map,
  Rocket,
  Settings,
  Shield,
  Smartphone,
  Sparkles,
  Target,
  UserRound,
} from "lucide-react";
import type { ReactNode } from "react";

import { GUIDE_SECTIONS, type GuideBlock, type GuideIcon } from "@/lib/guide-content";

const ICONS: Record<GuideIcon, ReactNode> = {
  sparkles: <Sparkles className="size-4" aria-hidden />,
  rocket: <Rocket className="size-4" aria-hidden />,
  map: <Map className="size-4" aria-hidden />,
  user: <UserRound className="size-4" aria-hidden />,
  file: <FileText className="size-4" aria-hidden />,
  compass: <Compass className="size-4" aria-hidden />,
  link: <Link2 className="size-4" aria-hidden />,
  briefcase: <Briefcase className="size-4" aria-hidden />,
  target: <Target className="size-4" aria-hidden />,
  calendar: <CalendarDays className="size-4" aria-hidden />,
  bot: <Bot className="size-4" aria-hidden />,
  key: <KeyRound className="size-4" aria-hidden />,
  smartphone: <Smartphone className="size-4" aria-hidden />,
  settings: <Settings className="size-4" aria-hidden />,
  help: <HelpCircle className="size-4" aria-hidden />,
  shield: <Shield className="size-4" aria-hidden />,
};

/** Minimal inline markdown: **bold** and `code`. */
function RichText({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return (
    <>
      {parts.map((part, index) => {
        if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
          return (
            <strong key={index} className="font-medium text-slate-900">
              {part.slice(2, -2)}
            </strong>
          );
        }
        if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
          return (
            <code
              key={index}
              className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[12px] text-slate-800"
            >
              {part.slice(1, -1)}
            </code>
          );
        }
        return <span key={index}>{part}</span>;
      })}
    </>
  );
}

type GuideMode = { publicSite?: boolean; assetPrefix?: string };

function operationHref(href: string, publicSite: boolean): string {
  if (!publicSite || href.startsWith("#")) return href;
  const targets: Record<string, string> = {
    "/jobs": "jobs", "/profile": "profile", "/matches": "matches",
    "/discover": "discover", "/agent": "agent", "/applications": "applications",
  };
  return `#${targets[href] ?? "pages"}`;
}

function Block({ block, publicSite = false, assetPrefix = "" }: { block: GuideBlock } & GuideMode) {
  switch (block.kind) {
    case "image":
      return (
        <figure className="my-6 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <a href={`${assetPrefix}${block.src}`} target="_blank" rel="noreferrer" aria-label={`查看大图：${block.alt}`} className="group block bg-slate-100 p-1 sm:p-2">
            <Image src={`${assetPrefix}${block.src}`} alt={block.alt} width={block.width} height={block.height} unoptimized
              className="h-auto w-full rounded-lg transition-opacity group-hover:opacity-90" />
          </a>
          <figcaption className="border-t border-slate-100 px-4 py-3 text-xs leading-6 text-slate-500">
            <span className="mr-2 inline-flex rounded bg-slate-100 px-1.5 text-[10px] font-medium text-slate-600">演示截图</span>
            {block.caption} <a href={`${assetPrefix}${block.src}`} target="_blank" rel="noreferrer" className="whitespace-nowrap text-sky-700 hover:underline">查看大图 ↗</a>
          </figcaption>
        </figure>
      );
    case "p":
      return (
        <p className="text-sm leading-7 text-slate-700">
          <RichText text={block.text} />
        </p>
      );
    case "list":
      return (
        <ul className="space-y-1.5 text-sm leading-7 text-slate-700">
          {block.items.map((item) => (
            <li key={item} className="flex gap-2">
              <span className="mt-2 size-1.5 shrink-0 rounded-full bg-slate-300" aria-hidden />
              <span>
                <RichText text={item} />
              </span>
            </li>
          ))}
        </ul>
      );
    case "steps":
      return (
        <ol className="grid gap-3 sm:grid-cols-2">
          {block.items.map((item, index) => (
            <li key={item.title} className="rounded-xl bg-slate-50 p-4">
              <span className="inline-flex size-7 items-center justify-center rounded-lg bg-white text-xs font-semibold text-slate-700 ring-1 ring-slate-200">
                {index + 1}
              </span>
              <p className="mt-3 text-sm font-medium text-slate-900">{item.title}</p>
              <p className="mt-1 text-xs leading-6 text-slate-600">{item.body}</p>
              {item.href ? (
                <Link
                  href={operationHref(item.href, publicSite)}
                  className="mt-2 inline-block text-xs font-medium text-sky-700 hover:underline"
                >
                  {publicSite ? "查看操作说明 →" : "去这里 →"}
                </Link>
              ) : null}
            </li>
          ))}
        </ol>
      );
    case "table":
      return (
        <div className="-mx-1 overflow-x-auto">
          <table className="w-full min-w-[420px] border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500">
                {block.head.map((cell) => (
                  <th key={cell} className="px-2 py-2 font-medium">
                    {cell}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row) => (
                <tr key={row.join("|")} className="border-b border-slate-100 last:border-0">
                  {row.map((cell, index) => (
                    <td
                      key={`${row[0]}-${index}`}
                      className={index === 0 ? "px-2 py-2 font-medium text-slate-800" : "px-2 py-2 text-slate-600"}
                    >
                      <RichText text={cell} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    case "tip": {
      const warn = block.tone === "warn";
      return (
        <div
          className={`flex gap-2 rounded-xl border p-3 text-xs leading-relaxed ${
            warn ? "border-amber-200 bg-amber-50 text-amber-900" : "border-sky-200 bg-sky-50 text-sky-900"
          }`}
        >
          {warn ? (
            <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
          ) : (
            <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden />
          )}
          <div>
            <RichText text={block.text} />
          </div>
        </div>
      );
    }
    case "code":
      return (
        <figure className="overflow-hidden rounded-xl border border-slate-200 bg-slate-900">
          {block.caption ? (
            <figcaption className="border-b border-slate-700/60 px-3 py-2 text-[11px] text-slate-400">
              {block.caption}
            </figcaption>
          ) : null}
          <pre className="overflow-x-auto px-3 py-3 text-[12px] leading-relaxed text-slate-100">
            <code>{block.text}</code>
          </pre>
        </figure>
      );
    default:
      return null;
  }
}

export function GuideReader({ publicSite = false, assetPrefix = "" }: GuideMode) {
  const sections = GUIDE_SECTIONS;
  return (
    <div id="guide-top" className="space-y-8 pb-10">
      <section className="relative overflow-hidden rounded-3xl border border-sky-100 bg-gradient-to-br from-white via-sky-50/70 to-indigo-50 px-5 py-8 sm:px-9 sm:py-10">
        <div className="pointer-events-none absolute -right-12 -top-16 size-64 rounded-full bg-sky-200/30 blur-3xl" />
        <div className="relative">
          <span className="inline-flex items-center gap-2 text-[11px] font-semibold tracking-widest text-sky-700"><BookOpen className="size-4" aria-hidden /> CAREERPILOT / 使用手册</span>
          <h1 className="mt-4 max-w-2xl text-2xl font-semibold leading-snug tracking-tight text-slate-950 sm:text-3xl">从注册到拿到面试，<br className="hidden sm:block" />每一步怎么做</h1>
          <p className="mt-4 max-w-xl text-sm leading-7 text-slate-600">先完成画像，再找到可信岗位，最后把投递与面试安排好。用这份手册，随时找到当前这一步的操作方法。</p>
          <div className="mt-5 flex flex-wrap items-center gap-3 text-xs text-slate-500"><span>{sections.length} 个章节</span><span aria-hidden>·</span><span>桌面与手机适用</span><span aria-hidden>·</span><a href="https://github.com/lvsir18/CareerPilot/blob/main/docs/USER_GUIDE.md" className="text-sky-700 hover:underline">Markdown 版 ↗</a></div>
        </div>
      </section>

      <div className="grid gap-3 sm:grid-cols-3" aria-label="按任务开始">
        {[
          { href: "#start", label: "第一次部署", desc: "检查环境 → 启动 → 注册", icon: <Rocket className="size-5" aria-hidden /> },
          { href: "#profile", label: "开始求职", desc: "确认画像 → 找岗位 → 跟进", icon: <Compass className="size-5" aria-hidden /> },
          { href: "#faq", label: "遇到问题", desc: "按现象排查与恢复操作", icon: <HelpCircle className="size-5" aria-hidden /> },
        ].map((item) => <a key={item.href} href={operationHref(item.href, publicSite)} className="group flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4 transition-colors hover:border-sky-300 hover:bg-sky-50/50">
          <span className="rounded-xl bg-slate-50 p-2.5 text-sky-700">{item.icon}</span>
          <span className="min-w-0 flex-1"><span className="block text-sm font-semibold text-slate-800">{item.label}</span><span className="mt-1 block text-[11px] leading-5 text-slate-500">{item.desc}</span></span>
          <ArrowRight className="size-4 shrink-0 text-slate-300 group-hover:text-sky-600" aria-hidden />
        </a>)}
      </div>

      <div className="grid items-start gap-7 lg:grid-cols-[210px_minmax(0,1fr)]">
        <GuideNavigation />
        <div className="min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white">
          <div className="border-b border-slate-100 bg-slate-50/70 px-5 py-4 text-xs leading-6 text-slate-500 sm:px-8">
            <span className="font-medium text-slate-700">阅读提示</span> · 按左侧目录跳转，或搜索具体操作。图中人物、岗位、预约均为虚构演示数据；Agent 图为预置对话，未调用模型。
          </div>
          {sections.map((section, sectionIndex) => (
            <section key={section.id} id={section.id} className="scroll-mt-36 border-b border-slate-100 px-5 py-8 last:border-0 lg:scroll-mt-24 sm:px-8 sm:py-10">
              <div className="mb-5 flex items-start gap-3">
                <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-xl bg-sky-50 text-sky-700">{ICONS[section.icon]}</span>
                <div className="min-w-0"><p className="mb-1 text-[10px] font-medium tracking-widest text-slate-400">CHAPTER {String(sectionIndex + 1).padStart(2, "0")}</p>
                  <h2 className="text-xl font-semibold tracking-tight text-slate-900"><a href={`#${section.id}`} className="hover:text-sky-700">{section.title}</a></h2>
                  <p className="mt-2 text-sm leading-6 text-slate-500">{section.summary}</p>
                </div>
              </div>
              <div className="space-y-4">{(section.blocks ?? []).map((block, index) => <Block key={`${section.id}-${index}`} block={block} publicSite={publicSite} assetPrefix={assetPrefix} />)}</div>
              {section.subsections?.length ? <div className="mt-6 space-y-8">{section.subsections.map((sub) => (
                <div key={sub.id} id={sub.id} className="scroll-mt-36 lg:scroll-mt-24">
                  <h3 className="mb-3 border-l-2 border-sky-300 pl-3 text-base font-semibold text-slate-800">{sub.title}</h3>
                  <div className="space-y-4">{sub.blocks.map((block, index) => <Block key={`${sub.id}-${index}`} block={block} publicSite={publicSite} assetPrefix={assetPrefix} />)}</div>
                </div>
              ))}</div> : null}
              <div className="mt-7 flex justify-end"><a href={sectionIndex + 1 < sections.length ? `#${sections[sectionIndex + 1]?.id}` : "#guide-top"} className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-sky-700">{sectionIndex + 1 < sections.length ? `下一章：${sections[sectionIndex + 1]?.title}` : "回到顶部"}<ArrowRight className="size-3" aria-hidden /></a></div>
            </section>
          ))}
          <section className="bg-slate-50 px-5 py-8 sm:px-8">
            <h2 className="text-lg font-semibold text-slate-900">没有找到答案？</h2>
            <p className="mt-2 text-sm leading-7 text-slate-600">反馈时请附上页面、复现步骤、预期结果与版本号。截图前遮住邮箱、简历正文与密钥。</p>
            <div className="mt-4 flex flex-wrap gap-3"><a href="https://github.com/lvsir18/CareerPilot/issues/new/choose" target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-xs font-medium text-white hover:bg-slate-700">反馈问题 <ArrowRight className="size-3" aria-hidden /></a><Link href={publicSite ? "/" : "/home"} className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs text-slate-600 hover:border-slate-300">回到首页</Link></div>
          </section>
        </div>
      </div>
    </div>
  );
}
