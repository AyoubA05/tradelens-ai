import { useEffect, useRef, useState } from "react";

import {
  buildTradeCreatePayload,
  resolvedAsset,
  type NewTradeFormValues,
} from "@/lib/app/new-trade";
import type { components } from "@/lib/api/schema";

/**
 * New Trade draft autosave (Task D3): browser half.
 *
 * Deliberately NOT `server-only` — this is a hook a Client Component calls.
 * The one thing it may never do is create a trade or block a real submit
 * (global rule: "Autosave must never create a trade" /
 * design-decisions.md's cost-and-litter risk section); every property below
 * exists to hold that line:
 *
 *  - Debounced: a save is scheduled `DEBOUNCE_MS` after the last edit and
 *    the timer resets on every further edit, so a trader typing a paragraph
 *    fires one PUT, not one per keystroke.
 *  - Never fires on an empty form: `isDraftWorthSaving` gates every save,
 *    including the very first one — an untouched form autosaves nothing.
 *  - Non-blocking failure: `saveDraft` never throws out of this hook. A
 *    failed PUT only changes what `status` says; `handleSubmit` in
 *    `NewTradeForm` never reads `status` and cannot be affected by it.
 */
export type TradeDraftPayload = components["schemas"]["TradeDraftPayload"];
export type TradeDraftResponse = components["schemas"]["TradeDraftResponse"];

export type DraftStatus =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved" }
  | { kind: "error" };

export function draftStatusLabel(status: DraftStatus): string {
  switch (status.kind) {
    case "saving":
      return "Saving draft…";
    case "saved":
      return "Draft saved";
    case "error":
      // Deliberately vague and deliberately calm — a failed autosave is
      // background housekeeping, never an error the trader must clear, and
      // it must never be read as "your trade is at risk."
      return "Draft not saved — your entries are still here";
    case "idle":
      return "";
  }
}

const DEBOUNCE_MS = 1500;

/**
 * True when the form has anything worth persisting.
 *
 * Mirrors the emptiness the trader would recognise: an asset picked, a date
 * set, or an entry time typed. `emptyNewTradeFormValues()` already carries
 * non-blank defaults for several select fields (timeframe, biases, setup,
 * result), so checking "does every field equal its default" would call a
 * freshly-mounted, completely untouched form "non-empty" — these three are
 * the fields with no non-blank default, which is what makes them the right
 * emptiness test.
 */
export function isDraftWorthSaving(values: NewTradeFormValues, otherLabel: string): boolean {
  return (
    resolvedAsset(values, otherLabel) !== "" ||
    values.tradeDate !== "" ||
    values.entryTime.trim() !== ""
  );
}

/**
 * Fold the form's values into `TradeDraftPayload`.
 *
 * Reuses `buildTradeCreatePayload` rather than a second, hand-maintained
 * mapping: every field `TradeCreate` accepts from this form is also in
 * `TradeDraftPayload`'s allowlist (the schema mirrors `TradeCreate`
 * deliberately — see that type's own doc comment), so the same fold is
 * valid for both. `ai_suggestions` is never set here — this function only
 * ever writes what the trader typed, never a suggestion (global rule:
 * suggestions render from `ai_suggestions`, never become form values).
 */
export function toDraftPayload(
  values: NewTradeFormValues,
  otherLabel: string,
): TradeDraftPayload {
  return buildTradeCreatePayload(values, otherLabel);
}

async function relayGet(): Promise<TradeDraftResponse | null> {
  try {
    const response = await fetch("/api/trades/draft", { method: "GET" });
    if (!response.ok) return null;
    return (await response.json()) as TradeDraftResponse;
  } catch {
    return null;
  }
}

async function relayPut(payload: TradeDraftPayload): Promise<boolean> {
  try {
    const response = await fetch("/api/trades/draft", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Load the owner's saved draft once, on mount, and prefill blank form
 * fields from it; debounce-save the form back to the draft on every change
 * thereafter.
 *
 * Only fields the freshly-mounted form still has at its EMPTY default are
 * overwritten by the loaded draft — `tradeDate` is deliberately excluded
 * from that (it is prefilled with today's date by the caller before this
 * hook ever runs, so "still blank" never true for it; a stale draft date
 * silently resurrecting itself over "today" would be a surprise, not a
 * convenience).
 *
 * `suspended` stops all further saving. The caller sets it once the trade is
 * durable: `POST /v1/trades` clears the draft server-side (that is the half
 * that holds when this browser never comes back), and this is the half that
 * stops an in-flight debounce from writing the just-journaled values back
 * into a new draft a moment later.
 */
export function useDraftAutosave(
  values: NewTradeFormValues,
  setValues: (updater: (v: NewTradeFormValues) => NewTradeFormValues) => void,
  otherLabel: string,
  suspended = false,
): DraftStatus {
  const [status, setStatus] = useState<DraftStatus>({ kind: "idle" });
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const savingRef = useRef(0);

  // Load once. Deliberately not re-run on `values` change — this is a
  // mount-time prefill, not a sync loop.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const draft = await relayGet();
      if (cancelled || !draft?.draft) return;
      const d = draft.draft;
      setValues((v) => ({
        ...v,
        asset: v.asset || d.asset || v.asset,
        entryTime: v.entryTime || d.entry_time || v.entryTime,
        confirmationModel: v.confirmationModel || d.confirmation_model || v.confirmationModel,
        entryPrice: v.entryPrice || (d.entry_price != null ? String(d.entry_price) : v.entryPrice),
        stopPrice: v.stopPrice || (d.stop_price != null ? String(d.stop_price) : v.stopPrice),
        tpPrice: v.tpPrice || (d.tp_price != null ? String(d.tp_price) : v.tpPrice),
        exitPrice: v.exitPrice || (d.exit_price != null ? String(d.exit_price) : v.exitPrice),
        processNotes: v.processNotes || d.trade_process_notes || v.processNotes,
      }));
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    // No "skip the first pass" guard: `values` changing again once the
    // mount-time load resolves (it calls `setValues`) simply restarts this
    // same debounce with the merged values, so an early save of the
    // pre-load state is at worst redundant, never wrong — it can only ever
    // be superseded by a later one, exactly like any other edit.
    if (timerRef.current) clearTimeout(timerRef.current);
    // The trade these values became is durable, and the server has already
    // ended the draft on create. A debounce scheduled a moment before the
    // submit must not now write that finished trade straight back into a
    // fresh draft — the next New Trade would open pre-filled with it.
    // `savingRef` is bumped so a PUT already awaiting its response cannot
    // move the status either.
    if (suspended) {
      savingRef.current += 1;
      return;
    }
    if (!isDraftWorthSaving(values, otherLabel)) return;

    timerRef.current = setTimeout(() => {
      const attempt = ++savingRef.current;
      setStatus({ kind: "saving" });
      void relayPut(toDraftPayload(values, otherLabel)).then((ok) => {
        // A newer save superseded this one — its own status update is the
        // one that should win, so a slow, stale response must not clobber
        // it (neither "saved" from an old attempt nor "error" from one).
        if (attempt !== savingRef.current) return;
        setStatus({ kind: ok ? "saved" : "error" });
      });
    }, DEBOUNCE_MS);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [values, otherLabel, suspended]);

  return status;
}
