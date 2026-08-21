import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const mockPathname = vi.fn(() => "/app");
vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname(),
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { AppShell } from "@/components/app/app-shell";
import { Sidebar } from "@/components/app/sidebar";
import { BottomNav } from "@/components/app/bottom-nav";
import { PartnerDrawer, PartnerLauncher } from "@/components/app/partner-drawer";

function renderShell() {
  return render(
    <AppShell
      sidebar={<Sidebar />}
      top={<PartnerLauncher />}
      drawer={<PartnerDrawer />}
      bottomNav={<BottomNav />}
    >
      <h1>Overview</h1>
    </AppShell>,
  );
}

describe("landmarks", () => {
  it("names both navigations distinctly", () => {
    // Two unnamed <nav>s are indistinguishable in a screen reader's landmark
    // list, which is how a user ends up in the phone bar looking for the rail.
    renderShell();
    expect(screen.getByRole("navigation", { name: "Sections" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
  });

  it("has exactly one main landmark", () => {
    renderShell();
    expect(screen.getAllByRole("main")).toHaveLength(1);
  });
});

describe("keyboard operation", () => {
  it("reaches the skip link first", () => {
    const { container } = renderShell();
    const focusable = container.querySelectorAll<HTMLElement>(
      "a[href], button:not([disabled]), [tabindex]:not([tabindex='-1'])",
    );
    expect(focusable[0]).toHaveTextContent("Skip to main content");
  });

  it("points the skip link at the main landmark", () => {
    renderShell();
    const link = screen.getByRole("link", { name: "Skip to main content" });
    expect(link).toHaveAttribute("href", "#main-content");
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
  });

  it("moves focus into the drawer when it opens", () => {
    renderShell();
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));
    const dialog = screen.getByRole("dialog");
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it("closes every overlay on Escape", () => {
    renderShell();
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "More" }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("link", { name: "Analytics" })).not.toBeInTheDocument();
  });

  it("gives every interactive element an accessible name", () => {
    // An icon-only control with no name is a button a screen reader announces
    // as "button".
    const { container } = renderShell();
    const controls = container.querySelectorAll<HTMLElement>("a[href], button");
    for (const control of controls) {
      const name =
        control.textContent?.trim() ||
        control.getAttribute("aria-label") ||
        control.getAttribute("title");
      expect(name, control.outerHTML.slice(0, 120)).toBeTruthy();
    }
  });

  it("hides decorative icons from the accessibility tree", () => {
    const { container } = renderShell();
    for (const svg of container.querySelectorAll("svg")) {
      expect(svg.getAttribute("aria-hidden")).toBe("true");
    }
  });
});

describe("focus trap", () => {
  // The panel currently contains exactly one focusable element (the close
  // button), so both directions self-loop onto it. Reading the live
  // focusable set from the dialog, rather than hard-coding "the close
  // button", keeps this meaningful if a second focusable element is ever
  // added to the panel.
  function openDrawer() {
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));
    return screen.getByRole("dialog");
  }

  function focusablesIn(panel: HTMLElement) {
    return Array.from(
      panel.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])',
      ),
    );
  }

  it("wraps Tab from the last focusable element to the first", () => {
    renderShell();
    const dialog = openDrawer();
    const focusables = focusablesIn(dialog);
    const last = focusables[focusables.length - 1];

    last.focus();
    expect(document.activeElement).toBe(last);

    fireEvent.keyDown(document, { key: "Tab" });

    expect(document.activeElement).toBe(focusables[0]);
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it("wraps Shift+Tab from the first focusable element to the last", () => {
    renderShell();
    const dialog = openDrawer();
    const focusables = focusablesIn(dialog);
    const first = focusables[0];
    const last = focusables[focusables.length - 1];

    first.focus();
    expect(document.activeElement).toBe(first);

    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });

    expect(document.activeElement).toBe(last);
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it("never lets focus land outside the panel while the drawer is open", () => {
    renderShell();
    const dialog = openDrawer();
    const focusables = focusablesIn(dialog);

    // Cycle Tab a few more times than there are focusable elements; focus
    // should never escape the panel.
    for (let i = 0; i < focusables.length * 3; i += 1) {
      fireEvent.keyDown(document, { key: "Tab" });
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
  });
});

describe("inert background", () => {
  it("marks content outside the drawer inert while it is open", () => {
    const { container } = renderShell();
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));

    // Every top-level sibling of the drawer's overlay should be inert so a
    // screen reader's browse mode cannot wander behind the modal overlay,
    // matching the promise aria-modal makes.
    const dialog = screen.getByRole("dialog");
    for (const child of Array.from(container.firstElementChild?.children ?? [])) {
      if (child.contains(dialog)) continue;
      expect(child.hasAttribute("inert")).toBe(true);
    }
  });

  it("removes inert from the background once the drawer closes", () => {
    const { container } = renderShell();
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));
    fireEvent.keyDown(document, { key: "Escape" });

    for (const child of Array.from(container.firstElementChild?.children ?? [])) {
      expect(child.hasAttribute("inert")).toBe(false);
    }
  });
});
