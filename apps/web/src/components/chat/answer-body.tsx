"use client";

import { Fragment, type ReactNode } from "react";

import { CitationChip } from "@/components/chat/citation-chip";
import { parseAnswer, type Inline } from "@/lib/markdown";
import type { Citation, Source } from "@/lib/types";

export function AnswerBody({
  text,
  workspace,
  citations = [],
  sources = [],
  streaming = false,
}: {
  text: string;
  workspace: string;
  citations?: Citation[];
  sources?: Source[];
  streaming?: boolean;
}) {
  const byNumber = new Map(citations.map((c) => [c.n, c]));
  const sourceByNumber = new Map(sources.map((s) => [s.n, s]));

  const inline = (items: Inline[], key: string): ReactNode =>
    items.map((item, index) => {
      const id = `${key}-${index}`;
      switch (item.type) {
        case "bold":
          return (
            <strong key={id} className="font-semibold">
              {item.text}
            </strong>
          );
        case "code":
          return (
            <code key={id} className="bg-muted rounded px-1 py-0.5 font-mono text-[12.5px]">
              {item.text}
            </code>
          );
        case "cite":
          return (
            <CitationChip
              key={id}
              n={item.n}
              workspace={workspace}
              citation={byNumber.get(item.n)}
              source={sourceByNumber.get(item.n)}
            />
          );
        default:
          return <Fragment key={id}>{item.text}</Fragment>;
      }
    });

  const blocks = parseAnswer(text);
  return (
    <div className="text-foreground space-y-3 text-[14.5px] leading-[1.7]">
      {blocks.map((block, index) => {
        const key = `b${index}`;
        if (block.type === "heading") {
          return (
            <p key={key} className="font-semibold">
              {inline(block.inlines, key)}
            </p>
          );
        }
        if (block.type === "list") {
          const List = block.ordered ? "ol" : "ul";
          return (
            <List
              key={key}
              className={
                block.ordered
                  ? "list-decimal space-y-1.5 pl-5"
                  : "marker:text-subtle list-disc space-y-1.5 pl-5"
              }
            >
              {block.items.map((item, i) => (
                <li key={`${key}-${i}`} className="pl-1">
                  {inline(item, `${key}-${i}`)}
                </li>
              ))}
            </List>
          );
        }
        return <p key={key}>{inline(block.inlines, key)}</p>;
      })}
      {streaming ? (
        <span
          className="animate-pulse-dot bg-primary inline-block h-4 w-1.5 rounded-sm align-middle"
          aria-hidden
        />
      ) : null}
    </div>
  );
}
