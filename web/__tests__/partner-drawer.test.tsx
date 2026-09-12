import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PartnerDrawer, PartnerLauncher } from "@/components/app/partner-drawer";

function renderBoth() {
  return render(
    <>
      <PartnerLauncher />
      <PartnerDrawer />
    </>,
  );
}

describe("partner drawer", () => {
  it("stays closed until asked", () => {
    renderBoth();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens from the launcher", () => {
    renderBoth();
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("is a named dialog, so a screen reader announces what opened", () => {
    renderBoth();
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));
    expect(screen.getByRole("dialog")).toHaveAccessibleName(/ai partner/i);
  });

  it("is modal, so the page behind it is not reachable", () => {
    renderBoth();
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-modal", "true");
  });

  it("closes on Escape", () => {
    renderBoth();
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes from its own control", () => {
    renderBoth();
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("says it reviews trades that already happened", () => {
    // The identity rule is not decoration: this surface must never read as a
    // place to ask what to trade next.
    renderBoth();
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));
    expect(screen.getByText(/already logged/i)).toBeInTheDocument();
  });

  it("holds the global conversation, sent to the global relay", () => {
    renderBoth();
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(screen.getByText(/does not suggest what to trade next/i)).toBeInTheDocument();
  });

  it("forgets the conversation when closed — the server keeps no copy either", () => {
    renderBoth();
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "half-typed" } });
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));
    expect(screen.getByRole("textbox")).toHaveValue("");
  });

  it("does not leak open state into a fresh mount after unmounting", () => {
    // Open state belongs to a mounted drawer, not a module-level flag that
    // outlives the component. Without the listener-count reset, this test
    // would start with the dialog already open because a prior test left the
    // module-level `isOpen` flag set to true.
    const first = renderBoth();
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    first.unmount();

    renderBoth();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
