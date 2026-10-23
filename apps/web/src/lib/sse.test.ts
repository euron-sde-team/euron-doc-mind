import { describe, expect, it } from "vitest";

import { SseParser } from "@/lib/sse";

describe("SseParser", () => {
  it("parses named events with JSON data", () => {
    const parser = new SseParser();
    const events = parser.push('event: delta\ndata: {"text":"Hello"}\n\nevent: done\ndata: {}\n\n');
    expect(events).toEqual([
      { event: "delta", data: '{"text":"Hello"}' },
      { event: "done", data: "{}" },
    ]);
  });

  it("buffers events split across chunks and normalises CRLF", () => {
    const parser = new SseParser();
    expect(parser.push('event: sources\r\ndata: {"sou')).toEqual([]);
    expect(parser.push('rces":[]}\r\n\r\n')).toEqual([
      { event: "sources", data: '{"sources":[]}' },
    ]);
  });

  it("ignores keep-alive comments and joins multi-line data", () => {
    const parser = new SseParser();
    expect(parser.push(": ping\n\ndata: line one\ndata: line two\n\n")).toEqual([
      { event: "message", data: "line one\nline two" },
    ]);
  });
});
