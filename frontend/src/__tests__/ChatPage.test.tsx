import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

// jsdom doesn't implement scrollIntoView
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

// We test the MessageBubble rendering by importing ChatPage and checking
// the rendered output. Since ChatPage uses streamChat, we mock the API.
vi.mock("@/lib/api", () => ({
  streamChat: vi.fn().mockReturnValue((async function* () {})()),
  api: { get: vi.fn(), post: vi.fn() },
  ApiError: class extends Error {},
}));

vi.mock("@/lib/auth", () => ({
  getToken: () => "fake-token",
  isAuthenticated: () => true,
}));

import { ChatPage } from "@/pages/ChatPage";

function renderChat(search = "") {
  return render(
    <MemoryRouter initialEntries={[`/chat${search}`]}>
      <ChatPage />
    </MemoryRouter>,
  );
}

describe("ChatPage", () => {
  it("renders without crashing", () => {
    renderChat();
    expect(screen.getByPlaceholderText(/type your question/i)).toBeInTheDocument();
  });

  it("shows conversation title from category param", () => {
    renderChat("?category=health-insurance");
    expect(screen.getByRole("heading", { name: /Health Insurance/i })).toBeInTheDocument();
  });

  it("shows default title when no category", () => {
    renderChat();
    expect(screen.getByText(/Conversation/i)).toBeInTheDocument();
  });

  it("submit button disabled when input empty", () => {
    renderChat();
    const btn = screen.getByRole("button", { name: "" }); // Send icon button
    expect(btn).toBeDisabled();
  });
});
