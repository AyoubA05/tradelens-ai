import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DangerZone } from "@/components/app/settings/danger-zone";

const { refresh } = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

/**
 * The two destructive actions. What matters: a button is enabled only by the
 * exact typed phrase, the request carries the constant phrase and nothing else,
 * one click sends one request, and a blocked screenshot cleanup is reported as
 * "nothing was deleted" — never as a success.
 */

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  refresh.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => vi.unstubAllGlobals());

function openTrades() {
  fireEvent.click(screen.getByRole("button", { name: "Delete all trades" }));
}

function openAccount() {
  fireEvent.click(screen.getByRole("button", { name: "Delete my account" }));
}

describe("delete all trades", () => {
  it.each(["delete", "DELETE ", " DELETE", "DELET", ""])("stays disabled for %j", (typed) => {
    render(<DangerZone />);
    openTrades();
    fireEvent.change(screen.getByLabelText("Type DELETE to confirm"), { target: { value: typed } });
    expect(screen.getByRole("button", { name: "Delete all trades permanently" })).toBeDisabled();
  });

  it("sends exactly the constant confirmation and reports the count", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ deleted: 7 }) });
    render(<DangerZone />);
    openTrades();
    fireEvent.change(screen.getByLabelText("Type DELETE to confirm"), { target: { value: "DELETE" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Delete all trades permanently" }));
    });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/settings/delete-trades");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ confirm: "DELETE" });
    expect(screen.getByRole("status")).toHaveTextContent("Deleted 7 trades.");
  });

  it.each([
    [false, /Try again\.$/],
    [true, /trying again will not fix this/],
  ])("says nothing was deleted when cleanup is blocked (unresolvable=%s)", async (unresolvable, copy) => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ ok: false, detail: "screenshot_cleanup_failed", unresolvable }),
    });
    render(<DangerZone />);
    openTrades();
    fireEvent.change(screen.getByLabelText("Type DELETE to confirm"), { target: { value: "DELETE" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Delete all trades permanently" }));
    });
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("nothing was deleted");
    expect(status).toHaveTextContent(copy);
    expect(status.textContent).not.toMatch(/Deleted \d+ trades/);
  });

  it("sends one request for a double click", async () => {
    let release: (v: unknown) => void = () => {};
    fetchMock.mockImplementation(() => new Promise((r) => (release = r)));
    render(<DangerZone />);
    openTrades();
    fireEvent.change(screen.getByLabelText("Type DELETE to confirm"), { target: { value: "DELETE" } });
    const button = screen.getByRole("button", { name: "Delete all trades permanently" });
    await act(async () => {
      fireEvent.click(button);
      fireEvent.click(button);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await act(async () => release({ ok: true, status: 200, json: async () => ({ deleted: 0 }) }));
  });
});

describe("delete my account (S9)", () => {
  it("sends the constant phrase, never the typed text, and hands off to the landing page", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true, next: "/account-deleted" }),
    });
    const onAccountDeleted = vi.fn();
    render(<DangerZone onAccountDeleted={onAccountDeleted} />);
    openAccount();
    fireEvent.change(screen.getByLabelText("Type DELETE MY ACCOUNT to confirm"), {
      target: { value: "  DELETE MY ACCOUNT  " },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Delete my account permanently" }));
    });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/settings/delete-account");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ confirm: "DELETE MY ACCOUNT" });
    expect(onAccountDeleted).toHaveBeenCalledWith("/account-deleted");
  });

  it.each(["delete my account", "DELETE MY  ACCOUNT", "DELETE"])("stays disabled for %j", (typed) => {
    render(<DangerZone />);
    openAccount();
    fireEvent.change(screen.getByLabelText("Type DELETE MY ACCOUNT to confirm"), { target: { value: typed } });
    expect(screen.getByRole("button", { name: "Delete my account permanently" })).toBeDisabled();
  });

  it("stays on the page and says nothing was deleted when cleanup is blocked", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ ok: false, detail: "screenshot_cleanup_failed", unresolvable: false }),
    });
    const onAccountDeleted = vi.fn();
    render(<DangerZone onAccountDeleted={onAccountDeleted} />);
    openAccount();
    fireEvent.change(screen.getByLabelText("Type DELETE MY ACCOUNT to confirm"), {
      target: { value: "DELETE MY ACCOUNT" },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Delete my account permanently" }));
    });
    expect(onAccountDeleted).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("nothing was deleted");
  });

  it("never navigates to a location that is not a same-site path", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true, next: "https://evil.test/" }),
    });
    const onAccountDeleted = vi.fn();
    render(<DangerZone onAccountDeleted={onAccountDeleted} />);
    openAccount();
    fireEvent.change(screen.getByLabelText("Type DELETE MY ACCOUNT to confirm"), {
      target: { value: "DELETE MY ACCOUNT" },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Delete my account permanently" }));
    });
    expect(onAccountDeleted).not.toHaveBeenCalled();
  });

  it("says what is kept and what is erased", () => {
    render(<DangerZone />);
    openAccount();
    expect(screen.getByText(/Anonymous records of what AI features cost to run are kept/)).toBeInTheDocument();
    expect(screen.getByText(/every chart image you uploaded/)).toBeInTheDocument();
  });
});

describe("after delete all trades (review should-fix: stale counts)", () => {
  it("re-reads the page's server data after a successful deletion", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ deleted: 20 }) });
    render(<DangerZone />);
    openTrades();
    fireEvent.change(screen.getByLabelText("Type DELETE to confirm"), { target: { value: "DELETE" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Delete all trades permanently" }));
    });
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("does not refresh when the deletion was blocked — nothing changed", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ ok: false, detail: "screenshot_cleanup_failed", unresolvable: false }),
    });
    render(<DangerZone />);
    openTrades();
    fireEvent.change(screen.getByLabelText("Type DELETE to confirm"), { target: { value: "DELETE" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Delete all trades permanently" }));
    });
    expect(refresh).not.toHaveBeenCalled();
  });
});
