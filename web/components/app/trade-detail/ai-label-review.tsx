"use client";

import { useCallback, useState } from "react";

import type { AIAnalysisDetail, AIAnalysisLabelPatch } from "@/lib/app/trade-analysis";

/**
 * Per-field review of the AI's labels (Task D3).
 *
 * The backend keeps a confirmation lock. A field named in `confirmed_fields`
 * is a value the trader stands behind, and no analysis job will overwrite it,
 * however new that job is. A field not in that list is the AI's current
 * reading, and a newer analysis may replace it.
 *
 * Two consequences shape this component, and both are the point of it:
 *
 * - Saving a new value for a field CONFIRMS it. It locks that field and
 *   unlocks nothing.
 * - `release` is the only way to lower the lock, and it is its own explicit
 *   action. Releasing does not revert anything — the trader's value stands
 *   until a newer analysis writes over it — so the copy says exactly that
 *   and the displayed value is left alone.
 *
 * Only fields the trader actually edited are sent. The patch schema is an
 * `extra="forbid"` allowlist where an absent key means "leave this alone",
 * so echoing the untouched fields back would re-confirm labels the trader
 * never looked at — quietly turning the AI's guesses into their judgement.
 *
 * Nothing here is forward-looking: these are labels on a trade that is
 * already closed.
 */

type FieldName = "bias" | "detected_setup" | "trade_quality" | "matched_strategy";

type Field = {
  name: FieldName;
  label: string;
  numeric?: true;
};

const FIELDS: Field[] = [
  { name: "bias", label: "Bias at entry" },
  { name: "detected_setup", label: "Setup described" },
  { name: "matched_strategy", label: "Matched strategy" },
  { name: "trade_quality", label: "Trade quality (1–5)", numeric: true },
];

const GRADE_LABEL = "Your grade";

const NOTHING_CHANGED = "Nothing has been changed yet, so there was nothing to save.";
const SAVE_FAILED =
  "These labels weren't saved — the change didn't reach the server. Your edits are still here exactly as you typed them, and you can try again.";
const QUALITY_INVALID =
  "Trade quality is a whole number from 1 to 5. Nothing was saved while it reads otherwise.";
const RELEASE_NOTE =
  "This value stays as you left it; a newer analysis may update it again.";

const inputClass =
  "w-full rounded-md border border-line bg-chart px-2 py-1.5 text-sm text-text outline-none focus:border-accent";
const labelClass = "flex flex-col gap-1 text-xs text-muted";

type Values = Record<FieldName | "user_grade", string>;

function valuesOf(analysis: AIAnalysisDetail): Values {
  return {
    bias: analysis.bias ?? "",
    detected_setup: analysis.detected_setup ?? "",
    matched_strategy: analysis.matched_strategy ?? "",
    trade_quality: analysis.trade_quality === null ? "" : String(analysis.trade_quality),
    user_grade: analysis.user_grade ?? "",
  };
}

export function AILabelReview({
  analysis,
  tradeId,
  onSaved,
}: {
  analysis: AIAnalysisDetail;
  tradeId: number;
  onSaved: () => void;
}) {
  // The baseline is what the server last told us it holds. The diff is taken
  // against it, so "changed" survives a save without a page refetch.
  const [baseline, setBaseline] = useState<Values>(() => valuesOf(analysis));
  const [values, setValues] = useState<Values>(() => valuesOf(analysis));
  const [confirmed, setConfirmed] = useState<string[]>(() => analysis.confirmed_fields);

  /**
   * What the newest analysis read for one label, or null.
   *
   * A locked field is never overwritten by a job, so without this the
   * trader could not see that a re-analysis had read something different —
   * they would have to release the field, re-run, and hope. Offering the
   * value with an explicit "Use it" keeps the decision theirs: nothing is
   * applied until they click, and clicking only fills the input, which they
   * then still have to save.
   */
  const proposalFor = (name: string): string | null => {
    const proposals = analysis.latest_proposals ?? {};
    const value = (proposals as Record<string, string>)[name];
    return typeof value === "string" && value !== "" ? value : null;
  };
  const [message, setMessage] = useState<{ tone: "note" | "problem"; text: string } | null>(
    null,
  );
  const [saving, setSaving] = useState(false);

  const send = useCallback(
    async (patch: Partial<AIAnalysisLabelPatch>, applied: Partial<Values>) => {
      setSaving(true);
      setMessage(null);
      try {
        const response = await fetch(`/api/trades/${tradeId}/analysis`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(patch),
          cache: "no-store",
          credentials: "same-origin",
        });
        if (!response.ok) throw new Error("patch failed");
        const labels = (await response.json()) as { confirmed_fields?: unknown };
        if (Array.isArray(labels.confirmed_fields)) {
          setConfirmed(labels.confirmed_fields.map(String));
        }
        // Only what we sent moves into the baseline. A field the trader is
        // still editing is not silently adopted as saved.
        setBaseline((current) => ({ ...current, ...applied }));
        setMessage({ tone: "note", text: "Saved." });
        onSaved();
      } catch {
        setMessage({ tone: "problem", text: SAVE_FAILED });
      } finally {
        setSaving(false);
      }
    },
    [onSaved, tradeId],
  );

  const save = useCallback(() => {
    const patch: Partial<AIAnalysisLabelPatch> = {};
    const applied: Partial<Values> = {};

    for (const field of FIELDS) {
      const typed = values[field.name].trim();
      if (typed === baseline[field.name].trim()) continue;
      if (field.numeric) {
        // A blank or a word must never leave here as NaN, which JSON would
        // render as `null` and the server would read as a real value.
        if (!/^-?\d+$/.test(typed)) {
          setMessage({ tone: "problem", text: QUALITY_INVALID });
          return;
        }
        const parsed = Number.parseInt(typed, 10);
        if (!Number.isInteger(parsed) || parsed < 1 || parsed > 5) {
          setMessage({ tone: "problem", text: QUALITY_INVALID });
          return;
        }
        patch.trade_quality = parsed;
        applied.trade_quality = typed;
        continue;
      }
      if (typed === "") continue;
      patch[field.name as Exclude<FieldName, "trade_quality">] = typed;
      applied[field.name] = typed;
    }

    const grade = values.user_grade.trim();
    if (grade !== baseline.user_grade.trim() && grade !== "") {
      patch.user_grade = grade;
      applied.user_grade = grade;
    }

    if (Object.keys(patch).length === 0) {
      setMessage({ tone: "note", text: NOTHING_CHANGED });
      return;
    }
    void send(patch, applied);
  }, [baseline, send, values]);

  const release = useCallback(
    (name: FieldName) => {
      // Release lowers the lock and touches no value: the trader's reading
      // stands until a newer analysis replaces it.
      void send({ release: [name] }, {});
    },
    [send],
  );

  return (
    <div className="mt-6 border-t border-line pt-5">
      <h3 className="font-display text-base font-semibold text-text">Your labels</h3>
      <p className="mt-1 max-w-xl text-sm leading-6 text-muted">
        These describe the trade you already took. Change one and it becomes yours: no later
        analysis will write over it until you hand it back.
      </p>

      <div className="mt-4 space-y-3">
        {FIELDS.map((field) => {
          const isConfirmed = confirmed.includes(field.name);
          return (
            <div
              key={field.name}
              data-testid={`label-field-${field.name}`}
              data-confirmed={isConfirmed ? "true" : "false"}
              className={
                isConfirmed
                  ? "rounded-lg border border-line-strong bg-surface-2 p-3"
                  : "rounded-lg border border-dashed border-line p-3"
              }
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
                  {isConfirmed ? "You confirmed this" : "The AI's reading"}
                </p>
                {isConfirmed && (
                  <button
                    type="button"
                    onClick={() => release(field.name)}
                    disabled={saving}
                    aria-label={`Let a newer analysis update ${field.label}`}
                    className="min-h-11 rounded-lg border border-line-strong px-3 py-1.5 text-xs font-semibold text-text transition-colors duration-150 ease-tl hover:bg-surface disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Let a newer analysis update this
                  </button>
                )}
              </div>
              <label className={`${labelClass} mt-2`}>
                {field.label}
                <input
                  type="text"
                  inputMode={field.numeric ? "numeric" : undefined}
                  value={values[field.name]}
                  onChange={(event) =>
                    setValues((current) => ({ ...current, [field.name]: event.target.value }))
                  }
                  className={inputClass}
                />
              </label>
              {isConfirmed && <p className="mt-2 text-xs leading-5 text-muted">{RELEASE_NOTE}</p>}
              {isConfirmed &&
                proposalFor(field.name) !== null &&
                proposalFor(field.name) !== values[field.name] && (
                  <div
                    data-testid={`label-proposal-${field.name}`}
                    className="mt-2 flex flex-wrap items-center gap-2 border-t border-line pt-2"
                  >
                    {/* Locked means "not applied", never "hidden". The newest
                        analysis still read something for this field; showing
                        it is what stops the lock from becoming a blindfold.
                        Applying is the trader's click, never automatic. */}
                    <p className="text-xs leading-5 text-muted">
                      The latest analysis read{" "}
                      <span className="font-medium text-text">{proposalFor(field.name)}</span>.
                    </p>
                    <button
                      type="button"
                      onClick={() =>
                        setValues((current) => ({
                          ...current,
                          [field.name]: proposalFor(field.name) as string,
                        }))
                      }
                      disabled={saving}
                      aria-label={`Use the latest reading for ${field.label}`}
                      className="min-h-11 rounded-lg border border-line-strong px-3 py-1.5 text-xs font-semibold text-text transition-colors duration-150 ease-tl hover:bg-surface disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      Use it
                    </button>
                  </div>
                )}
            </div>
          );
        })}

        <div className="rounded-lg border border-dashed border-line p-3">
          <label className={labelClass}>
            {GRADE_LABEL}
            <input
              type="text"
              value={values.user_grade}
              onChange={(event) =>
                setValues((current) => ({ ...current, user_grade: event.target.value }))
              }
              className={inputClass}
            />
          </label>
          <p className="mt-2 text-xs leading-5 text-muted">
            Your own grade for how you executed this trade. The AI never overwrites it.
          </p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="min-h-11 rounded-lg border border-line-strong px-4 py-2 text-sm font-semibold text-text transition-colors duration-150 ease-tl hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {saving ? "Saving…" : "Save these labels"}
        </button>
        {message !== null && (
          <p
            className="max-w-md text-sm leading-6 text-muted"
            role={message.tone === "problem" ? "alert" : "status"}
          >
            {message.text}
          </p>
        )}
      </div>
    </div>
  );
}
