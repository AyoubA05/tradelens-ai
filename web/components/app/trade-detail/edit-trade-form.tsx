"use client";

import { useState } from "react";
import type { FormEvent } from "react";

import type { TradeDetail, TradeUpdate } from "@/lib/app/trades";

const RESULT_OPTIONS = ["Win", "Loss", "Breakeven"] as const;

const inputClass =
  "w-full rounded-md border border-line bg-chart px-2 py-1.5 text-sm text-text outline-none focus:border-accent";
const labelClass = "flex flex-col gap-1 text-xs text-muted";

function emptyToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

function numberOrNull(value: string): number | null | "invalid" {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : "invalid";
}

function flagOrNull(value: string): number | null {
  if (value === "yes") return 1;
  if (value === "no") return 0;
  return null;
}

function flagToSelectValue(v: number | null | undefined): string {
  if (v === 1) return "yes";
  if (v === 0) return "no";
  return "";
}

type Draft = {
  trade_date: string;
  asset: string;
  direction: string;
  session: string;
  killzone: string;
  setup_type: string;
  timeframe: string;
  htf_bias: string;
  result: string;
  pnl: string;
  risk_amount: string;
  rr_realized: string;
  followed_rules: string;
  mistake_tags: string;
  notes: string;
};

function draftFrom(trade: TradeDetail): Draft {
  return {
    trade_date: trade.trade_date ?? "",
    asset: trade.asset ?? "",
    direction: trade.direction ?? "",
    session: trade.session ?? "",
    killzone: trade.killzone ?? "",
    setup_type: trade.setup_type ?? "",
    timeframe: trade.timeframe ?? "",
    htf_bias: trade.htf_bias ?? "",
    result: trade.result ?? "",
    pnl: trade.pnl === null || trade.pnl === undefined ? "" : String(trade.pnl),
    risk_amount:
      trade.risk_amount === null || trade.risk_amount === undefined ? "" : String(trade.risk_amount),
    rr_realized:
      trade.rr_realized === null || trade.rr_realized === undefined ? "" : String(trade.rr_realized),
    followed_rules: flagToSelectValue(trade.followed_rules),
    mistake_tags: trade.mistake_tags ?? "",
    notes: trade.notes ?? "",
  };
}

/**
 * The Trade Detail inline edit form.
 *
 * `expected_updated_at` — the `updated_at` this form was opened with — rides
 * on every PATCH (design decision #5). A 409 means the trade changed
 * elsewhere since then: this never auto-retries and never silently keeps
 * either version. It shows the conflict plainly and waits for the trader to
 * choose "Reload latest," which discards this draft only because they asked
 * to, not because the request failed.
 */
export function EditTradeForm({
  trade,
  onCancel,
  onSaved,
  onConflictReload,
}: {
  trade: TradeDetail;
  onCancel: () => void;
  onSaved: () => void;
  onConflictReload: () => void;
}) {
  const [draft, setDraft] = useState<Draft>(() => draftFrom(trade));
  const [saving, setSaving] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);

  function set<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((d) => ({ ...d, [key]: value }));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setValidationError(null);
    setSaveError(null);

    const pnl = numberOrNull(draft.pnl);
    const risk = numberOrNull(draft.risk_amount);
    const rr = numberOrNull(draft.rr_realized);
    if (pnl === "invalid" || risk === "invalid" || rr === "invalid") {
      setValidationError("P&L, risk amount and R realized must be numbers, or left blank.");
      return;
    }

    const body: TradeUpdate = {
      expected_updated_at: trade.updated_at ?? "",
      trade_date: emptyToNull(draft.trade_date),
      asset: emptyToNull(draft.asset),
      direction: emptyToNull(draft.direction),
      session: emptyToNull(draft.session),
      killzone: emptyToNull(draft.killzone),
      setup_type: emptyToNull(draft.setup_type),
      timeframe: emptyToNull(draft.timeframe),
      htf_bias: emptyToNull(draft.htf_bias),
      result: (emptyToNull(draft.result) as TradeUpdate["result"]) ?? null,
      pnl,
      risk_amount: risk,
      rr_realized: rr,
      followed_rules: flagOrNull(draft.followed_rules),
      mistake_tags: emptyToNull(draft.mistake_tags),
      notes: emptyToNull(draft.notes),
    };

    setSaving(true);
    try {
      const response = await fetch(`/api/trades/${trade.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (response.status === 409) {
        setConflict(true);
        return;
      }
      if (!response.ok) {
        setSaveError("This edit did not save. Nothing was changed. You can try again.");
        return;
      }
      onSaved();
    } catch {
      setSaveError("We could not reach the server. Nothing was changed. Check your connection and try again.");
    } finally {
      setSaving(false);
    }
  }

  if (conflict) {
    return (
      <div role="alert" className="mt-6 rounded-xl border border-negative/30 bg-negative/5 px-6 py-6">
        <h2 className="font-display text-base font-semibold text-text">
          This trade changed elsewhere
        </h2>
        <p className="mt-2 max-w-md text-sm text-muted">
          Someone — another tab, another device — saved a change to this trade after you started
          editing. Your edits here have not been saved, and nothing has been overwritten. Reload
          to see the current version before editing again.
        </p>
        <div className="mt-4 flex gap-2">
          <button
            type="button"
            onClick={onConflictReload}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg transition-colors duration-150 ease-tl hover:bg-accent/90"
          >
            Reload latest version
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-line-strong px-4 py-2 text-sm text-text transition-colors duration-150 ease-tl hover:bg-surface-2"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="mt-6 rounded-xl border border-line bg-surface p-5">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <label className={labelClass}>
          Date
          <input
            type="date"
            value={draft.trade_date}
            onChange={(e) => set("trade_date", e.target.value)}
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Asset
          <input
            type="text"
            value={draft.asset}
            onChange={(e) => set("asset", e.target.value)}
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Direction
          <input
            type="text"
            value={draft.direction}
            onChange={(e) => set("direction", e.target.value)}
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Session
          <input
            type="text"
            value={draft.session}
            onChange={(e) => set("session", e.target.value)}
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Killzone
          <input
            type="text"
            value={draft.killzone}
            onChange={(e) => set("killzone", e.target.value)}
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Setup type
          <input
            type="text"
            value={draft.setup_type}
            onChange={(e) => set("setup_type", e.target.value)}
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Timeframe
          <input
            type="text"
            value={draft.timeframe}
            onChange={(e) => set("timeframe", e.target.value)}
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          HTF bias
          <input
            type="text"
            value={draft.htf_bias}
            onChange={(e) => set("htf_bias", e.target.value)}
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Result
          <select
            value={draft.result}
            onChange={(e) => set("result", e.target.value)}
            className={inputClass}
          >
            <option value="">Not recorded</option>
            {RESULT_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <label className={labelClass}>
          P&amp;L
          <input
            type="text"
            inputMode="decimal"
            value={draft.pnl}
            onChange={(e) => set("pnl", e.target.value)}
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Risk amount
          <input
            type="text"
            inputMode="decimal"
            value={draft.risk_amount}
            onChange={(e) => set("risk_amount", e.target.value)}
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          R realized
          <input
            type="text"
            inputMode="decimal"
            value={draft.rr_realized}
            onChange={(e) => set("rr_realized", e.target.value)}
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Followed rules
          <select
            value={draft.followed_rules}
            onChange={(e) => set("followed_rules", e.target.value)}
            className={inputClass}
          >
            <option value="">Not recorded</option>
            <option value="yes">Yes</option>
            <option value="no">No</option>
          </select>
        </label>
        <label className={labelClass}>
          Mistake tags
          <input
            type="text"
            value={draft.mistake_tags}
            onChange={(e) => set("mistake_tags", e.target.value)}
            className={inputClass}
          />
        </label>
      </div>

      <label className={`${labelClass} mt-4`}>
        Notes
        <textarea
          value={draft.notes}
          onChange={(e) => set("notes", e.target.value)}
          rows={4}
          className={inputClass}
        />
      </label>

      {validationError && (
        <p role="alert" className="mt-4 text-sm text-negative">
          {validationError}
        </p>
      )}
      {saveError && (
        <p role="alert" className="mt-4 text-sm text-negative">
          {saveError}
        </p>
      )}

      <div className="mt-5 flex gap-2">
        <button
          type="submit"
          disabled={saving}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg transition-colors duration-150 ease-tl hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {saving ? "Saving…" : "Save changes"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className="rounded-lg border border-line-strong px-4 py-2 text-sm text-text transition-colors duration-150 ease-tl hover:bg-surface-2"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
