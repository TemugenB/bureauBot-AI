import { describe, it, expect, vi, beforeEach } from "vitest";
import { streamChat } from "@/lib/api";

function makeSSE(events: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  const raw = events.join("");
  return new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(raw));
      controller.close();
    },
  });
}

beforeEach(() => {
  vi.restoreAllMocks();
  // Mock localStorage for auth header
  vi.stubGlobal("localStorage", {
    getItem: () => "fake-token",
    setItem: () => {},
    removeItem: () => {},
  });
});

describe("streamChat", () => {
  it("parses session event", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      body: makeSSE(['event: session\ndata: {"session_id":"s1"}\n\n', "event: done\ndata: [DONE]\n\n"]),
    }));
    const events = [];
    for await (const e of streamChat("hi")) events.push(e);
    expect(events.find((e) => e.type === "session")?.data).toBe("s1");
  });

  it("parses token events", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      body: makeSSE(["data: Hello\n\n", "data:  world\n\n", "event: done\ndata: [DONE]\n\n"]),
    }));
    const tokens = [];
    for await (const e of streamChat("hi")) {
      if (e.type === "token") tokens.push(e.data);
    }
    expect(tokens.join("")).toBe("Hello world");
  });

  it("parses error event", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      body: makeSSE(['event: error\ndata: {"error":"API failed"}\n\n']),
    }));
    const events = [];
    for await (const e of streamChat("hi")) events.push(e);
    const err = events.find((e) => e.type === "error");
    expect(err?.data).toBe("API failed");
  });

  it("parses disclaimer event", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      body: makeSSE(['event: disclaimer\ndata: {"message":"unverified"}\n\n']),
    }));
    const events = [];
    for await (const e of streamChat("hi")) events.push(e);
    const disc = events.find((e) => e.type === "disclaimer");
    expect(disc?.data).toBe("unverified");
  });

  it("parses done event", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      body: makeSSE(["event: done\ndata: [DONE]\n\n"]),
    }));
    const events = [];
    for await (const e of streamChat("hi")) events.push(e);
    expect(events.some((e) => e.type === "done")).toBe(true);
  });

  it("yields error for non-ok response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500, body: null }));
    const events = [];
    for await (const e of streamChat("hi")) events.push(e);
    expect(events[0].type).toBe("error");
  });
});
