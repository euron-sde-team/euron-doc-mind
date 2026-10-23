import { describe, expect, it } from "vitest";

import { citedNumbers, parseAnswer, parseInline } from "@/lib/markdown";

describe("parseInline", () => {
  it("separates text, citations, bold and code", () => {
    expect(parseInline("Leave is **24 days** [1] per `year` [2].")).toEqual([
      { type: "text", text: "Leave is " },
      { type: "bold", text: "24 days" },
      { type: "text", text: " " },
      { type: "cite", n: 1 },
      { type: "text", text: " per " },
      { type: "code", text: "year" },
      { type: "text", text: " " },
      { type: "cite", n: 2 },
      { type: "text", text: "." },
    ]);
  });

  it("never produces markup from model output", () => {
    const inlines = parseInline('<img src=x onerror="alert(1)"> [3]');
    expect(inlines[0]).toEqual({ type: "text", text: '<img src=x onerror="alert(1)"> ' });
  });
});

describe("parseAnswer", () => {
  it("groups bullets into a list and keeps paragraphs", () => {
    const blocks = parseAnswer("The main risks:\n- LiDAR supply [1]\n- Customer concentration [1]\n\nBoth are tracked.");
    expect(blocks.map((b) => b.type)).toEqual(["paragraph", "list", "paragraph"]);
    const list = blocks[1];
    expect(list?.type === "list" && list.items.length).toBe(2);
  });

  it("recognises numbered lists and headings", () => {
    const blocks = parseAnswer("## Steps\n1. Hold the button [1]\n2. Wait [1]");
    expect(blocks[0]?.type).toBe("heading");
    expect(blocks[1]).toMatchObject({ type: "list", ordered: true });
  });
});

describe("citedNumbers", () => {
  it("lists citations once, in order of appearance", () => {
    expect(citedNumbers("A [2]. B [1][2]. C [3].")).toEqual([2, 1, 3]);
  });
});
