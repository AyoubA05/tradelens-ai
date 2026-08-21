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

  it("moves focus into the More sheet when it opens", () => {
    renderShell();
    fireEvent.click(screen.getByRole("button", { name: "More" }));
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
    // MoreSheet is a role="dialog" like the drawer, and the drawer is already
    // closed at this point in the test, so this is unambiguous proof the
    // sheet itself closed rather than a coincidence of two overlays sharing
    // a role.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
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

  // The production panel currently holds exactly one focusable element (the
  // close button), which makes "wrap to first" and "wrap to last" the same
  // no-op whether the trap runs or not — jsdom does no native Tab traversal,
  // so with a single element activeElement never has anywhere else to go.
  // That makes a one-element fixture non-discriminating: it would pass even
  // if the wrap-around branching were deleted entirely. To pin the actual
  // contract (cycling among N elements, not just "focus stayed put"), a
  // second real focusable element is injected into the live panel here, in
  // the test only — production stays a single-control panel until a later
  // phase actually adds a second control.
  function injectSecondFocusable(dialog: HTMLElement): HTMLButtonElement {
    const extra = document.createElement("button");
    extra.type = "button";
    extra.textContent = "Extra test control";
    dialog.appendChild(extra);
    return extra;
  }

  it("wraps Tab from the last focusable element to the first", () => {
    renderShell();
    const dialog = openDrawer();
    injectSecondFocusable(dialog);
    const focusables = focusablesIn(dialog);
    expect(focusables.length).toBeGreaterThan(1);
    const first = focusables[0];
    const last = focusables[focusables.length - 1];

    last.focus();
    expect(document.activeElement).toBe(last);

    fireEvent.keyDown(document, { key: "Tab" });

    expect(document.activeElement).toBe(first);
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it("wraps Shift+Tab from the first focusable element to the last", () => {
    renderShell();
    const dialog = openDrawer();
    injectSecondFocusable(dialog);
    const focusables = focusablesIn(dialog);
    expect(focusables.length).toBeGreaterThan(1);
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
    injectSecondFocusable(dialog);
    const focusables = focusablesIn(dialog);
    expect(focusables.length).toBeGreaterThan(1);
    focusables[0].focus();

    // Cycle Tab a few more times than there are focusable elements; focus
    // should never escape the panel.
    for (let i = 0; i < focusables.length * 3; i += 1) {
      fireEvent.keyDown(document, { key: "Tab" });
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
  });

  // The More sheet's panel already renders several focusable elements (the
  // close button plus the overflow links), so cycling is observable without
  // injecting an extra control the way the drawer's single-control panel
  // needs.
  function openMoreSheet() {
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    return screen.getByRole("dialog");
  }

  it("wraps Tab from the last focusable element to the first in the More sheet", () => {
    renderShell();
    const dialog = openMoreSheet();
    const focusables = focusablesIn(dialog);
    expect(focusables.length).toBeGreaterThan(1);
    const first = focusables[0];
    const last = focusables[focusables.length - 1];

    last.focus();
    expect(document.activeElement).toBe(last);

    fireEvent.keyDown(document, { key: "Tab" });

    expect(document.activeElement).toBe(first);
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it("wraps Shift+Tab from the first focusable element to the last in the More sheet", () => {
    renderShell();
    const dialog = openMoreSheet();
    const focusables = focusablesIn(dialog);
    expect(focusables.length).toBeGreaterThan(1);
    const first = focusables[0];
    const last = focusables[focusables.length - 1];

    first.focus();
    expect(document.activeElement).toBe(first);

    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });

    expect(document.activeElement).toBe(last);
    expect(dialog.contains(document.activeElement)).toBe(true);
  });
});

describe("focus restoration", () => {
  it("restores focus to the opening control when the drawer closes", () => {
    renderShell();
    const opener = screen.getByRole("button", { name: /ask about a trade/i });
    // Simulate the pre-open state a keyboard or mouse user actually leaves
    // behind: the control that opened the overlay has focus at click time.
    opener.focus();
    fireEvent.click(opener);
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(document.activeElement).toBe(opener);
  });

  it("restores focus to the opening control when the More sheet closes", () => {
    renderShell();
    const opener = screen.getByRole("button", { name: "More" });
    opener.focus();
    fireEvent.click(opener);
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(document.activeElement).toBe(opener);
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

  // The More sheet's own root div sits one level deeper than the drawer's —
  // it is mounted inside BottomNav's fragment, a sibling of the phone <nav>,
  // rather than as a direct child of the shell root — so "outside the sheet"
  // means the sheet root's actual DOM siblings, not the shell's top-level
  // children. Walking up from the dialog itself keeps this correct instead of
  // assuming a particular nesting depth.
  function siblingsOfDialogRoot(dialog: HTMLElement) {
    const root = dialog.parentElement;
    return Array.from(root?.parentElement?.children ?? []).filter((child) => child !== root);
  }

  it("marks content outside the More sheet inert while it is open", () => {
    renderShell();
    fireEvent.click(screen.getByRole("button", { name: "More" }));

    const dialog = screen.getByRole("dialog");
    const siblings = siblingsOfDialogRoot(dialog);
    expect(siblings.length).toBeGreaterThan(0);
    for (const sibling of siblings) {
      expect(sibling.hasAttribute("inert")).toBe(true);
    }
  });

  it("removes inert from the background once the More sheet closes", () => {
    renderShell();
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    const dialog = screen.getByRole("dialog");
    const siblings = siblingsOfDialogRoot(dialog);

    fireEvent.keyDown(document, { key: "Escape" });

    for (const sibling of siblings) {
      expect(sibling.hasAttribute("inert")).toBe(false);
    }
  });
});
