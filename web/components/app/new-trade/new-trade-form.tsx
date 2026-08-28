"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { useRouter } from "next/navigation";

import {
  ASSET_OPTIONS,
  BIAS_OPTIONS,
  CONFLUENCE_OPTIONS,
  EMOTION_OPTIONS,
  FOLLOWED_RULES_OPTIONS,
  MISTAKE_OPTIONS,
  OTHER_ASSET,
  RESULT_OPTIONS,
  SETUP_OPTIONS,
  TIMEFRAME_OPTIONS,
} from "@/lib/app/new-trade-fields";
import {
  buildTradeCreatePayload,
  emptyNewTradeFormValues,
  validateNewTrade,
  type NewTradeFormValues,
} from "@/lib/app/new-trade";

const inputClass =
  "w-full rounded-md border border-line bg-chart px-2 py-1.5 text-sm text-text outline-none focus:border-accent";
const labelClass = "flex flex-col gap-1 text-xs text-muted";
const sectionClass = "rounded-xl border border-line bg-surface p-5";
const sectionTitleClass = "font-display text-sm font-semibold text-text";

function todayIso(): string {
  // Local calendar date, not UTC — courtesy mirror of the server's
  // owner-timezone future-date check (design constraint / global rule 4);
  // the server's `today_for_owner` remains the actual gate.
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function toggleInList(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

/**
 * The New Trade form (Task C2).
 *
 * One dense form, grouped, everything visible at once — design decision #7
 * and global rule "One dense form, never a wizard." The Streamlit page it
 * replaces carries a `tl_wizard_bar`; this component does not. The grid
 * groups collapse to a single column below `sm:`, so on a ~375px screen the
 * groups stack vertically and stay on one page — they never become separate
 * screens.
 *
 * Client validation (`validateNewTrade`) is a courtesy mirror of the
 * server's rules, never the gate (global rule 4): the submit button stays
 * enabled through every client-side error, disabled only while a request is
 * in flight, and the server's own 422 is what actually blocks a bad write —
 * see the catch branch below. Completeness warnings render but never
 * disable submit (global rule 5).
 */
export function NewTradeForm() {
  const router = useRouter();
  const [values, setValues] = useState<NewTradeFormValues>(() => ({
    ...emptyNewTradeFormValues(),
    tradeDate: todayIso(),
  }));
  const [screenshotFile, setScreenshotFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [duplicateOf, setDuplicateOf] = useState<number | null>(null);

  function set<K extends keyof NewTradeFormValues>(key: K, value: NewTradeFormValues[K]) {
    setValues((v) => ({ ...v, [key]: value }));
  }

  const { errors, warnings } = validateNewTrade(values, OTHER_ASSET);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitError(null);
    setDuplicateOf(null);

    const payload = buildTradeCreatePayload(values, OTHER_ASSET);
    setSubmitting(true);
    try {
      const response = await fetch("/api/trades/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        // The server is the real gate (global rule 4): a 422 here is the
        // allowlist, the future-date check, or canonical_outcome catching
        // something the client-side mirror above missed or a race changed.
        let detail = "This trade did not save. Nothing was recorded. Check the form and try again.";
        try {
          const body = (await response.json()) as { detail?: unknown };
          if (typeof body?.detail === "string") detail = body.detail;
        } catch {
          // no body to read — keep the generic message
        }
        setSubmitError(detail);
        return;
      }
      const created = (await response.json()) as { id: number; duplicate_of: number | null };
      if (created.duplicate_of !== null) {
        // Design decision #5: this is not an error. Nothing new was
        // created; the existing trade is shown rather than a second row.
        setDuplicateOf(created.duplicate_of);
        return;
      }
      // Screenshot upload against the new trade id is a separate step
      // (design decision #1 — the trade's id authorises the upload); the
      // relay for that is not part of this task, so a picked file is
      // reported rather than silently dropped.
      router.push(`/app/trades/${created.id}`);
    } catch {
      setSubmitError("We could not reach the server. Nothing was saved. Check your connection and try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (duplicateOf !== null) {
    return (
      <div role="alert" className={sectionClass}>
        <h2 className={sectionTitleClass}>This trade is already logged</h2>
        <p className="mt-2 max-w-md text-sm text-muted">
          A trade matching this date, asset, direction, entry time and price levels already
          exists. Nothing new was created — this is a post-trade journal, not a place for
          duplicates.
        </p>
        <div className="mt-4 flex gap-2">
          <button
            type="button"
            onClick={() => router.push(`/app/trades/${duplicateOf}`)}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg transition-colors duration-150 ease-tl hover:bg-accent/90"
          >
            View existing trade
          </button>
          <button
            type="button"
            onClick={() => setDuplicateOf(null)}
            className="rounded-lg border border-line-strong px-4 py-2 text-sm text-text transition-colors duration-150 ease-tl hover:bg-surface-2"
          >
            Edit and try again
          </button>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5" noValidate>
      {/* Screenshot */}
      <section className={sectionClass}>
        <h2 className={sectionTitleClass}>Chart</h2>
        <p className="mt-1 text-xs text-muted">
          Optional. Post-trade review only — nothing here is a live signal.
        </p>
        <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className={labelClass}>
            Upload screenshot
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              onChange={(e) => setScreenshotFile(e.target.files?.[0] ?? null)}
              className={inputClass}
            />
          </label>
          <p className="self-end text-xs text-muted">
            {screenshotFile
              ? `${screenshotFile.name} — attach it from the trade's page after saving.`
              : "No screenshot attached."}
          </p>
        </div>
      </section>

      {/* When and what */}
      <section className={sectionClass}>
        <h2 className={sectionTitleClass}>When and what</h2>
        <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <label className={labelClass}>
            Trade date
            <input
              type="date"
              value={values.tradeDate}
              max={todayIso()}
              onChange={(e) => set("tradeDate", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            Entry time
            <input
              type="text"
              placeholder="e.g., 09:30 or 9:30 AM"
              value={values.entryTime}
              onChange={(e) => set("entryTime", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            Timeframe
            <select
              value={values.timeframe}
              onChange={(e) => set("timeframe", e.target.value)}
              className={inputClass}
            >
              {TIMEFRAME_OPTIONS.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </label>
          <label className={labelClass}>
            Asset
            <select
              value={values.asset}
              onChange={(e) => set("asset", e.target.value)}
              className={inputClass}
            >
              <option value="" disabled>
                Choose an asset
              </option>
              {ASSET_OPTIONS.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </label>
          {values.asset === OTHER_ASSET && (
            <label className={labelClass}>
              Custom asset
              <input
                type="text"
                placeholder="e.g., MNQ"
                value={values.assetCustom}
                onChange={(e) => set("assetCustom", e.target.value)}
                className={inputClass}
              />
            </label>
          )}
          <label className={labelClass}>
            HTF bias
            <select
              value={values.htfBias}
              onChange={(e) => set("htfBias", e.target.value)}
              className={inputClass}
            >
              {BIAS_OPTIONS.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </label>
          <label className={labelClass}>
            LTF bias
            <select
              value={values.ltfBias}
              onChange={(e) => set("ltfBias", e.target.value)}
              className={inputClass}
            >
              {BIAS_OPTIONS.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>

      {/* Setup and evidence */}
      <section className={sectionClass}>
        <h2 className={sectionTitleClass}>Setup and evidence</h2>
        <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className={labelClass}>
            Setup model
            <select
              value={values.setupType}
              onChange={(e) => set("setupType", e.target.value)}
              className={inputClass}
            >
              {SETUP_OPTIONS.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </label>
          <label className={labelClass}>
            What confirmed the trade?
            <input
              type="text"
              placeholder="e.g., 1m IFVG + 5m BOS"
              value={values.confirmationModel}
              onChange={(e) => set("confirmationModel", e.target.value)}
              className={inputClass}
            />
          </label>
        </div>
        <fieldset className="mt-4">
          <legend className="text-xs text-muted">Evidence</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {CONFLUENCE_OPTIONS.map((o) => {
              const checked = values.confluences.includes(o);
              return (
                <label
                  key={o}
                  className={`cursor-pointer rounded-full border px-3 py-1 text-xs ${
                    checked
                      ? "border-accent bg-accent/10 text-accent"
                      : "border-line text-muted"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => set("confluences", toggleInList(values.confluences, o))}
                    className="sr-only"
                  />
                  {o}
                </label>
              );
            })}
          </div>
        </fieldset>
        <fieldset className="mt-4">
          <legend className="text-xs text-muted">Followed your rules?</legend>
          <div className="mt-2 flex gap-4">
            {FOLLOWED_RULES_OPTIONS.map((o) => (
              <label key={o} className="flex items-center gap-1.5 text-sm text-text">
                <input
                  type="radio"
                  name="followed_rules"
                  checked={values.followedRules === o}
                  onChange={() => set("followedRules", o)}
                />
                {o}
              </label>
            ))}
          </div>
          {(values.followedRules === "No" || values.followedRules === "Partial") && (
            <label className={`${labelClass} mt-2`}>
              Which rule, or what went wrong?
              <input
                type="text"
                value={values.ruleBroken}
                onChange={(e) => set("ruleBroken", e.target.value)}
                className={inputClass}
              />
            </label>
          )}
        </fieldset>
      </section>

      {/* Risk and outcome */}
      <section className={sectionClass}>
        <h2 className={sectionTitleClass}>Risk and outcome</h2>
        <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <label className={labelClass}>
            Result
            <select
              value={values.result}
              onChange={(e) => set("result", e.target.value)}
              className={inputClass}
            >
              {RESULT_OPTIONS.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </label>
          <label className={labelClass}>
            P&amp;L ($)
            <input
              type="text"
              inputMode="decimal"
              placeholder="e.g., 250.00"
              value={values.pnl}
              onChange={(e) => set("pnl", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            Risk ($)
            <input
              type="text"
              inputMode="decimal"
              placeholder="e.g., 125.00"
              value={values.riskAmount}
              onChange={(e) => set("riskAmount", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            Position size
            <input
              type="text"
              inputMode="numeric"
              placeholder="e.g., 3"
              value={values.positionSize}
              onChange={(e) => set("positionSize", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            R multiple
            <input
              type="text"
              inputMode="decimal"
              placeholder="e.g., 2.0"
              value={values.rMultiple}
              onChange={(e) => set("rMultiple", e.target.value)}
              className={inputClass}
            />
          </label>
        </div>
        <details className="mt-4">
          <summary className="cursor-pointer text-xs text-muted">
            Exact price levels (markup)
          </summary>
          <p className="mt-2 text-xs text-muted">
            Optional. Decimals are kept exactly as typed (e.g. 3.3765).
          </p>
          <div className="mt-2 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <label className={labelClass}>
              Entry price
              <input
                type="text"
                inputMode="decimal"
                placeholder="e.g., 19850.25"
                value={values.entryPrice}
                onChange={(e) => set("entryPrice", e.target.value)}
                className={inputClass}
              />
            </label>
            <label className={labelClass}>
              Stop price
              <input
                type="text"
                inputMode="decimal"
                placeholder="e.g., 3.3765"
                value={values.stopPrice}
                onChange={(e) => set("stopPrice", e.target.value)}
                className={inputClass}
              />
            </label>
            <label className={labelClass}>
              Take profit
              <input
                type="text"
                inputMode="decimal"
                placeholder="e.g., 19920.00"
                value={values.tpPrice}
                onChange={(e) => set("tpPrice", e.target.value)}
                className={inputClass}
              />
            </label>
            <label className={labelClass}>
              Exit price
              <input
                type="text"
                inputMode="decimal"
                placeholder="e.g., 19905.00"
                value={values.exitPrice}
                onChange={(e) => set("exitPrice", e.target.value)}
                className={inputClass}
              />
            </label>
          </div>
        </details>
      </section>

      {/* Reflection */}
      <section className={sectionClass}>
        <h2 className={sectionTitleClass}>Reflection</h2>
        <p className="mt-1 text-xs text-muted">Every field here is optional.</p>
        <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className={labelClass}>
            What happened during this trade?
            <textarea
              rows={3}
              value={values.processNotes}
              onChange={(e) => set("processNotes", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            How were you feeling?
            <textarea
              rows={3}
              value={values.mindset}
              onChange={(e) => set("mindset", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            What did you do well?
            <textarea
              rows={2}
              value={values.didWell}
              onChange={(e) => set("didWell", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            What should you do better next time?
            <textarea
              rows={2}
              value={values.doBetter}
              onChange={(e) => set("doBetter", e.target.value)}
              className={inputClass}
            />
          </label>
        </div>
        <fieldset className="mt-4">
          <legend className="text-xs text-muted">Tag any mistakes</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {MISTAKE_OPTIONS.map((o) => {
              const checked = values.mistakeTags.includes(o);
              return (
                <label
                  key={o}
                  className={`cursor-pointer rounded-full border px-3 py-1 text-xs ${
                    checked
                      ? "border-negative bg-negative/10 text-negative"
                      : "border-line text-muted"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => set("mistakeTags", toggleInList(values.mistakeTags, o))}
                    className="sr-only"
                  />
                  {o}
                </label>
              );
            })}
          </div>
        </fieldset>
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
          {(
            [
              ["emotionsBefore", "Before"],
              ["emotionsDuring", "During"],
              ["emotionsAfter", "After"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className={labelClass}>
              {label}
              <select
                value={values[key]}
                onChange={(e) => set(key, e.target.value)}
                className={inputClass}
              >
                <option value="">—</option>
                {EMOTION_OPTIONS.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
      </section>

      {/* Completeness warnings — never blocking (global rule 5) */}
      {warnings.length > 0 && (
        <div className="rounded-xl border border-line bg-surface-2/50 px-4 py-3 text-sm text-muted">
          <p className="font-medium text-text">A thin record is allowed. This would help:</p>
          <ul className="mt-1 list-inside list-disc">
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Client-side errors — courtesy only; the server is the real gate */}
      {errors.length > 0 && (
        <div role="alert" className="rounded-xl border border-negative/30 bg-negative/5 px-4 py-3 text-sm text-negative">
          <ul className="list-inside list-disc">
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </div>
      )}
      {submitError && (
        <p role="alert" className="text-sm text-negative">
          {submitError}
        </p>
      )}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={submitting}
          className="rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-bg transition-colors duration-150 ease-tl hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? "Saving…" : "Save trade"}
        </button>
      </div>
    </form>
  );
}
