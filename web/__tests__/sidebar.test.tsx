import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const mockPathname = vi.fn(() => "/app");
vi.mock("next/navigation", () => ({ usePathname: () => mockPathname() }));

import { Sidebar } from "@/components/app/sidebar";
import { APP_DESTINATIONS } from "@/lib/app/navigation";

describe("sidebar", () => {
  it("links to every destination", () => {
    mockPathname.mockReturnValue("/app");
    render(<Sidebar />);
    for (const d of APP_DESTINATIONS) {
      expect(screen.getByRole("link", { name: d.label })).toHaveAttribute("href", d.href);
    }
  });

  it("offers logging a trade as the primary action", () => {
    mockPathname.mockReturnValue("/app");
    render(<Sidebar />);
    expect(screen.getByRole("link", { name: "Log completed trade" })).toHaveAttribute(
      "href",
      "/app/trades/new",
    );
  });

  it("marks the current destination for assistive technology, not just visually", () => {
    mockPathname.mockReturnValue("/app/journal");
    render(<Sidebar />);
    expect(screen.getByRole("link", { name: "Journal" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("marks exactly one destination current", () => {
    mockPathname.mockReturnValue("/app/journal/42");
    render(<Sidebar />);
    const current = screen
      .getAllByRole("link")
      .filter((el) => el.getAttribute("aria-current") === "page");
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveAccessibleName("Journal");
  });

  it("names the navigation so a screen reader can distinguish it", () => {
    mockPathname.mockReturnValue("/app");
    render(<Sidebar />);
    expect(screen.getByRole("navigation", { name: "Sections" })).toBeInTheDocument();
  });
});
