import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const mockPathname = vi.fn(() => "/app");
vi.mock("next/navigation", () => ({ usePathname: () => mockPathname() }));

import { BottomNav } from "@/components/app/bottom-nav";

describe("phone navigation", () => {
  it("shows the four priority destinations plus More", () => {
    mockPathname.mockReturnValue("/app");
    render(<BottomNav />);
    expect(screen.getByRole("link", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Journal" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "AI Reviews" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "More" })).toBeInTheDocument();
  });

  it("keeps the lower-frequency destinations out of the bar", () => {
    mockPathname.mockReturnValue("/app");
    render(<BottomNav />);
    expect(screen.queryByRole("link", { name: "Analytics" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Strategy Profile" })).not.toBeInTheDocument();
  });

  it("reveals them behind More", () => {
    mockPathname.mockReturnValue("/app");
    render(<BottomNav />);
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    expect(screen.getByRole("link", { name: "Analytics" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Strategy Profile" })).toBeInTheDocument();
  });

  it("closes the sheet on Escape", () => {
    mockPathname.mockReturnValue("/app");
    render(<BottomNav />);
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("link", { name: "Analytics" })).not.toBeInTheDocument();
  });

  it("marks the current destination", () => {
    mockPathname.mockReturnValue("/app/journal");
    render(<BottomNav />);
    expect(screen.getByRole("link", { name: "Journal" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("names itself so it does not collide with the sidebar in the a11y tree", () => {
    mockPathname.mockReturnValue("/app");
    render(<BottomNav />);
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
  });
});
