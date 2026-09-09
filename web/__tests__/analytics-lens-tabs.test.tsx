import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LensTabs } from "@/components/app/analytics/lens-tabs";

describe("The four-lens selector", () => {
  it("names all four lenses in words, not colour alone", () => {
    render(<LensTabs active="performance" search="from=2026-08-01&to=2026-08-31" />);
    for (const label of ["Performance", "Risk", "Timing", "Setups"]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
  });

  it("puts the lens in the URL and keeps the period and filters beside it", () => {
    render(<LensTabs active="performance" search="from=2026-08-01&to=2026-08-31&asset=NQ" />);
    const href = screen.getByRole("link", { name: "Timing" }).getAttribute("href") ?? "";
    const query = new URLSearchParams(href.slice(href.indexOf("?") + 1));
    expect(query.get("lens")).toBe("timing");
    expect(query.get("from")).toBe("2026-08-01");
    expect(query.get("to")).toBe("2026-08-31");
    expect(query.get("asset")).toBe("NQ");
  });

  it("does not stack a second lens value onto an existing one", () => {
    render(<LensTabs active="risk" search="lens=risk&from=2026-08-01" />);
    const href = screen.getByRole("link", { name: "Setups" }).getAttribute("href") ?? "";
    const query = new URLSearchParams(href.slice(href.indexOf("?") + 1));
    expect(query.getAll("lens")).toEqual(["setups"]);
  });

  it("marks the active lens for assistive technology, not only by styling", () => {
    render(<LensTabs active="risk" search="" />);
    expect(screen.getByRole("link", { name: "Risk" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Timing" })).not.toHaveAttribute("aria-current");
  });

  it("is keyboard reachable: every lens is a real link with an href", () => {
    render(<LensTabs active="performance" search="" />);
    for (const link of screen.getAllByRole("link")) {
      expect(link).toHaveAttribute("href");
      expect(link).not.toHaveAttribute("tabindex", "-1");
    }
  });

  it("carries no date control of its own", () => {
    const { container } = render(<LensTabs active="performance" search="" />);
    expect(container.querySelectorAll('input[type="date"]')).toHaveLength(0);
  });
});
