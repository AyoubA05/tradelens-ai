import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import Loading from "@/app/app/loading";
import ErrorBoundary from "@/app/app/error";

describe("route boundaries", () => {
  it("the loading state says what is loading", () => {
    render(<Loading />);
    expect(screen.getByRole("status")).toHaveTextContent(/overview/i);
  });

  it("the error boundary offers a way out", () => {
    const reset = vi.fn();
    render(<ErrorBoundary error={new Error("x")} reset={reset} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    screen.getByRole("button", { name: /try again/i }).click();
    expect(reset).toHaveBeenCalled();
  });

  it("the error boundary does not leak the underlying message", () => {
    // A backend error string can carry internals a trader should not see.
    render(<ErrorBoundary error={new Error("connection refused at 10.0.0.4")} reset={() => {}} />);
    expect(screen.getByRole("alert").textContent).not.toContain("10.0.0.4");
  });
});
