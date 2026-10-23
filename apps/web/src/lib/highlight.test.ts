import { describe, expect, it } from "vitest";

import { sliceHighlight, snippetRuns } from "@/lib/highlight";

const S = String.fromCharCode(1);
const E = String.fromCharCode(2);

describe("snippetRuns", () => {
  it("splits matches marked with control characters", () => {
    expect(snippetRuns(`Our ${S}parental${E} ${S}leave${E} policy`)).toEqual([
      { text: "Our ", match: false },
      { text: "parental", match: true },
      { text: " ", match: false },
      { text: "leave", match: true },
      { text: " policy", match: false },
    ]);
  });

  it("treats HTML in documents as plain text", () => {
    expect(snippetRuns(`<script>x</script> ${S}hit${E}`)[0]).toEqual({ text: "<script>x</script> ", match: false });
  });

  it("tolerates an unterminated match", () => {
    expect(snippetRuns(`a ${S}b`)).toEqual([
      { text: "a ", match: false },
      { text: "b", match: true },
    ]);
  });
});

describe("sliceHighlight", () => {
  it("clamps ranges to the text", () => {
    expect(sliceHighlight("abcdef", 2, 4)).toEqual(["ab", "cd", "ef"]);
    expect(sliceHighlight("abc", 5, 9)).toEqual(["abc", "", ""]);
    expect(sliceHighlight("abc", -3, 1)).toEqual(["", "a", "bc"]);
  });
});
