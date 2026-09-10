"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import type { StrategyFields, StrategyResponse } from "@/lib/app/strategy";

/**
 * The playbook editor.
 *
 * Explicit save, never autosave: every save changes what the AI reads and
 * retires cached reviews, so it is a deliberate act. The whole playbook is
 * sent every time (the server does a full replacement) together with the
 * version this editor was loaded from, so a stale tab is refused rather
 * than allowed to overwrite a newer playbook.
 *
 * A refused save never discards what the trader typed. Nothing is truncated
 * here or on the server: a field over its limit is marked, and the trader
 * shortens it themselves.
 */

type FieldKey = keyof StrategyFields;
type Values = Record<FieldKey, string>;

type FieldSpec = {
  key: FieldKey;
  label: string;
  placeholder: string;
  multiline: boolean;
};

// Which inputs sit under which heading. Layout, not a rule: whether a section
// counts as "written" is decided server-side and shown in the summary.
const SECTIONS: { id: string; fields: FieldSpec[] }[] = [
  {
    id: "identity",
    fields: [
      { key: "name", label: "Strategy Name", placeholder: "e.g. ICT OB Strategy", multiline: false },
      {
        key: "trading_style",
        label: "Trading Style",
        placeholder: "e.g. ICT, SMC, Price Action",
        multiline: false,
      },
      {
        key: "markets",
        label: "Markets / Assets",
        placeholder: "e.g. NQ, ES, BTCUSD, EURUSD",
        multiline: false,
      },
      { key: "timeframes", label: "Timeframes", placeholder: "e.g. 15m, 1H, 4H", multiline: false },
    ],
  },
  {
    id: "entry",
    fields: [
      {
        key: "entry_rules",
        label: "What has to be true before you enter",
        placeholder: "e.g. BOS + OB retest on 15m, CHoCH confirmation required",
        multiline: true,
      },
    ],
  },
  {
    id: "exit",
    fields: [
      {
        key: "stop_rules",
        label: "Where the stop goes",
        placeholder: "e.g. Behind the OB wick, no more than 10 points away",
        multiline: true,
      },
      {
        key: "take_profit_rules",
        label: "Where you take profit",
        placeholder: "e.g. Next opposing OB, 50% at 1:1 R, runner to 1:3",
        multiline: true,
      },
    ],
  },
  {
    id: "risk",
    fields: [
      {
        key: "risk_rules",
        label: "How much you risk, and how often",
        placeholder: "e.g. Max 1% per trade, max 2 trades per session, 1:2 R:R minimum",
        multiline: true,
      },
    ],
  },
  {
    id: "setups",
    fields: [
      {
        key: "setups_traded",
        label: "What you trade",
        placeholder: "e.g. OB retest, FVG fill, liquidity sweep + reversal",
        multiline: true,
      },
      {
        key: "setups_avoided",
        label: "What you skip",
        placeholder: "e.g. Counter-trend, news events, choppy consolidation",
        multiline: true,
      },
      {
        key: "news_session_rules",
        label: "When you stay out",
        placeholder: "e.g. No trades 30 min before/after high-impact news; NY AM only",
        multiline: false,
      },
    ],
  },
  {
    id: "self_awareness",
    fields: [
      {
        key: "common_mistakes",
        label: "What you want reviews to watch for",
        placeholder: "e.g. Entering too early before confirmation, revenge trading",
        multiline: true,
      },
    ],
  },
];

const FIELD_KEYS = SECTIONS.flatMap((s) => s.fields.map((f) => f.key));

const inputClass =
  "w-full rounded-md border border-line bg-chart px-2 py-1.5 text-sm text-text outline-none focus:border-accent aria-[invalid=true]:border-negative";

const CONFLICT_TEXT =
  "This playbook changed in another tab or device. Your edits are still here.";

function toValues(fields: StrategyFields | null | undefined): Values {
  return Object.fromEntries(FIELD_KEYS.map((k) => [k, fields?.[k] ?? ""])) as Values;
}

function sameValues(a: Values, b: Values): boolean {
  return FIELD_KEYS.every((k) => a[k] === b[k]);
}

function problemText(problem: string, limit: number): string {
  if (problem === "too_long") return `Longer than the ${limit}-character limit. Shorten it to save.`;
  if (problem === "required") return "Strategy name is required — it is how reviews refer to this playbook.";
  if (problem === "invalid_characters") return "Contains characters that cannot be saved.";
  return "This field could not be saved.";
}

export function PlaybookEditor({ data }: { data: StrategyResponse }) {
  const router = useRouter();
  const [saved, setSaved] = useState<Values>(() => toValues(data.profile));
  const [values, setValues] = useState<Values>(() => toValues(data.profile));
  const [revision, setRevision] = useState<string | null>(data.revision);
  const [pending, setPending] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [problems, setProblems] = useState<Partial<Record<FieldKey, string>>>({});
  const [status, setStatus] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const reloadRequested = useRef(false);

  const dirty = useMemo(() => !sameValues(values, saved), [values, saved]);

  // A newer server version (another tab's save, an added insight, or a
  // requested reload) replaces the editor ONLY when that cannot discard
  // typing: the trader asked for it, or there is nothing unsaved.
  useEffect(() => {
    if (data.revision === revision) return;
    if (reloadRequested.current || !dirty) {
      const fresh = toValues(data.profile);
      setSaved(fresh);
      setValues(fresh);
      setRevision(data.revision);
      setConflict(false);
      setProblems({});
      reloadRequested.current = false;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.revision]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const overLimit = FIELD_KEYS.filter((k) => values[k].length > data.limits[k]);

  function applyStarter() {
    const hasText = FIELD_KEYS.some((k) => values[k].trim() !== "");
    if (
      hasText &&
      !window.confirm(
        "Replace what is in the editor with the starter playbook? Nothing is saved until you press Save playbook.",
      )
    ) {
      return;
    }
    setValues(toValues(data.starter));
    setProblems({});
    setStatus(null);
  }

  function loadSaved() {
    if (!window.confirm("Replace your edits with the saved version? Your unsaved text will be lost.")) {
      return;
    }
    reloadRequested.current = true;
    router.refresh();
  }

  async function save() {
    setStatus(null);
    if (values.name.trim() === "") {
      setProblems({ name: "required" });
      return;
    }
    if (overLimit.length) {
      setProblems(Object.fromEntries(overLimit.map((k) => [k, "too_long"])));
      setStatus({ tone: "error", text: "Shorten the highlighted fields to save." });
      return;
    }
    setProblems({});
    setPending(true);
    const body = {
      ...Object.fromEntries(FIELD_KEYS.map((k) => [k, values[k].trim() === "" ? null : values[k]])),
      expected_revision: revision,
    };
    try {
      const response = await fetch("/api/strategy", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = (await response.json().catch(() => ({}))) as Partial<StrategyResponse> & {
        detail?: unknown;
      };
      if (response.ok && payload.revision !== undefined) {
        const fresh = toValues(payload.profile ?? null);
        setSaved(fresh);
        setValues(fresh);
        setRevision(payload.revision ?? null);
        setConflict(false);
        setStatus({ tone: "ok", text: "Playbook saved. AI reviews will now use your rules." });
        router.refresh();
        return;
      }
      if (response.status === 409) {
        setConflict(true);
        return;
      }
      if (response.status === 422 && Array.isArray(payload.detail)) {
        const next: Partial<Record<FieldKey, string>> = {};
        for (const item of payload.detail as { field?: string; problem?: string }[]) {
          if (item.field && FIELD_KEYS.includes(item.field as FieldKey) && item.problem) {
            next[item.field as FieldKey] = item.problem;
          }
        }
        setProblems(next);
        setStatus({ tone: "error", text: "Some fields could not be saved. They are marked below." });
        return;
      }
      setStatus({ tone: "error", text: "Could not save the playbook. Try again." });
    } catch {
      setStatus({ tone: "error", text: "Could not save the playbook. Try again." });
    } finally {
      setPending(false);
    }
  }

  const labels = Object.fromEntries(data.sections.map((s) => [s.id, s.label]));

  return (
    <form
      data-testid="playbook-editor"
      aria-label="Edit your playbook"
      onSubmit={(event) => {
        event.preventDefault();
        void save();
      }}
      className="mt-6 rounded-xl border border-line bg-surface p-5"
    >
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={applyStarter}
          className="min-h-[44px] rounded-lg border border-line-strong px-4 py-2 text-sm text-text transition-colors duration-150 ease-tl hover:bg-surface-2"
        >
          Start from the ICT/SMC starter playbook
        </button>
        <p className="text-xs text-muted">
          A starting template to edit into your own rules. It is not a recommendation, and nothing
          is saved until you press Save playbook.
        </p>
      </div>

      {SECTIONS.map((section, index) => {
        const body = (
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            {section.fields.map((field) => {
              const id = `strategy-${field.key}`;
              const length = values[field.key].length;
              const limit = data.limits[field.key];
              const over = length > limit;
              const legacy = data.over_limit.includes(field.key);
              const problem = problems[field.key];
              const describedBy = [`${id}-count`, problem || over ? `${id}-problem` : null]
                .filter(Boolean)
                .join(" ");
              return (
                <div
                  key={field.key}
                  className={field.multiline ? "flex flex-col gap-1 sm:col-span-2" : "flex flex-col gap-1"}
                >
                  <label htmlFor={id} className="text-xs text-muted">
                    {field.label}
                  </label>
                  {field.multiline ? (
                    <textarea
                      id={id}
                      rows={4}
                      value={values[field.key]}
                      placeholder={field.placeholder}
                      aria-invalid={over || Boolean(problem)}
                      aria-describedby={describedBy}
                      onChange={(e) => setValues((v) => ({ ...v, [field.key]: e.target.value }))}
                      className={inputClass}
                    />
                  ) : (
                    <input
                      id={id}
                      type="text"
                      value={values[field.key]}
                      placeholder={field.placeholder}
                      aria-invalid={over || Boolean(problem)}
                      aria-describedby={describedBy}
                      onChange={(e) => setValues((v) => ({ ...v, [field.key]: e.target.value }))}
                      className={inputClass}
                    />
                  )}
                  <p
                    id={`${id}-count`}
                    className={`font-mono text-[11px] ${over ? "text-negative" : "text-muted"}`}
                  >
                    {`${length} / ${limit}`}
                  </p>
                  {problem || over ? (
                    <p id={`${id}-problem`} role="alert" className="text-xs text-negative">
                      {legacy && over && !problem
                        ? `This rule is longer than the ${limit}-character limit. Shorten it to save.`
                        : problemText(problem ?? "too_long", limit)}
                    </p>
                  ) : null}
                  {field.key === "name" ? (
                    <p className="text-xs text-muted">
                      Trades you log from now on carry this name. Earlier trades keep the name they
                      were logged with.
                    </p>
                  ) : null}
                </div>
              );
            })}
          </div>
        );
        return index === 0 ? (
          <fieldset key={section.id} className="mt-6">
            <legend className="font-display text-lg font-semibold text-text">
              {labels[section.id] ?? section.id}
            </legend>
            {body}
          </fieldset>
        ) : (
          <details key={section.id} className="mt-4 rounded-lg border border-line px-3 py-2" open={
            section.fields.some((f) => data.over_limit.includes(f.key))
          }>
            <summary className="min-h-[44px] cursor-pointer py-2 font-display text-base font-semibold text-text">
              {labels[section.id] ?? section.id}
            </summary>
            {body}
          </details>
        );
      })}

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={pending}
          className="min-h-[44px] rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg transition-colors duration-150 ease-tl hover:bg-accent/90 disabled:opacity-60"
        >
          Save playbook
        </button>
        {dirty ? <p className="text-xs text-muted">Unsaved changes</p> : null}
      </div>

      {conflict ? (
        <div role="alert" data-testid="playbook-conflict" className="mt-4 rounded-lg border border-negative/30 bg-negative/5 px-4 py-3">
          <p className="text-sm text-text">{CONFLICT_TEXT}</p>
          <button
            type="button"
            onClick={loadSaved}
            className="mt-2 min-h-[44px] rounded-lg border border-line-strong px-3 py-1.5 text-sm text-text transition-colors duration-150 ease-tl hover:bg-surface-2"
          >
            Load the saved version
          </button>
        </div>
      ) : null}

      <p aria-live="polite" data-testid="playbook-status" className="mt-3 text-sm">
        {status ? (
          <span className={status.tone === "ok" ? "text-positive" : "text-negative"}>
            {status.text}
          </span>
        ) : null}
      </p>
    </form>
  );
}
