import { File, FileCode2, FileSpreadsheet, FileText, FileType2, Presentation } from "lucide-react";

import { cn } from "@/lib/cn";
import type { DocumentKind } from "@/lib/types";

const KINDS: Record<DocumentKind, { icon: typeof File; className: string; label: string }> = {
  pdf: {
    icon: FileText,
    className: "bg-[#fdeeee] text-[#d1383d] dark:bg-[#3a1717] dark:text-[#ff8a8f]",
    label: "PDF",
  },
  docx: {
    icon: FileType2,
    className: "bg-[#ecf0fe] text-[#3b5bdb] dark:bg-[#18213d] dark:text-[#91a7ff]",
    label: "Word",
  },
  xlsx: {
    icon: FileSpreadsheet,
    className: "bg-[#e8f6ee] text-[#2b8a57] dark:bg-[#12291c] dark:text-[#69db9c]",
    label: "Excel",
  },
  csv: {
    icon: FileSpreadsheet,
    className: "bg-[#e8f6ee] text-[#2b8a57] dark:bg-[#12291c] dark:text-[#69db9c]",
    label: "CSV",
  },
  pptx: {
    icon: Presentation,
    className: "bg-[#fff1e6] text-[#d9590a] dark:bg-[#33200f] dark:text-[#ffa94d]",
    label: "PowerPoint",
  },
  txt: { icon: File, className: "bg-muted text-muted-foreground", label: "Text" },
  md: { icon: File, className: "bg-muted text-muted-foreground", label: "Markdown" },
  html: {
    icon: FileCode2,
    className: "bg-[#f4ecfd] text-[#8241c9] dark:bg-[#2a183d] dark:text-[#c39bf2]",
    label: "HTML",
  },
};

export function kindLabel(kind: DocumentKind): string {
  return KINDS[kind]?.label ?? kind.toUpperCase();
}

export function KindIcon({ kind, className }: { kind: DocumentKind; className?: string }) {
  const { icon: Icon, className: tone } = KINDS[kind] ?? KINDS.txt;
  return (
    <span
      className={cn("flex size-8 shrink-0 items-center justify-center rounded-lg", tone, className)}
      aria-hidden
    >
      <Icon className="size-4" />
    </span>
  );
}
