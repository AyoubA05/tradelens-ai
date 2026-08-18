import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LoadingState, Skeleton } from "@/components/app/states/loading-state";
import { EmptyState } from "@/components/app/states/empty-state";
import { ErrorState } from "@/components/app/states/error-state";

describe("loading", () => {
  it("announces itself rather than showing a silent grey box", () => {
    render(<LoadingState label="Loading your trades" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading your trades");
  });

  it("hides decorative skeletons from assistive technology", () => {
    const { container } = render(<Skeleton />);
    expect(container.firstChild).toHaveAttribute("aria-hidden", "true");
  });
});

describe("empty", () => {
  it("says what the screen is for and offers the action that fills it", () => {
    render(
      <EmptyState
        title="No trades in this period"
        description="Widen the period, or log a completed trade."
        action={{ href: "/app/trades/new", label: "Log completed trade" }}
      />,
    );
    expect(screen.getByRole("heading", { name: "No trades in this period" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Log completed trade" })).toHaveAttribute(
      "href",
      "/app/trades/new",
    );
  });

  it("works without an action", () => {
    render(<EmptyState title="Nothing here yet" description="It will fill as you log trades." />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});

describe("error", () => {
  it("is announced assertively, because it interrupts what the reader wanted", () => {
    render(<ErrorState description="That period could not be loaded." />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("offers a way out", () => {
    const onRetry = vi.fn();
    render(<ErrorState description="That period could not be loaded." retry={{ onRetry }} />);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("does not apologise or blame the reader", () => {
    render(<ErrorState description="That period could not be loaded." />);
    const text = screen.getByRole("alert").textContent ?? "";
    expect(text.toLowerCase()).not.toMatch(/sorry|oops|whoops/);
  });
});
