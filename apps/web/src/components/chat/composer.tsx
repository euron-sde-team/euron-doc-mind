"use client";

import { ArrowUp, Square } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

export function Composer({
  onSend,
  onStop,
  busy = false,
  disabled = false,
  placeholder = "Ask anything about your documents",
  autoFocus = false,
  className,
}: {
  onSend: (question: string) => void;
  onStop?: () => void;
  busy?: boolean;
  disabled?: boolean;
  placeholder?: string;
  autoFocus?: boolean;
  className?: string;
}) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    element.style.height = "0px";
    element.style.height = `${Math.min(element.scrollHeight, 200)}px`;
  }, [value]);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    const question = value.trim();
    if (!question || busy || disabled) return;
    onSend(question);
    setValue("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form
      onSubmit={submit}
      className={cn(
        "border-input bg-card focus-within:border-ring flex items-end gap-2 rounded-2xl border p-2 pl-4 shadow-md transition-colors",
        className,
      )}
    >
      <textarea
        ref={ref}
        rows={1}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        autoFocus={autoFocus}
        maxLength={2000}
        aria-label="Question"
        className="placeholder:text-subtle max-h-[200px] min-h-6 flex-1 resize-none bg-transparent py-1.5 text-[14.5px] leading-6 outline-none"
      />
      {busy && onStop ? (
        <Button type="button" size="icon-sm" variant="secondary" onClick={onStop} aria-label="Stop">
          <Square className="!size-3 fill-current" />
        </Button>
      ) : (
        <Button
          type="submit"
          size="icon-sm"
          disabled={!value.trim() || busy || disabled}
          aria-label="Send"
        >
          <ArrowUp />
        </Button>
      )}
    </form>
  );
}
