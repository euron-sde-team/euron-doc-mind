"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { BrandMark } from "@/components/brand";
import { AnswerBody } from "@/components/chat/answer-body";
import { SourcesPanel } from "@/components/chat/sources-panel";
import { TokenMeter } from "@/components/chat/token-meter";
import { Tooltip } from "@/components/ui/tooltip";
import type { Message } from "@/lib/types";

export function UserBubble({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <div className="bg-muted max-w-[85%] rounded-2xl rounded-br-md px-4 py-2.5 text-[14.5px] leading-relaxed whitespace-pre-wrap">
        {content}
      </div>
    </div>
  );
}

function CopyAnswer({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Tooltip content={copied ? "Copied" : "Copy answer"}>
      <button
        type="button"
        aria-label="Copy answer"
        className="text-subtle hover:bg-muted hover:text-foreground rounded-md p-1 transition-colors"
        onClick={async () => {
          await navigator.clipboard.writeText(text.replace(/\s?\[\d{1,2}\]/g, ""));
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
      >
        {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      </button>
    </Tooltip>
  );
}

export function AssistantMessage({ message, workspace }: { message: Message; workspace: string }) {
  return (
    <div className="flex gap-3.5">
      <BrandMark className="mt-0.5 size-7 shrink-0" />
      <div className="min-w-0 flex-1 space-y-3">
        <AnswerBody
          text={message.content}
          workspace={workspace}
          citations={message.citations}
          sources={message.sources}
        />
        <SourcesPanel
          workspace={workspace}
          sources={message.sources}
          citations={message.citations}
        />
        <div className="flex items-center justify-between gap-3 pt-0.5">
          {message.usage ? <TokenMeter usage={message.usage} /> : <span />}
          <CopyAnswer text={message.content} />
        </div>
      </div>
    </div>
  );
}
