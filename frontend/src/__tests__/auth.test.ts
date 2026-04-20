import { describe, it, expect, beforeEach, vi } from "vitest";
import { getToken, setToken, clearToken, isAuthenticated } from "@/lib/auth";

const store: Record<string, string> = {};

beforeEach(() => {
  Object.keys(store).forEach((k) => delete store[k]);
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = v; },
    removeItem: (k: string) => { delete store[k]; },
  });
});

describe("auth", () => {
  it("setToken + getToken round-trip", () => {
    setToken("abc123");
    expect(getToken()).toBe("abc123");
  });

  it("clearToken removes token", () => {
    setToken("abc123");
    clearToken();
    expect(getToken()).toBeNull();
  });

  it("isAuthenticated true when token exists", () => {
    setToken("token");
    expect(isAuthenticated()).toBe(true);
  });

  it("isAuthenticated false when no token", () => {
    expect(isAuthenticated()).toBe(false);
  });
});
