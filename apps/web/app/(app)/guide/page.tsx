import Link from "next/link";
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

export const dynamic = "force-dynamic";

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

function Block({ block }: { block: GuideBlock }) {
  switch (block.kind) {
    case "p":
      return (
        <p className="text-sm leading-relaxed text-slate-700">
          <RichText text={block.text} />
        </p>
      );
    case "list":
      return (
        <ul className="space-y-1.5 text-sm leading-relaxed text-slate-700">
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
              <p className="mt-1 text-xs leading-relaxed text-slate-600">{item.body}</p>
              {item.href ? (
                <Link
                  href={item.href}
                  className="mt-2 inline-block text-xs font-medium text-sky-700 hover:underline"
                >
                  去这里 →
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

export default function GuidePage() {
  const sections = GUIDE_SECTIONS;

  return (
    <div className="space-y-8 pb-10">
      <section className="relative overflow-hidden rounded-3xl border border-slate-200 bg-gradient-to-br from-slate-900 via-slate-900 to-sky-950 px-6 py-10 text-white sm:px-10">
        <div className="pointer-events-none absolute -top-24 -right-16 size-64 rounded-full bg-sky-500/25 blur-3xl" />
        <div className="relative">
          <span className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-[11px] font-medium tracking-wide text-sky-100 ring-1 ring-white/15">
            <BookOpen className="size-3.5" aria-hidden />
            使用手册
          </span>
          <h1 className="mt-4 text-2xl font-semibold sm:text-3xl">从注册到拿到面试，每一步怎么做</h1>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-300">
            {sections.length} 个章节，覆盖部署、账号、画像、找岗位、岗位库维护、投递跟进、Agent 与多端访问。
            内容与仓库里的 docs/USER_GUIDE.md 同源，这里更适合在浏览器里边用边看。
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              href="/discover"
              className="inline-flex items-center gap-1.5 rounded-xl bg-white px-4 py-2 text-sm font-medium text-slate-900 hover:bg-slate-100"
            >
              开始找岗位
              <ArrowRight className="size-4" aria-hidden />
            </Link>
            <Link
              href="/"
              className="inline-flex items-center gap-1.5 rounded-xl border border-white/25 px-4 py-2 text-sm font-medium text-white hover:border-white/50"
            >
              回到首页
            </Link>
          </div>
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
        <nav aria-label="目录" className="hidden lg:block">
          <div className="sticky top-24 max-h-[70vh] space-y-1 overflow-y-auto pr-2">
            {sections.map((section) => (
              <div key={section.id}>
                <a
                  href={`#${section.id}`}
                  className="block rounded-lg px-2 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                >
                  {section.title}
                </a>
                {section.subsections?.length ? (
                  <div className="ml-2 border-l border-slate-200 pl-2">
                    {section.subsections.map((sub) => (
                      <a
                        key={sub.id}
                        href={`#${sub.id}`}
                        className="block rounded px-1.5 py-1 text-[11px] text-slate-500 hover:text-slate-800"
                      >
                        {sub.title}
                      </a>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </nav>

        <div className="space-y-6">
          <div className="flex gap-2 overflow-x-auto pb-1 lg:hidden" aria-label="章节快捷跳转">
            {sections.map((section) => (
              <a
                key={section.id}
                href={`#${section.id}`}
                className="shrink-0 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[11px] text-slate-600"
              >
                {section.title}
              </a>
            ))}
          </div>

          {sections.map((section) => (
            <section
              key={section.id}
              id={section.id}
              className="scroll-mt-24 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
            >
              <div className="flex items-start gap-3">
                <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-xl bg-sky-50 text-sky-700 ring-1 ring-sky-100">
                  {ICONS[section.icon]}
                </span>
                <div>
                  <h2 className="text-base font-semibold text-slate-900">{section.title}</h2>
                  <p className="mt-1 text-sm text-slate-500">{section.summary}</p>
                </div>
              </div>

              <div className="mt-4 space-y-3">
                {(section.blocks ?? []).map((block, index) => (
                  <Block key={`${section.id}-${index}`} block={block} />
                ))}
              </div>

              {section.subsections?.length ? (
                <div className="mt-5 space-y-5">
                  {section.subsections.map((sub) => (
                    <div key={sub.id} id={sub.id} className="scroll-mt-24 rounded-xl bg-slate-50/60 p-4">
                      <h3 className="text-sm font-semibold text-slate-800">{sub.title}</h3>
                      <div className="mt-2 space-y-3">
                        {sub.blocks.map((block, index) => (
                          <Block key={`${sub.id}-${index}`} block={block} />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
            </section>
          ))}

          <section className="rounded-2xl border border-slate-800 bg-slate-900 p-6 text-slate-100">
            <h2 className="text-base font-semibold">还有问题？</h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-300">
              手册覆盖不到的细节，可以直接问 Agent —— 它能读你的画像、岗位库与投递记录。
              也可以在 GitHub 提 issue，附上你所在的页面与操作步骤。
            </p>
            <div className="mt-4 flex flex-wrap gap-3">
              <Link
                href="/agent"
                className="inline-flex items-center gap-1.5 rounded-xl bg-white px-4 py-2 text-sm font-medium text-slate-900 hover:bg-slate-100"
              >
                打开 Agent 工作台
                <ArrowRight className="size-4" aria-hidden />
              </Link>
              <Link
                href="/home"
                className="inline-flex items-center gap-1.5 rounded-xl border border-white/25 px-4 py-2 text-sm font-medium text-white hover:border-white/50"
              >
                回到首页
              </Link>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
