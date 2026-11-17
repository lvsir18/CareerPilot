"use client";

import type { ReactNode } from "react";

import type { AgentMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Minimal markdown renderer for LLM answers.
 *
 * The agent returns plain text that usually contains headings, bullet lists and
 * fenced code blocks. Rendering it as a single text node collapsed every line
 * break, which is why answers looked like raw model output. This renderer
 * covers the subset the agent actually emits; anything unrecognised is kept as
 * pre-wrapped text so nothing is silently dropped.
 */

const INLINE_PATTERN =
  /(`[^`\n]+`|\*\*[^*\n]+\*\*|\[[^\]\n]+\]\(https?:\/\/[^\s)]+\))/g;

function renderInline(text: string, keyBase: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let index = 0;
  INLINE_PATTERN.lastIndex = 0;
  let match = INLINE_PATTERN.exec(text);
  while (match !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    const token = match[0];
    const key = `${keyBase}-${index}`;
    index += 1;
    if (token.startsWith("`")) {
      nodes.push(
        <code
          key={key}
          className="rounded bg-slate-200/80 px-1 py-0.5 font-mono text-[0.85em] text-slate-800"
        >
          {token.slice(1, -1)}
        </code>,
      );
    } else if (token.startsWith("**")) {
      nodes.push(
        <strong key={key} className="font-semibold text-slate-900">
          {token.slice(2, -2)}
        </strong>,
      );
    } else {
      const link = /^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/.exec(token);
      const label = link?.[1];
      const href = link?.[2];
      if (label && href) {
        nodes.push(
          <a
            key={key}
            href={href}
            target="_blank"
            rel="noreferrer noopener"
            className="text-sky-700 underline underline-offset-2"
          >
            {label}
          </a>,
        );
      } else {
        nodes.push(token);
      }
    }
    lastIndex = match.index + token.length;
    match = INLINE_PATTERN.exec(text);
  }
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes;
}

type Block =
  | { kind: "code"; lang: string; code: string }
  | { kind: "heading"; level: number; text: string }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "table"; header: string[]; rows: string[][] }
  | { kind: "quote"; text: string }
  | { kind: "paragraph"; text: string };

const TABLE_DIVIDER = /^\s*\|?[\s:|-]*-[\s:|-]*\|[\s:|-]*$/;

function splitRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((cell) => cell.trim());
}

function parseBlocks(content: string): Block[] {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  const at = (index: number): string => lines[index] ?? "";
  let i = 0;
  while (i < lines.length) {
    const line = at(i);
    if (!line.trim()) {
      i += 1;
      continue;
    }

    const fence = /^\s*```(\S*)\s*$/.exec(line);
    if (fence) {
      const code: string[] = [];
      i += 1;
      while (i < lines.length && !/^\s*```\s*$/.test(at(i))) {
        code.push(at(i));
        i += 1;
      }
      i += 1;
      blocks.push({ kind: "code", lang: fence[1] ?? "", code: code.join("\n") });
      continue;
    }

    const heading = /^\s*(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push({
        kind: "heading",
        level: (heading[1] ?? "").length,
        text: heading[2] ?? "",
      });
      i += 1;
      continue;
    }

    if (/^\s*[-*+]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(at(i))) {
        items.push(at(i).replace(/^\s*[-*+]\s+/, ""));
        i += 1;
      }
      blocks.push({ kind: "list", ordered: false, items });
      continue;
    }

    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(at(i))) {
        items.push(at(i).replace(/^\s*\d+[.)]\s+/, ""));
        i += 1;
      }
      blocks.push({ kind: "list", ordered: true, items });
      continue;
    }

    if (/^\s*>\s?/.test(line)) {
      const quoted: string[] = [];
      while (i < lines.length && /^\s*>\s?/.test(at(i))) {
        quoted.push(at(i).replace(/^\s*>\s?/, ""));
        i += 1;
      }
      blocks.push({ kind: "quote", text: quoted.join("\n") });
      continue;
    }

    if (line.trim().startsWith("|") && TABLE_DIVIDER.test(at(i + 1))) {
      const header = splitRow(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && at(i).trim().startsWith("|")) {
        rows.push(splitRow(at(i)));
        i += 1;
      }
      blocks.push({ kind: "table", header, rows });
      continue;
    }

    const paragraph: string[] = [];
    while (
      i < lines.length &&
      at(i).trim() &&
      !/^\s*```/.test(at(i)) &&
      !/^\s*#{1,4}\s+/.test(at(i)) &&
      !/^\s*[-*+]\s+/.test(at(i)) &&
      !/^\s*\d+[.)]\s+/.test(at(i)) &&
      !/^\s*>\s?/.test(at(i))
    ) {
      paragraph.push(at(i));
      i += 1;
    }
    blocks.push({ kind: "paragraph", text: paragraph.join("\n") });
  }
  return blocks;
}

function tryPrettyJson(content: string): string | null {
  const trimmed = content.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(trimmed);
    if (parsed === null || typeof parsed !== "object") {
      return null;
    }
    return JSON.stringify(parsed, null, 2);
  } catch {
    return null;
  }
}

export function MarkdownLite({ content }: { content: string }) {
  const pretty = tryPrettyJson(content);
  if (pretty) {
    return (
      <pre className="overflow-x-auto rounded-lg bg-slate-900 p-3 font-mono text-[11px] leading-relaxed text-slate-100">
        {pretty}
      </pre>
    );
  }

  return (
    <div className="space-y-2 text-sm leading-relaxed text-slate-700">
      {parseBlocks(content).map((block, index) => {
        const key = `block-${index}`;
        if (block.kind === "code") {
          return (
            <pre
              key={key}
              className="overflow-x-auto rounded-lg bg-slate-900 p-3 font-mono text-[11px] leading-relaxed text-slate-100"
            >
              <code>{block.code}</code>
            </pre>
          );
        }
        if (block.kind === "heading") {
          return (
            <p
              key={key}
              className={cn(
                "font-semibold text-slate-900",
                block.level <= 2 ? "text-base" : "text-sm",
              )}
            >
              {renderInline(block.text, key)}
            </p>
          );
        }
        if (block.kind === "list") {
          const ListTag = block.ordered ? "ol" : "ul";
          return (
            <ListTag
              key={key}
              className={cn(
                "space-y-1 pl-5",
                block.ordered ? "list-decimal" : "list-disc",
              )}
            >
              {block.items.map((item, itemIndex) => (
                <li key={`${key}-${itemIndex}`}>{renderInline(item, `${key}-${itemIndex}`)}</li>
              ))}
            </ListTag>
          );
        }
        if (block.kind === "table") {
          return (
            <div key={key} className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-xs">
                <thead>
                  <tr className="bg-slate-200/60">
                    {block.header.map((cell, cellIndex) => (
                      <th
                        key={`${key}-h-${cellIndex}`}
                        className="border border-slate-300 px-2 py-1 font-medium text-slate-700"
                      >
                        {renderInline(cell, `${key}-h-${cellIndex}`)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {block.rows.map((row, rowIndex) => (
                    <tr key={`${key}-r-${rowIndex}`} className="odd:bg-white even:bg-slate-50">
                      {block.header.map((_, cellIndex) => (
                        <td
                          key={`${key}-r-${rowIndex}-${cellIndex}`}
                          className="border border-slate-300 px-2 py-1 align-top"
                        >
                          {renderInline(row[cellIndex] ?? "", `${key}-r-${rowIndex}-${cellIndex}`)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        if (block.kind === "quote") {
          return (
            <blockquote
              key={key}
              className="border-l-2 border-slate-300 pl-3 text-slate-600 whitespace-pre-wrap"
            >
              {renderInline(block.text, key)}
            </blockquote>
          );
        }
        return (
          <p key={key} className="whitespace-pre-wrap">
            {renderInline(block.text, key)}
          </p>
        );
      })}
    </div>
  );
}

export function AgentMessageBubble({ message }: { message: AgentMessage }) {
  const isUser = message.role === "user";
  return (
    <div
      className={cn(
        // w-fit keeps short messages as a compact pill instead of stretching
        // to the full row width; max-w stops long ones from getting too wide.
        "w-fit max-w-[85%] rounded-2xl px-4 py-2.5",
        isUser ? "ml-auto bg-sky-50 text-slate-800" : "mr-auto bg-slate-100 text-slate-700",
      )}
    >
      {isUser ? (
        <p className="text-sm whitespace-pre-wrap">{message.content}</p>
      ) : (
        <MarkdownLite content={message.content} />
      )}
    </div>
  );
}