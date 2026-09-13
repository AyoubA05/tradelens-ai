"use client";

import { useRef, useState } from "react";

import { SettingStatus } from "@/components/app/settings/setting-status";

/**
 * Data — your records in and out, sample trades, and what AI has cost.
 *
 * Export is a plain same-origin link: the relay answers with a CSV attachment
 * whose formula cells the API has already neutralised (decision S5). Import is
 * synchronous and bounded (decision S4): a file over the size limit is refused
 * here and never sent, and the server refuses more than `maxImportRows`.
 */

const MAX_IMPORT_FILE_BYTES = 900_000;
const GENERIC_FAILURE = "That did not work. Try again.";

type Status = { tone: "ok" | "fail"; text: string } | null;

export function DataSection({
  data,
  cost,
}: {
  data: { trade_count: number; sample_count: number; csv_columns: string[]; max_import_rows: number };
  cost: { month: string; total_usd: number; rows: { feature: string; cost_usd: number; calls: number }[] };
}) {
  const [tradeCount, setTradeCount] = useState(data.trade_count);
  const [sampleCount, setSampleCount] = useState(data.sample_count);
  const [importStatus, setImportStatus] = useState<Status>(null);
  const [importErrors, setImportErrors] = useState<string[]>([]);
  const [sampleStatus, setSampleStatus] = useState<Status>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);

  const tooLarge = "That file is larger than 1 MB. Split it and import each part.";

  async function importFile(file: File | undefined) {
    if (!file || inFlight.current) return;
    setImportStatus(null);
    setImportErrors([]);
    if (file.size > MAX_IMPORT_FILE_BYTES) {
      setImportStatus({ tone: "fail", text: tooLarge });
      return;
    }
    inFlight.current = true;
    setBusy(true);
    try {
      const csv = await file.text();
      const response = await fetch("/api/settings/import", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ csv }),
      });
      const body = (await response.json().catch(() => ({}))) as {
        inserted?: number;
        skipped?: number;
        errors?: string[];
        detail?: unknown;
      };
      if (response.ok) {
        const inserted = body.inserted ?? 0;
        const skipped = body.skipped ?? 0;
        setTradeCount((n) => n + inserted);
        setImportErrors(Array.isArray(body.errors) ? body.errors : []);
        if (inserted || skipped) {
          setImportStatus({ tone: "ok", text: `Imported ${inserted} trades, skipped ${skipped} duplicates.` });
        } else if (!body.errors?.length) {
          setImportStatus({ tone: "ok", text: "That CSV was valid but had no rows." });
        }
        return;
      }
      const tooManyRows =
        response.status === 422 &&
        Array.isArray(body.detail) &&
        body.detail.some((d) => (d as { problem?: unknown })?.problem === "too_many_rows");
      setImportStatus({
        tone: "fail",
        text: tooManyRows
          ? `That file has more than ${data.max_import_rows} trades. Split it and import each part.`
          : response.status === 413
            ? tooLarge
            : GENERIC_FAILURE,
      });
    } catch {
      setImportStatus({ tone: "fail", text: GENERIC_FAILURE });
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  async function samples(method: "POST" | "DELETE") {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setSampleStatus(null);
    try {
      const response = await fetch("/api/settings/sample-trades", {
        method,
        headers: { "content-type": "application/json" },
      });
      if (!response.ok) {
        setSampleStatus({ tone: "fail", text: GENERIC_FAILURE });
        return;
      }
      const body = (await response.json()) as { count: number; sample_count: number };
      setTradeCount((n) => n - sampleCount + body.sample_count);
      setSampleCount(body.sample_count);
      setSampleStatus({
        tone: "ok",
        text: method === "POST" ? `Loaded ${body.count} sample trades.` : `Removed ${body.count} sample trades.`,
      });
    } catch {
      setSampleStatus({ tone: "fail", text: GENERIC_FAILURE });
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  const buttonClass =
    "min-h-[44px] rounded-lg border border-line-strong px-3 py-1.5 text-sm text-text transition-colors duration-150 ease-tl hover:bg-surface-2 disabled:opacity-60";

  return (
    <section aria-labelledby="settings-data" className="mt-10">
      <h2 id="settings-data" className="font-display text-xl font-bold">
        Data
      </h2>
      <p className="mt-1 text-sm text-muted">Your records, in and out — and what AI has cost.</p>

      <div className="mt-4 flex flex-wrap items-start gap-6">
        <a href="/api/settings/export" download className={buttonClass}>
          {`Export ${tradeCount} trades as CSV`}
        </a>
        <div>
          <label htmlFor="settings-import" className="block text-sm text-text">
            Import trades from CSV
          </label>
          <input
            id="settings-import"
            type="file"
            accept=".csv,text/csv"
            disabled={busy}
            onChange={(event) => void importFile(event.target.files?.[0])}
            className="mt-1 text-sm text-text"
          />
          {importStatus ? <SettingStatus tone={importStatus.tone} text={importStatus.text} /> : null}
          {importErrors.length ? (
            <ul className="mt-2 list-disc pl-5 text-xs text-negative">
              {importErrors.map((err, i) => (
                <li key={i}>{err}</li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
      <p className="mt-2 text-xs text-muted">Export first to see the column format an import expects.</p>

      <div className="mt-6 flex flex-wrap gap-3">
        <button type="button" onClick={() => void samples("POST")} disabled={busy} className={buttonClass}>
          Load sample trades
        </button>
        <button
          type="button"
          onClick={() => void samples("DELETE")}
          disabled={busy || sampleCount === 0}
          className={buttonClass}
        >
          Clear sample trades
        </button>
      </div>
      {sampleStatus ? <SettingStatus tone={sampleStatus.tone} text={sampleStatus.text} /> : null}
      <p className="mt-2 text-xs text-muted">
        {`${sampleCount} sample trades are loaded. They are flagged as samples and clearing them never touches a trade you logged.`}
      </p>

      <div className="mt-8">
        {cost.rows.length === 0 ? (
          <p className="text-sm text-muted">No AI spend recorded this month.</p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">AI cost by feature this month</caption>
                <thead>
                  <tr className="text-muted">
                    <th scope="col" className="py-2 pr-4 font-normal">Feature</th>
                    <th scope="col" className="py-2 pr-4 font-normal">Cost</th>
                    <th scope="col" className="py-2 font-normal">Calls</th>
                  </tr>
                </thead>
                <tbody>
                  {cost.rows.map((row) => (
                    <tr key={row.feature} className="border-t border-line">
                      <td className="py-2 pr-4 text-text">{row.feature}</td>
                      <td className="py-2 pr-4 font-mono text-text">{`$${row.cost_usd.toFixed(4)}`}</td>
                      <td className="py-2 font-mono text-text">{row.calls}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-sm text-text">{`AI spend this month: $${cost.total_usd.toFixed(4)}.`}</p>
          </>
        )}
      </div>
    </section>
  );
}
