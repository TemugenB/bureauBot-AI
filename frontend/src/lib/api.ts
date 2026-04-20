import { getToken } from "./auth";

export class ApiError extends Error {
  status: number;
  data: unknown;
  constructor(message: string, status: number, data: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `http://localhost:8000/api/v1${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...authHeaders(),
      ...options.headers,
    },
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(`${res.status} ${res.statusText}`, res.status, data);
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
};

export type StreamEvent =
  | { type: "session"; data: string }
  | { type: "token"; data: string }
  | { type: "done"; data: string }
  | { type: "error"; data: string }
  | { type: "disclaimer"; data: string };

export async function* streamChat(
  message: string,
  sessionId?: string,
  jurisdiction = "HU",
): AsyncGenerator<StreamEvent> {
  const res = await fetch("http://localhost:8000/api/v1/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ message, session_id: sessionId, jurisdiction }),
  });

  if (!res.ok || !res.body) {
    yield { type: "error", data: `HTTP ${res.status}` };
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      const lines = part.split("\n");
      let eventType = "message";
      let eventData = "";

      for (const line of lines) {
        if (line.startsWith("event: ")) eventType = line.slice(7).trim();
        else if (line.startsWith("data: ")) eventData = line.slice(6);
      }

      if (!eventData && eventType === "message") continue;

      if (eventType === "session") {
        try { yield { type: "session", data: JSON.parse(eventData).session_id }; }
        catch { yield { type: "session", data: eventData }; }
      } else if (eventType === "done") {
        yield { type: "done", data: "" };
      } else if (eventType === "error") {
        try { yield { type: "error", data: JSON.parse(eventData).error }; }
        catch { yield { type: "error", data: eventData }; }
      } else if (eventType === "disclaimer") {
        try { yield { type: "disclaimer", data: JSON.parse(eventData).message }; }
        catch { yield { type: "disclaimer", data: eventData }; }
      } else {
        yield { type: "token", data: eventData.replace(/\\n/g, "\n") };
      }
    }
  }
}
