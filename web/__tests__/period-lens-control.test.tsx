import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const replace = vi.fn();
const searchParams = new URLSearchParams("from=2026-08-12&to=2026-08-18");
const mockPathname = vi.fn(() => "/app/journal");
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => mockPathname(),
  useSearchParams: () => searchParams,
}));

import { PeriodLens } from "@/components/app/period-lens";

describe("period lens", () => {
  it("shows the window every figure on the page is measured over", () => {
    render(<PeriodLens />);
    expect(screen.getByText("2026-08-12 → 2026-08-18")).toBeInTheDocument();
  });

  it("says what it is, so the range is not a bare pair of dates", () => {
    render(<PeriodLens />);
    expect(screen.getByRole("button", { name: /period/i })).toBeInTheDocument();
  });

  it("keeps the preset group closed until asked", () => {
    render(<PeriodLens />);
    expect(screen.queryByRole("group", { name: /period presets/i })).not.toBeInTheDocument();
  });

  it("opens a group of the windows a trader reviews in", () => {
    // Plain buttons in a labelled group, not role="menu": the menu pattern
    // requires arrow-key navigation, focus moving in on open, and focus
    // returning to the trigger on Escape, none of which this implements.
    render(<PeriodLens />);
    fireEvent.click(screen.getByRole("button", { name: /period/i }));
    expect(screen.getByRole("group", { name: /period presets/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Last 7 days" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Year to date" })).toBeInTheDocument();
  });

  it("writes the choice to the URL, so the period is linkable and shared", () => {
    render(<PeriodLens />);
    fireEvent.click(screen.getByRole("button", { name: /period/i }));
    fireEvent.click(screen.getByRole("button", { name: "Last 7 days" }));
    expect(replace).toHaveBeenCalled();
    const target = replace.mock.calls.at(-1)![0] as string;
    expect(target.startsWith("/app/journal?")).toBe(true);
    expect(target).toContain("from=");
    expect(target).toContain("to=");
  });

  it("reports expanded state to assistive technology", () => {
    render(<PeriodLens />);
    const trigger = screen.getByRole("button", { name: /period/i });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
  });

  it("closes on Escape", () => {
    render(<PeriodLens />);
    fireEvent.click(screen.getByRole("button", { name: /period/i }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("group", { name: /period presets/i })).not.toBeInTheDocument();
  });
});

describe("routes the range does not govern", () => {
  it.each([
    ["a single trade", "/app/journal/42"],
    ["New Trade", "/app/trades/new"],
    ["Weekly Recap, which keeps its week selector", "/app/reviews/weekly"],
    ["Daily Debrief, which keeps its day selector", "/app/reviews/daily"],
    ["Strategy Profile", "/app/strategy"],
    ["Settings", "/app/settings"],
  ])("renders nothing on %s", (_name, pathname) => {
    // Hidden, not inert. A lens shown beside a week selector claims to govern a
    // page it does not, and the reader has no way to tell which one won.
    mockPathname.mockReturnValue(pathname);
    const { container } = render(<PeriodLens />);
    expect(container).toBeEmptyDOMElement();
  });

  it("comes back on a surface it does govern", () => {
    mockPathname.mockReturnValue("/app/analytics");
    render(<PeriodLens />);
    expect(screen.getByRole("button", { name: /period/i })).toBeInTheDocument();
  });
});
