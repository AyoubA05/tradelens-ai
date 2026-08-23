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
