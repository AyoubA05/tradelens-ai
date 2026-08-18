import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppShell } from "@/components/app/app-shell";

function renderShell() {
  return render(
    <AppShell
      sidebar={<nav aria-label="Sections">sidebar</nav>}
      top={<div>top</div>}
      drawer={<div>drawer</div>}
      bottomNav={<nav aria-label="Primary">bottom</nav>}
    >
      <h1>Overview</h1>
    </AppShell>,
  );
}

describe("app shell", () => {
  it("renders one main landmark for the page content", () => {
    renderShell();
    expect(screen.getAllByRole("main")).toHaveLength(1);
  });

  it("gives main the id the skip link targets", () => {
    renderShell();
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
  });

  it("makes main focusable so the skip link can land on it", () => {
    // Without tabindex the browser moves the URL fragment but leaves focus
    // where it was, so the next Tab walks straight back into the navigation
    // the user was trying to skip.
    renderShell();
    expect(screen.getByRole("main")).toHaveAttribute("tabindex", "-1");
  });

  it("renders each region it is given", () => {
    renderShell();
    expect(screen.getByText("sidebar")).toBeInTheDocument();
    expect(screen.getByText("top")).toBeInTheDocument();
    expect(screen.getByText("drawer")).toBeInTheDocument();
    expect(screen.getByText("bottom")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Overview" })).toBeInTheDocument();
  });

  it("puts the skip link first in the tab order", () => {
    const { container } = renderShell();
    const focusable = container.querySelectorAll("a, button, [tabindex]:not([tabindex='-1'])");
    expect(focusable[0]).toHaveTextContent("Skip to main content");
  });
});
