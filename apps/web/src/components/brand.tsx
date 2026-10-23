import { cn } from "@/lib/cn";

export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden className={cn("size-7", className)}>
      <rect width="64" height="64" rx="16" fill="var(--primary)" />
      <path d="M20 16h14a14 14 0 0 1 0 28h-6v6h-8z" fill="#fff" />
      <circle cx="34" cy="30" r="5" fill="var(--primary)" />
    </svg>
  );
}

export function Wordmark({ name, className }: { name: string; className?: string }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <BrandMark />
      <span className="text-[15px] font-semibold tracking-tight">{name}</span>
    </span>
  );
}
