import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DataSection } from "@/components/app/settings/data-section";

const fetchMock = vi.fn();
const data = {
  trade_count: 12,
  sample_count: 20,
  csv_columns: ["trade_date"],
  max_import_rows: 5000,
};
const emptyCost = { month: "2026-09", total_usd: 0, rows: [] };

/**
 * A File whose `text()` resolves with its content.
 *
 * jsdom 26 does not implement `File.prototype.text` (browsers do). Rather than
 * polyfill the prototype — jsdom's own FileReader resolves on a later tick,
 * outside the test's `act` — each file gets an own `text()` returning exactly
 * what it was built from. `size` stays the real byte length, so the 1 MB
 * refusal is still tested against a genuine File.
 */
function csvFile(content: string, name = "t.csv"): File {
  const file = new File([content], name, { type: "text/csv" });
  Object.defineProperty(file, "text", { value: () => Promise.resolve(content) });
  return file;
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => vi.unstubAllGlobals());

async function choose(file: File) {
  await act(async () => {
    fireEvent.change(screen.getByLabelText(/import trades from csv/i), { target: { files: [file] } });
  });
}

describe("export (review should-fix: no bare JSON page on failure)", () => {
  it("fetches the same-origin relay and saves the file", async () => {
    const createObjectURL = vi.fn(() => "blob:trades");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    fetchMock.mockResolvedValue({ ok: true, status: 200, blob: async () => new Blob(["a,b\n"]) });
    render(<DataSection data={data} cost={emptyCost} />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Export 12 trades as CSV" }));
    });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/settings/export");
    expect(click).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:trades");
    expect(screen.queryByRole("status")).toBeNull();
    click.mockRestore();
  });

  it.each([401, 403, 502])("shows a fixed sentence instead of navigating on %i", async (status) => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    fetchMock.mockResolvedValue({ ok: false, status, json: async () => ({ ok: false }) });
    render(<DataSection data={data} cost={emptyCost} />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Export 12 trades as CSV" }));
    });
    expect(screen.getByRole("status")).toHaveTextContent("The export did not download. Try again.");
    expect(click).not.toHaveBeenCalled();
    click.mockRestore();
  });

  it("offers no navigable export link", () => {
    render(<DataSection data={data} cost={emptyCost} />);
    expect(screen.queryByRole("link", { name: /export/i })).toBeNull();
  });
});

describe("import (S4)", () => {
  it("never sends a file over the size limit", async () => {
    render(<DataSection data={data} cost={emptyCost} />);
    await choose(csvFile("x".repeat(900_001)));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent(/larger than 1 MB/);
  });

  it("refuses a file whose escaped request would exceed 1 MB, without sending it", async () => {
    // 600,000 quotes: under the file limit, but JSON escaping doubles them.
    render(<DataSection data={data} cost={emptyCost} />);
    await choose(csvFile('"'.repeat(600_000)));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent(/larger than 1 MB/);
  });

  it("sends a file exactly at the size limit", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ inserted: 0, skipped: 0, errors: [] }) });
    render(<DataSection data={data} cost={emptyCost} />);
    await choose(csvFile("x".repeat(900_000)));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("sends the file text and reports counts in the Streamlit wording", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ inserted: 3, skipped: 1, errors: [] }),
    });
    render(<DataSection data={data} cost={emptyCost} />);
    await choose(csvFile("trade_date,asset\n"));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/settings/import");
    expect(fetchMock.mock.calls[0][1].method).toBe("POST");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ csv: "trade_date,asset\n" });
    expect(screen.getByRole("status")).toHaveTextContent("Imported 3 trades, skipped 1 duplicates.");
    expect(screen.getByRole("button", { name: "Export 15 trades as CSV" })).toBeInTheDocument();
  });

  it("says a valid empty file had no rows", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ inserted: 0, skipped: 0, errors: [] }) });
    render(<DataSection data={data} cost={emptyCost} />);
    await choose(csvFile("trade_date,asset\n"));
    expect(screen.getByRole("status")).toHaveTextContent("That CSV was valid but had no rows.");
  });

  it("lists the server's fixed row errors", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ inserted: 0, skipped: 0, errors: ["Row 2 could not be imported."] }),
    });
    render(<DataSection data={data} cost={emptyCost} />);
    await choose(csvFile("x"));
    expect(screen.getByText("Row 2 could not be imported.")).toBeInTheDocument();
  });

  it("names the row limit when the server refuses too many rows", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ ok: false, detail: [{ field: "csv", problem: "too_many_rows" }] }),
    });
    render(<DataSection data={data} cost={emptyCost} />);
    await choose(csvFile("x"));
    expect(screen.getByRole("status")).toHaveTextContent("That file has more than 5000 trades.");
  });

  it("says the file is too large when the relay refuses it", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 413, json: async () => ({ ok: false }) });
    render(<DataSection data={data} cost={emptyCost} />);
    await choose(csvFile("x"));
    expect(screen.getByRole("status")).toHaveTextContent(/larger than 1 MB/);
  });

  it("falls back to the generic sentence for anything else", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 502, json: async () => ({ ok: false }) });
    render(<DataSection data={data} cost={emptyCost} />);
    await choose(csvFile("x"));
    expect(screen.getByRole("status")).toHaveTextContent("That did not work. Try again.");
  });
});

describe("sample trades", () => {
  it("loads samples and updates the counts", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ count: 20, sample_count: 20 }) });
    render(<DataSection data={{ ...data, sample_count: 0, trade_count: 5 }} cost={emptyCost} />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Load sample trades" }));
    });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/settings/sample-trades");
    expect(fetchMock.mock.calls[0][1].method).toBe("POST");
    expect(screen.getByRole("status")).toHaveTextContent("Loaded 20 sample trades.");
    expect(screen.getByRole("button", { name: "Export 25 trades as CSV" })).toBeInTheDocument();
  });

  it("clears samples with DELETE", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ count: 20, sample_count: 0 }) });
    render(<DataSection data={data} cost={emptyCost} />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Clear sample trades" }));
    });
    expect(fetchMock.mock.calls[0][1].method).toBe("DELETE");
    expect(screen.getByRole("status")).toHaveTextContent("Removed 20 sample trades.");
    expect(screen.getByRole("button", { name: "Clear sample trades" })).toBeDisabled();
  });

  it("disables clearing when there are no sample trades", () => {
    render(<DataSection data={{ ...data, sample_count: 0 }} cost={emptyCost} />);
    expect(screen.getByRole("button", { name: "Clear sample trades" })).toBeDisabled();
  });
});

describe("cost", () => {
  it("shows this month's cost with four decimals and the total", () => {
    render(
      <DataSection
        data={data}
        cost={{ month: "2026-09", total_usd: 0.0123, rows: [{ feature: "AI Partner", cost_usd: 0.0123, calls: 2 }] }}
      />,
    );
    expect(screen.getByRole("cell", { name: "$0.0123" })).toBeInTheDocument();
    expect(screen.getByText("AI spend this month: $0.0123.")).toBeInTheDocument();
  });

  it("says when there is no spend", () => {
    render(<DataSection data={data} cost={emptyCost} />);
    expect(screen.getByText("No AI spend recorded this month.")).toBeInTheDocument();
  });
});
