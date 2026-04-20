import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { HomePage } from "@/pages/HomePage";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

function renderPage() {
  return render(
    <MemoryRouter>
      <HomePage />
    </MemoryRouter>,
  );
}

describe("HomePage", () => {
  it("renders all 6 category cards", () => {
    renderPage();
    expect(screen.getByText("Residence Permit Renewal")).toBeInTheDocument();
    expect(screen.getByText("Health Insurance")).toBeInTheDocument();
    expect(screen.getByText("Student ID")).toBeInTheDocument();
    expect(screen.getByText("Address Card")).toBeInTheDocument();
    expect(screen.getByText("TAJ Card Application")).toBeInTheDocument();
    expect(screen.getByText("Tax ID")).toBeInTheDocument();
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
