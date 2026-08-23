import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DeleteTradeDialog } from "@/components/app/trade-detail/delete-trade-dialog";

describe("DeleteTradeDialog", () => {
  it("stays closed until opened", () => {
    render(
      <DeleteTradeDialog open={false} onClose={vi.fn()} onDeleted={vi.fn()} deleteTrade={vi.fn()} />,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("is a modal that states plainly what happens, and requires an explicit confirm", () => {
    render(
      <DeleteTradeDialog open onClose={vi.fn()} onDeleted={vi.fn()} deleteTrade={vi.fn()} />,
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveTextContent(/removes the trade and its screenshots/i);
    expect(dialog).toHaveTextContent(/cannot be undone/i);
    expect(screen.getByRole("button", { name: /delete trade/i })).toBeInTheDocument();
  });

  it("closes on Escape", () => {
    const onClose = vi.fn();
    render(
      <DeleteTradeDialog open onClose={onClose} onDeleted={vi.fn()} deleteTrade={vi.fn()} />,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("closes from Cancel without deleting anything", () => {
    const onClose = vi.fn();
    const deleteTrade = vi.fn();
    render(
      <DeleteTradeDialog open onClose={onClose} onDeleted={vi.fn()} deleteTrade={deleteTrade} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onClose).toHaveBeenCalled();
    expect(deleteTrade).not.toHaveBeenCalled();
  });

  it("puts initial focus on Cancel, not on the destructive confirm", () => {
    // Deliberate: a destructive action should not be one accidental Enter
    // key away from firing. The behaviour was designed in from the start but
    // nothing asserted it, so a refactor of the focus trap could have moved
    // it silently.
    render(
      <DeleteTradeDialog open onClose={vi.fn()} onDeleted={vi.fn()} deleteTrade={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: /cancel/i })).toHaveFocus();
    expect(screen.getByRole("button", { name: /^delete trade$/i })).not.toHaveFocus();
  });

  it("calls onDeleted on a 204", async () => {
    const onDeleted = vi.fn();
    const deleteTrade = vi.fn().mockResolvedValue({ status: 204 });
    render(
      <DeleteTradeDialog open onClose={vi.fn()} onDeleted={onDeleted} deleteTrade={deleteTrade} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /^delete trade$/i }));
    await waitFor(() => expect(onDeleted).toHaveBeenCalled());
  });

  describe("503 — screenshot cleanup failed", () => {
    it("says plainly that nothing was deleted and it can be retried", async () => {
      const deleteTrade = vi.fn().mockResolvedValue({ status: 503 });
      const onDeleted = vi.fn();
      render(
        <DeleteTradeDialog open onClose={vi.fn()} onDeleted={onDeleted} deleteTrade={deleteTrade} />,
      );
      fireEvent.click(screen.getByRole("button", { name: /^delete trade$/i }));

      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent(/nothing was deleted/i);
      expect(alert).toHaveTextContent(/try again/i);
      expect(onDeleted).not.toHaveBeenCalled();
    });

    it("never says the trade was removed", async () => {
      const deleteTrade = vi.fn().mockResolvedValue({ status: 503 });
      render(<DeleteTradeDialog open onClose={vi.fn()} onDeleted={vi.fn()} deleteTrade={deleteTrade} />);
      fireEvent.click(screen.getByRole("button", { name: /^delete trade$/i }));

      const alert = await screen.findByRole("alert");
      expect(alert.textContent ?? "").not.toMatch(/trade (was |is )?(removed|deleted)\b/i);
    });

    it("stays open so the trader can retry, and a retry can still succeed", async () => {
      const deleteTrade = vi.fn().mockResolvedValueOnce({ status: 503 }).mockResolvedValueOnce({ status: 204 });
      const onDeleted = vi.fn();
      render(
        <DeleteTradeDialog open onClose={vi.fn()} onDeleted={onDeleted} deleteTrade={deleteTrade} />,
      );
      fireEvent.click(screen.getByRole("button", { name: /^delete trade$/i }));
      await screen.findByRole("alert");
      expect(screen.getByRole("dialog")).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: /^delete trade$/i }));
      await waitFor(() => expect(onDeleted).toHaveBeenCalled());
      expect(deleteTrade).toHaveBeenCalledTimes(2);
    });
  });

  describe("503 — a cleanup failure a retry can never clear", () => {
    // The backend reports `unresolvable` separately from `remaining`
    // precisely so nobody tells a trader to keep retrying something that
    // cannot succeed. Same truth as the retryable branch — nothing was
    // deleted — but the advice has to be different, or the split was pointless.
    const unresolvable = () => vi.fn().mockResolvedValue({ status: 503, unresolvable: true });

    it("says nothing was deleted and that retrying will not help", async () => {
      const onDeleted = vi.fn();
      render(
        <DeleteTradeDialog
          open
          onClose={vi.fn()}
          onDeleted={onDeleted}
          deleteTrade={unresolvable()}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: /^delete trade$/i }));

      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent(/nothing was deleted/i);
      expect(alert).toHaveTextContent(/trying again will not/i);
      expect(alert).toHaveTextContent(/support/i);
      expect(onDeleted).not.toHaveBeenCalled();
    });

    it("does not offer the retry the retryable branch offers", async () => {
      render(
        <DeleteTradeDialog
          open
          onClose={vi.fn()}
          onDeleted={vi.fn()}
          deleteTrade={unresolvable()}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: /^delete trade$/i }));

      const alert = await screen.findByRole("alert");
      expect(alert.textContent ?? "").not.toMatch(/you can try again/i);
      // The confirm button is disabled too: leaving it live would contradict
      // the sentence directly above it.
      expect(screen.getByRole("button", { name: /^delete trade$/i })).toBeDisabled();
    });

    it("never implies anything was deleted", async () => {
      render(
        <DeleteTradeDialog
          open
          onClose={vi.fn()}
          onDeleted={vi.fn()}
          deleteTrade={unresolvable()}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: /^delete trade$/i }));

      const alert = await screen.findByRole("alert");
      const text = alert.textContent ?? "";
      expect(text).not.toMatch(/trade (was |is )?(removed|deleted)\b/i);
      expect(text).not.toMatch(/partly|partially/i);
    });

    it("reads differently from the retryable 503, not as the same message", async () => {
      const { unmount } = render(
        <DeleteTradeDialog
          open
          onClose={vi.fn()}
          onDeleted={vi.fn()}
          deleteTrade={unresolvable()}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: /^delete trade$/i }));
      const unresolvableText = (await screen.findByRole("alert")).textContent ?? "";
      unmount();

      render(
        <DeleteTradeDialog
          open
          onClose={vi.fn()}
          onDeleted={vi.fn()}
          deleteTrade={vi.fn().mockResolvedValue({ status: 503, unresolvable: false })}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: /^delete trade$/i }));
      const retryableText = (await screen.findByRole("alert")).textContent ?? "";

      expect(retryableText).toMatch(/you can try again/i);
      expect(unresolvableText).not.toBe(retryableText);
      // Both still make the one guarantee that must never vary.
      expect(retryableText).toMatch(/nothing was deleted/i);
      expect(unresolvableText).toMatch(/nothing was deleted/i);
    });
  });

  describe("other failures", () => {
    it("reports a generic failure the same way — nothing deleted, retryable", async () => {
      const deleteTrade = vi.fn().mockResolvedValue({ status: 500 });
      render(<DeleteTradeDialog open onClose={vi.fn()} onDeleted={vi.fn()} deleteTrade={deleteTrade} />);
      fireEvent.click(screen.getByRole("button", { name: /^delete trade$/i }));

      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent(/nothing was deleted/i);
    });

    it("reports a network failure the same way", async () => {
      const deleteTrade = vi.fn().mockRejectedValue(new Error("network down"));
      render(<DeleteTradeDialog open onClose={vi.fn()} onDeleted={vi.fn()} deleteTrade={deleteTrade} />);
      fireEvent.click(screen.getByRole("button", { name: /^delete trade$/i }));

      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent(/nothing was deleted/i);
    });
  });
});
