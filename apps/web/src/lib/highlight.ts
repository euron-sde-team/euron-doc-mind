/**
 * Search snippets arrive with matches wrapped in the control characters U+0001 and U+0002
 * (never HTML), so splitting them into text runs keeps document content inert.
 */
const START = String.fromCharCode(1);
const END = String.fromCharCode(2);

export type Run = { text: string; match: boolean };

export function snippetRuns(snippet: string): Run[] {
  const runs: Run[] = [];
  let rest = snippet;
  while (rest.length) {
    const start = rest.indexOf(START);
    if (start === -1) {
      runs.push({ text: rest, match: false });
      break;
    }
    if (start > 0) runs.push({ text: rest.slice(0, start), match: false });
    const end = rest.indexOf(END, start + 1);
    if (end === -1) {
      runs.push({ text: rest.slice(start + 1), match: true });
      break;
    }
    runs.push({ text: rest.slice(start + 1, end), match: true });
    rest = rest.slice(end + 1);
  }
  return runs.filter((run) => run.text.length > 0);
}

/** Split a section into before / highlighted / after, clamped to the text bounds. */
export function sliceHighlight(text: string, start: number, end: number): [string, string, string] {
  const from = Math.max(0, Math.min(start, text.length));
  const to = Math.max(from, Math.min(end, text.length));
  return [text.slice(0, from), text.slice(from, to), text.slice(to)];
}
