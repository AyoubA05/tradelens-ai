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
  ScreenshotUpload,
  type ScreenshotUploadStatus,
} from "@/components/app/new-trade/screenshot-upload";
import {
  abandonScreenshotUpload,
  attachScreenshot,
  attachScreenshotUrl,
} from "@/lib/app/screenshot-upload";
import {
  buildTradeCreatePayload,
  emptyNewTradeFormValues,
  validateNewTrade,
  type NewTradeFormValues,
} from "@/lib/app/new-trade";
import { useDraftAutosave, draftStatusLabel } from "@/lib/app/draft-autosave";
import { AutofillReview } from "@/components/app/new-trade/autofill-review";

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
  // Task D1: a link is an alternative source, never a second file — picking
  // one clears the other (see the file picker's `disabled` above and the
  // URL field's `disabled={... || !!file}`).
  const [screenshotUrl, setScreenshotUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [duplicateOf, setDuplicateOf] = useState<number | null>(null);
  const [uploadStatus, setUploadStatus] = useState<ScreenshotUploadStatus>({ kind: "idle" });
  // Set only once the trade actually exists. Everything downstream reads it
  // to decide what to say: while it is null a failure means nothing was
  // written, and once it is set NO failure may ever say that again.
  const [savedTradeId, setSavedTradeId] = useState<number | null>(null);
  const [screenshotProblem, setScreenshotProblem] = useState<string | null>(null);
  // A quarantine object left behind by a failed attach. Nothing else in the
  // system can name it, so abandoning it here is the only cleanup there is.
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  // `updated_at` from the create response, carried for the optional
  // suggestions-review PATCH below (Task D2) — that endpoint's own
  // conflict guard needs the stamp the trade was created with.
  const [createdUpdatedAt, setCreatedUpdatedAt] = useState<string | null>(null);
  // Set once a screenshot is attached — the id autofill needs (design
  // decision #4: it keys on a screenshot, and one cannot exist before this
  // point). `null` throughout a submit with no screenshot means the review
  // step below never appears, exactly like today.
  const [autofillScreenshotId, setAutofillScreenshotId] = useState<number | null>(null);
  // Shown instead of navigating away immediately once a screenshot is
  // attached, so the trader can review AI suggestions before leaving the
  // page they can still act on them from (Task D2).
  const [reviewingAutofill, setReviewingAutofill] = useState(false);

  function set<K extends keyof NewTradeFormValues>(key: K, value: NewTradeFormValues[K]) {
    setValues((v) => ({ ...v, [key]: value }));
  }

  // Task D3. Debounced, skips an empty form, and a save failure only ever
  // changes what this quiet indicator says — see the hook's own comment for
  // why that can never reach `submitError` or block `handleSubmit`.
  // Suspended the moment a submit starts, and thereafter once the trade is
  // durable: the server ends the draft on create, and this stops a debounce
  // scheduled just before the submit from writing the journaled values back
  // as a fresh draft the next New Trade would prefill from. `submitting` is
  // the half that matters for a debounce deadline falling *inside* the
  // create POST — waiting for `savedTradeId` would let that timer fire and
  // issue a PUT that cannot be cancelled, landing after the server cleared
  // the draft. A failed create sets `submitting` back to false, so autosave
  // resumes for a trade that is not journaled after all.
  const draftStatus = useDraftAutosave(
    values,
    setValues,
    OTHER_ASSET,
    submitting || savedTradeId !== null || duplicateOf !== null,
  );

  const { errors, warnings } = validateNewTrade(values, OTHER_ASSET);

  /**
   * Attach the picked screenshot to a trade that ALREADY EXISTS.
   *
   * Takes the trade id as an argument rather than resubmitting anything:
   * this is the same call the retry button makes, so a retry can never
   * create a second trade. (The server's fingerprint would refuse a
   * duplicate write anyway — but the UI must not offer a path that looks
   * like resubmitting the form.)
   *
   * Returns the attached screenshot's id, or `null` on any failure — the
   * caller uses this (not a bare boolean) so it can also decide whether
   * autofill review is possible.
   */
  async function runUpload(tradeId: number, file: File): Promise<number | null> {
    setScreenshotProblem(null);
    const result = await attachScreenshot(tradeId, file, {
      onPhase: (phase, progress) => setUploadStatus({ kind: "busy", phase, progress }),
    });
    return applyAttachResult(result);
  }

  /**
   * The URL sibling of `runUpload` (Task D1). One relay call rather than
   * three, so there is no `pendingKey` to abandon on failure — see
   * `attachScreenshotUrl`'s own comment.
   */
  async function runUrlIngest(tradeId: number, url: string): Promise<number | null> {
    setScreenshotProblem(null);
    setUploadStatus({ kind: "busy", phase: "validating", progress: 1 });
    const result = await attachScreenshotUrl(tradeId, url);
    return applyAttachResult(result);
  }

  function applyAttachResult(
    result: Awaited<ReturnType<typeof attachScreenshot>>,
  ): number | null {
    if (result.status === "attached") {
      setPendingKey(null);
      setUploadStatus({ kind: "attached" });
      setAutofillScreenshotId(result.screenshot.id);
      return result.screenshot.id;
    }
    setPendingKey(result.pendingKey ?? null);
    setUploadStatus({ kind: "problem", message: result.message });
    setScreenshotProblem(result.message);
    return null;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitError(null);
    setDuplicateOf(null);

    const payload = buildTradeCreatePayload(values, OTHER_ASSET);
    setSubmitting(true);
    // Local, not state: `setSavedTradeId` below does not update its own
    // `savedTradeId` binding within this same synchronous call, so the
    // catch block cannot rely on that state to know whether creation
    // already happened — it needs a value set and read in the same pass.
    let createdTradeId: number | null = null;
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
        // Nothing was created on this path, which is why it may say so.
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
      const created = (await response.json()) as {
        id: number;
        duplicate_of: number | null;
        updated_at?: string | null;
      };
      if (created.duplicate_of !== null) {
        // Design decision #5: this is not an error. Nothing new was
        // created; the existing trade is shown rather than a second row.
        setDuplicateOf(created.duplicate_of);
        return;
      }

      // Past this line the trade is durable (design decision #6). No
      // failure below may claim it was not saved, and none may send the
      // trader back through create.
      createdTradeId = created.id;
      setSavedTradeId(created.id);
      setCreatedUpdatedAt(created.updated_at ?? null);
      let attachedScreenshotId: number | null = null;
      if (screenshotFile) {
        attachedScreenshotId = await runUpload(created.id, screenshotFile);
        if (attachedScreenshotId === null) return; // the partial-failure panel takes over
      } else if (screenshotUrl.trim()) {
        attachedScreenshotId = await runUrlIngest(created.id, screenshotUrl.trim());
        if (attachedScreenshotId === null) return; // the partial-failure panel takes over
      }
      if (attachedScreenshotId !== null) {
        // A screenshot exists, so autofill can now run (design decision #4)
        // — offer the review step instead of navigating away immediately.
        // No screenshot means no suggestions are possible, so that case
        // navigates exactly as it always did.
        setReviewingAutofill(true);
        return;
      }
      router.push(`/app/trades/${created.id}`);
    } catch {
      // Design decision #6: once a trade exists, no failure may claim
      // nothing was saved — including one thrown here, after creation, by
      // something like `router.push`. Guard on the local `createdTradeId`
      // (not the `savedTradeId` state, which has not re-rendered yet within
      // this same call): unset means the POST response was never observed.
      // The server may still have committed before the connection failed, so
      // the copy must preserve that uncertainty; set means the trade is
      // durable and this falls through to
      // the same saved-trade panel a failed screenshot attach uses, never
      // back to "nothing was saved."
      if (createdTradeId !== null) {
        setSavedTradeId(createdTradeId);
        setScreenshotProblem(
          "Your trade is saved. Something went wrong after that — you can open it from here.",
        );
      } else {
        setSubmitError(
          "We could not confirm whether the trade was saved. Check your connection — it is safe to retry the same trade.",
        );
      }
    } finally {
      setSubmitting(false);
    }
  }

  /**
   * The trade is saved and the screenshot is not attached (design decision
   * #6 / Task D2).
   *
   * This panel exists so that a flaky upload can never be reported as a
   * lost trade. It offers exactly two ways forward — retry the upload
   * against the existing trade, or open the trade without a screenshot —
   * and deliberately offers no route back into the form, because that is
   * the only action here that could look like creating a second trade.
   */
  if (savedTradeId !== null && screenshotProblem !== null) {
    return (
      <div role="alert" className={sectionClass}>
        <h2 className={sectionTitleClass}>Your trade is saved. The screenshot did not attach.</h2>
        <p className="mt-2 max-w-md text-sm text-muted">
          The trade is recorded exactly as you entered it — nothing was lost. Only the chart image
          failed to upload.
        </p>
        <p className="mt-2 max-w-md break-words text-sm text-negative">{screenshotProblem}</p>
        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <button
            type="button"
            disabled={uploadStatus.kind === "busy" || (!screenshotFile && !screenshotUrl.trim())}
            onClick={async () => {
              // The existing trade id, never the form — same rule for both
              // sources (Task D1/D2). This recovery path goes straight to
              // the trade on success, same as before Task D2: the AI
              // suggestions review is offered on the main create path only
              // (see `handleSubmit`), not on this already-once-failed retry.
              const attached = screenshotFile
                ? await runUpload(savedTradeId, screenshotFile)
                : screenshotUrl.trim()
                  ? await runUrlIngest(savedTradeId, screenshotUrl.trim())
                  : null;
              if (attached !== null) {
                router.push(`/app/trades/${savedTradeId}`);
              }
            }}
            className="min-h-[44px] rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg transition-colors duration-150 ease-tl hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {uploadStatus.kind === "busy" ? "Uploading…" : "Try the upload again"}
          </button>
          <button
            type="button"
            onClick={() => {
              // Giving up on the upload is the moment the quarantine
              // object becomes litter, so this is where abandon belongs.
              if (pendingKey) void abandonScreenshotUpload(savedTradeId, pendingKey);
              router.push(`/app/trades/${savedTradeId}`);
            }}
            className="min-h-[44px] rounded-lg border border-line-strong px-4 py-2 text-sm text-text transition-colors duration-150 ease-tl hover:bg-surface-2"
          >
            Open the trade without a screenshot
          </button>
        </div>
        <p className="mt-3 text-xs text-muted">
          You can also attach a screenshot later from the trade&apos;s own page.
        </p>
      </div>
    );
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
        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <button
            type="button"
            onClick={() => router.push(`/app/trades/${duplicateOf}`)}
            className="min-h-[44px] rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg transition-colors duration-150 ease-tl hover:bg-accent/90"
          >
            View existing trade
          </button>
          <button
            type="button"
            onClick={() => setDuplicateOf(null)}
            className="min-h-[44px] rounded-lg border border-line-strong px-4 py-2 text-sm text-text transition-colors duration-150 ease-tl hover:bg-surface-2"
          >
            Edit and try again
          </button>
        </div>
      </div>
    );
  }

  // Task D2: the trade and its screenshot both already exist at this point
  // — creation happened above, in `handleSubmit`. Reviewing suggestions here
  // is strictly additive to that flow: skipping is always available and
  // behaves exactly like the pre-Phase-4E "just navigate" path.
  if (reviewingAutofill && savedTradeId !== null && autofillScreenshotId !== null) {
    return (
      <AutofillReview
        tradeId={savedTradeId}
        screenshotId={autofillScreenshotId}
        expectedUpdatedAt={createdUpdatedAt}
        onDone={() => router.push(`/app/trades/${savedTradeId}`)}
      />
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
        <div className="mt-3">
          <ScreenshotUpload
            file={screenshotFile}
            onSelect={(file) => {
              setScreenshotFile(file);
              if (file) setScreenshotUrl("");
              setUploadStatus({ kind: "idle" });
              setScreenshotProblem(null);
            }}
            url={screenshotUrl}
            onUrlChange={(url) => {
              setScreenshotUrl(url);
              setUploadStatus({ kind: "idle" });
              setScreenshotProblem(null);
            }}
            status={uploadStatus}
            disabled={submitting}
          />
        </div>
      </section>

      {/* Draft status — Task D3, a quiet indicator, never a gate. */}
      <p className="text-xs text-muted" aria-live="polite">
        {draftStatusLabel(draftStatus)}
      </p>

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
        <div className="break-words rounded-xl border border-line bg-surface-2/50 px-4 py-3 text-sm text-muted">
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
        <div role="alert" className="break-words rounded-xl border border-negative/30 bg-negative/5 px-4 py-3 text-sm text-negative">
          <ul className="list-inside list-disc">
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </div>
      )}
      {submitError && (
        <p role="alert" className="break-words text-sm text-negative">
          {submitError}
        </p>
      )}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={submitting}
          className="min-h-[44px] w-full rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-bg sm:w-auto transition-colors duration-150 ease-tl hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? "Saving…" : "Save trade"}
        </button>
      </div>
    </form>
  );
}
