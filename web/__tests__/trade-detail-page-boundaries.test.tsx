import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import Loading from "@/app/app/trades/[id]/loading";
import ErrorBoundary from "@/app/app/trades/[id]/error";
import NotFound from "@/app/app/trades/[id]/not-found";
import { routeUsesPeriod } from "@/lib/app/period";

describe("Trade Detail route boundaries", () => {
  it("the loading state says what is loading", () => {
    render(<Loading />);
    expect(screen.getByRole("status")).toHaveTextContent(/trade/i);
  });

  it("the error boundary offers a way out", () => {
    const reset = vi.fn();
    render(<ErrorBoundary error={new Error("x")} reset={reset} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    screen.getByRole("button", { name: /try again/i }).click();
    expect(reset).toHaveBeenCalled();
  });

  it("the error boundary does not leak the underlying message", () => {
    render(<ErrorBoundary error={new Error("connection refused at 10.0.0.4")} reset={() => {}} />);
    expect(screen.getByRole("alert").textContent).not.toContain("10.0.0.4");
  });

  it("not-found reads as genuinely not-found, with no hint that the trade might exist for someone else", () => {
    render(<NotFound />);
    const text = screen.getByRole("heading").parentElement?.textContent ?? "";
    expect(text.toLowerCase()).not.toMatch(/permission|belongs to|another (account|user)|not yours/);
  });

  it("not-found offers a way back into the journal", () => {
    render(<NotFound />);
    expect(screen.getByRole("link", { name: /journal/i })).toHaveAttribute("href", "/app/journal");
  });

  it("is not governed by the global period lens — a single trade has one date", () => {
    // Design decision #3: a period selector on this route would be a second
    // control claiming the same temporal scope the trade's own date answers.
    expect(routeUsesPeriod("/app/trades/42")).toBe(false);
  });
});
