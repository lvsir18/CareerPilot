"use client";

import { ChevronDown, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { GUIDE_SECTIONS, type GuideBlock } from "@/lib/guide-content";

function blockText(block: GuideBlock): string {
  switch (block.kind) {
    case "p": case "tip": case "code": return block.text;
    case "list": return block.items.join(" ");
    case "steps": return block.items.map((item) => `${item.title} ${item.body}`).join(" ");
    case "table": return [...block.head, ...block.rows.flat()].join(" ");
    case "image": return `${block.alt} ${block.caption}`;
  }
}

const ENTRIES = GUIDE_SECTIONS.flatMap((section) => [
  { id: section.id, parent: section.id, title: section.title, text: `${section.summary} ${(section.blocks ?? []).map(blockText).join(" ")}` },
  ...(section.subsections ?? []).map((sub) => ({ id: sub.id, parent: section.id, title: sub.title, text: sub.blocks.map(blockText).join(" ") })),
]);
const GROUPS = [
  { title: "开始使用", ids: ["what", "start", "pages", "account"] },
  { title: "求职工作流", ids: ["profile", "discover", "import", "jobs", "matches", "applications", "agent"] },
  { title: "配置与帮助", ids: ["keys", "mobile", "config", "faq", "limits"] },
];

export function GuideNavigation() {
  const directory = useRef<HTMLElement>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState("what");
  const needle = query.trim().toLocaleLowerCase();
  const hits = needle ? ENTRIES.filter((entry) => `${entry.title} ${entry.text}`.toLocaleLowerCase().includes(needle)) : [];

  useEffect(() => {
    if (open) directory.current?.scrollIntoView?.({ block: "start", behavior: "instant" });
  }, [open]);

  useEffect(() => {
    // Observe only chapter starts; short subsections should not steal selection.
    if (typeof IntersectionObserver === "undefined") return;
    const visible = new Map<string, number>();
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) visible.set(entry.target.id, entry.boundingClientRect.top);
        else visible.delete(entry.target.id);
      }
      const first = [...visible].sort((a, b) => a[1] - b[1])[0];
      if (first) setActive(first[0]);
    }, { rootMargin: "-120px 0px -55% 0px", threshold: 0 });
    for (const section of GUIDE_SECTIONS) {
      const element = document.getElementById(section.id);
      if (element) observer.observe(element);
    }
    return () => observer.disconnect();
  }, []);

  function follow(parent: string) {
    setActive(parent);
    setOpen(false);
  }

  return (
    <aside ref={directory} className="sticky top-14 scroll-mt-14 z-20 self-start rounded-2xl border border-slate-200 bg-white/95 backdrop-blur lg:top-20 lg:z-auto lg:border-0 lg:bg-transparent">
      <button type="button" aria-expanded={open} aria-controls="guide-directory" onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between gap-2 px-4 py-3 text-sm font-medium text-slate-800 lg:hidden">
        <span>章节目录 · {GUIDE_SECTIONS.find((section) => section.id === active)?.title}</span>
        <ChevronDown className={`size-4 shrink-0 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden />
      </button>
      <nav id="guide-directory" aria-label="手册目录" className={`${open ? "block" : "hidden"} max-h-[70dvh] overflow-y-auto p-3 lg:block lg:max-h-[calc(100dvh-7rem)] lg:p-0 lg:pr-4`}>
        <label htmlFor="guide-search" className="sr-only">搜索手册</label>
        <div className="relative mb-4">
          <Search className="pointer-events-none absolute left-3 top-3 size-4 text-slate-400" aria-hidden />
          <input id="guide-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索章节与操作…" className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-9 pr-9 [&::-webkit-search-cancel-button]:appearance-none text-xs text-slate-800 outline-none focus:border-sky-400 focus:ring-2 focus:ring-sky-100" />
          {query ? <button type="button" aria-label="清空搜索" onClick={() => setQuery("")} className="absolute right-2 top-2 rounded p-1 text-slate-500 hover:bg-slate-100"><X className="size-4" aria-hidden /></button> : null}
        </div>
        {needle ? (
          <div>
            <p className="mb-2 px-2 text-xs text-slate-500" role="status">找到 {hits.length} 个相关章节</p>
            {hits.length === 0 ? <p className="px-2 py-4 text-xs leading-6 text-slate-500">没有找到结果，试试「画像」「导入」或「取消」。</p> : hits.map((hit) => {
              const index = hit.text.toLocaleLowerCase().indexOf(needle);
              const snippet = hit.text.slice(Math.max(0, index - 18), Math.max(0, index - 18) + 70).replace(/\*\*|`/g, "");
              return <a key={hit.id} href={`#${hit.id}`} onClick={() => follow(hit.parent)} className="mb-1 block rounded-lg p-2 hover:bg-sky-50">
                <span className="block text-xs font-medium text-slate-800">{hit.title}</span>
                <span className="mt-1 block text-[11px] leading-5 text-slate-500">{snippet}…</span>
              </a>;
            })}
          </div>
        ) : GROUPS.map((group) => (
          <div key={group.title} className="mb-5">
            <p className="mb-2 px-2 text-[10px] font-semibold tracking-widest text-slate-400">{group.title}</p>
            {GUIDE_SECTIONS.filter((section) => group.ids.includes(section.id)).map((section) => (
              <div key={section.id}>
                <a href={`#${section.id}`} onClick={() => follow(section.id)} aria-current={active === section.id ? "location" : undefined}
                  className={`block rounded-lg px-2 py-2 text-xs transition-colors ${active === section.id ? "bg-sky-50 font-semibold text-sky-700" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"}`}>
                  {section.title}
                </a>
                {active === section.id && section.subsections?.length ? <div className="ml-2 mt-1 border-l border-slate-200 pl-2">
                  {section.subsections.map((sub) => <a key={sub.id} href={`#${sub.id}`} onClick={() => follow(section.id)} className="block px-2 py-1.5 text-[11px] text-slate-500 hover:text-sky-700">{sub.title}</a>)}
                </div> : null}
              </div>
            ))}
          </div>
        ))}
        <a href="#guide-top" className="block border-t border-slate-200 px-2 pt-4 text-xs text-slate-500 hover:text-sky-700">回到手册顶部 ↑</a>
      </nav>
    </aside>
  );
}
