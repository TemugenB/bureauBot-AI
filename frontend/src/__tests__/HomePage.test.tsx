import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { HomePage } from "@/pages/HomePage";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock("@/lib/api", () => ({
  api: {
    get: vi.fn().mockResolvedValue([
      { id: "1", title: "Residence Permit Renewal", featured: true },
      { id: "2", title: "Health Insurance", featured: true },
      { id: "3", title: "Address Card", featured: true },
    ]),
  },
}));

vi.mock("@/lib/auth", () => ({
  getToken: () => "fake-token",
  isAuthenticated: () => true,
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <HomePage />
    </MemoryRouter>,
  );
}

describe("HomePage", () => {
  it("renders featured cards", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Residence Permit Renewal")).toBeInTheDocument();
    });
    expect(screen.getByText("Health Insurance")).toBeInTheDocument();
    expect(screen.getByText("Address Card")).toBeInTheDocument();
  });

  it("search form navigates to chat", async () => {
    renderPage();
    const input = screen.getByPlaceholderText(/renew my residence/i);
    await userEvent.type(input, "How do I get a TAJ card?");
    await userEvent.click(screen.getByRole("button", { name: /ask/i }));
    expect(mockNavigate).toHaveBeenCalledWith(
      expect.stringContaining("/chat?q="),
    );
  });
});
