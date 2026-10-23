/**
 * A minimal server-sent events reader for POST requests (EventSource only does GET).
 * Feed it decoded text chunks; it yields complete events, handling events split across
 * chunks, CRLF line endings, multi-line data and comment (keep-alive) lines.
 */
export type SseEvent = { event: string; data: string };

export class SseParser {
  private buffer = "";

  push(chunk: string): SseEvent[] {
    this.buffer += chunk.replace(/\r\n/g, "\n");
    const events: SseEvent[] = [];
    let boundary = this.buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const raw = this.buffer.slice(0, boundary);
      this.buffer = this.buffer.slice(boundary + 2);
      const parsed = parseBlock(raw);
      if (parsed) events.push(parsed);
      boundary = this.buffer.indexOf("\n\n");
    }
    return events;
  }
}

function parseBlock(raw: string): SseEvent | null {
  let event = "message";
  const data: string[] = [];
  for (const line of raw.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
  return data.length ? { event, data: data.join("\n") } : null;
}

/** POST a JSON body and dispatch each parsed event until the stream ends. */
export async function postEventStream(
  url: string,
  body: unknown,
  onEvent: (event: SseEvent) => void,
  signal?: AbortSignal,
): Promise<Response> {
  const response = await fetch(url, {
    method: "POST",
    credentials: "include",
    headers: { "content-type": "application/json", accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) return response;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SseParser();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    for (const event of parser.push(decoder.decode(value, { stream: true }))) onEvent(event);
  }
  return response;
}
