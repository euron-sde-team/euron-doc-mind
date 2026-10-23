/**
 * A deliberately small Markdown subset for answers: paragraphs, bullet and numbered lists,
 * **bold**, `code` and [n] citation markers. It produces data, not HTML; the renderer turns
 * it into React elements, so model output can never inject markup.
 */
export type Inline =
  | { type: "text"; text: string }
  | { type: "bold"; text: string }
  | { type: "code"; text: string }
  | { type: "cite"; n: number };

export type Block =
  | { type: "paragraph"; inlines: Inline[] }
  | { type: "list"; ordered: boolean; items: Inline[][] }
  | { type: "heading"; inlines: Inline[] };

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\[\d{1,2}\])/g;
const BULLET = /^\s*[-*\u2022]\s+/;
const NUMBERED = /^\s*\d{1,3}[.)]\s+/;

export function parseInline(text: string): Inline[] {
  const inlines: Inline[] = [];
  for (const part of text.split(INLINE)) {
    if (!part) continue;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      inlines.push({ type: "bold", text: part.slice(2, -2) });
    } else if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      inlines.push({ type: "code", text: part.slice(1, -1) });
    } else if (/^\[\d{1,2}\]$/.test(part)) {
      inlines.push({ type: "cite", n: Number(part.slice(1, -1)) });
    } else {
      inlines.push({ type: "text", text: part });
    }
  }
  return inlines;
}

export function parseAnswer(markdown: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: Inline[][] } | null = null;

  const flushParagraph = () => {
    if (paragraph.length)
      blocks.push({ type: "paragraph", inlines: parseInline(paragraph.join(" ")) });
    paragraph = [];
  };
  const flushList = () => {
    if (list) blocks.push({ type: "list", ...list });
    list = null;
  };

  for (const raw of markdown.split("\n")) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }
    const heading = /^#{1,4}\s+(.*)$/.exec(line);
    if (heading?.[1]) {
      flushParagraph();
      flushList();
      blocks.push({ type: "heading", inlines: parseInline(heading[1]) });
      continue;
    }
    const ordered = NUMBERED.test(line);
    if (ordered || BULLET.test(line)) {
      flushParagraph();
      if (!list || list.ordered !== ordered) {
        flushList();
        list = { ordered, items: [] };
      }
      list.items.push(parseInline(line.replace(ordered ? NUMBERED : BULLET, "")));
      continue;
    }
    flushList();
    paragraph.push(line.trim());
  }
  flushParagraph();
  flushList();
  return blocks;
}

/** Citation numbers in order of first appearance. */
export function citedNumbers(markdown: string): number[] {
  const seen: number[] = [];
  for (const match of markdown.matchAll(/\[(\d{1,2})\]/g)) {
    const n = Number(match[1]);
    if (!seen.includes(n)) seen.push(n);
  }
  return seen;
}
