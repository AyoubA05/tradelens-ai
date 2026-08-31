"use client";

import { useId, useRef } from "react";

import { ACCEPTED_SCREENSHOT_TYPES, type UploadPhase } from "@/lib/app/screenshot-upload";

/**
 * The chart screenshot island on the New Trade form (Task D1).
 *
 * Optional, always. A trade with no screenshot is an ordinary record, not a
 * missing one — so the idle state is a plain invitation with no empty frame
 * and no placeholder image, and nothing here ever renders an <img> for a
 * file that was not attached.
 *
 * The upload cannot start until the trade exists (design decision #1: the
 * trade's id is what authorises it), so selecting a file here only holds it
 * — `NewTradeForm` runs the presign/PUT/finalize sequence after the create
 * succeeds and feeds the phase back in through `phase`/`progress`.
 */

export type ScreenshotUploadStatus =
  | { kind: "idle" }
  | { kind: "busy"; phase: UploadPhase; progress: number }
  | { kind: "attached" }
  | { kind: "problem"; message: string };

const BUSY_LABEL: Record<UploadPhase, string> = {
  presigning: "Preparing the upload…",
  uploading: "Uploading…",
  validating: "Checking the image…",
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ScreenshotUpload({
  file,
  onSelect,
  url,
  onUrlChange,
  status,
  disabled = false,
}: {
  file: File | null;
  onSelect: (file: File | null) => void;
  /** The URL text field's value (Task D1). `undefined` hides the field
   *  entirely — callers that have not adopted image-URL ingest yet see no
   *  behaviour change. */
  url?: string;
  onUrlChange?: (url: string) => void;
  status: ScreenshotUploadStatus;
  disabled?: boolean;
}) {
  const inputId = useId();
  const urlInputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const busy = status.kind === "busy";
  const urlEnabled = onUrlChange !== undefined;

  function clear() {
    onSelect(null);
    // The input keeps its own value, so re-picking the same file after a
    // failure would fire no change event without this reset.
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        {/* A label styled as the control: a 44px-tall tap target that works
            one-handed, rather than the browser's own tiny file button. */}
        <label
          htmlFor={inputId}
          className={`inline-flex min-h-[44px] w-full items-center justify-center rounded-lg border border-line-strong px-4 py-2.5 text-sm font-medium text-text transition-colors duration-150 ease-tl sm:w-auto ${
            disabled || busy ? "cursor-not-allowed opacity-60" : "cursor-pointer hover:bg-surface-2"
          }`}
        >
          {file ? "Choose a different screenshot" : "Choose a screenshot"}
          <input
            id={inputId}
            ref={inputRef}
            type="file"
            accept={ACCEPTED_SCREENSHOT_TYPES.join(",")}
            disabled={disabled || busy}
            onChange={(e) => onSelect(e.target.files?.[0] ?? null)}
            className="sr-only"
          />
        </label>
        {file && !busy && (
          <button
            type="button"
            onClick={clear}
            className="min-h-[44px] rounded-lg px-3 text-sm text-muted underline-offset-2 hover:text-text hover:underline"
          >
            Remove
          </button>
        )}
      </div>

      {/* `break-all` and `min-w-0`: a long unbroken filename must wrap
          inside the card at ~375px, never push the form sideways. */}
      <p className="min-w-0 break-all text-xs text-muted">
        {file ? (
          <>
            <span className="font-mono text-text">{file.name}</span>
            <span> · {formatSize(file.size)}</span>
          </>
        ) : url && url.trim() ? (
          "One link, one screenshot — picking a file above replaces it."
        ) : (
          "No screenshot selected. That is fine — a trade without one is a complete record."
        )}
      </p>

      {/* Beside the file picker, not replacing it (Task D1) — a trader can
          paste a chart link instead of a local file. Hidden entirely when
          the caller passes no `onUrlChange`, so a caller that has not
          adopted URL ingest sees no behaviour change. */}
      {urlEnabled && (
        <label className="flex flex-col gap-1 text-xs text-muted">
          Or paste a link to a chart image
          <input
            id={urlInputId}
            type="url"
            inputMode="url"
            placeholder="https://…"
            // `min-w-0`: a long unbroken URL must wrap inside the card at
            // ~375px, never push the form sideways (same rule as the
            // filename above; `break-all` lives on the input's own text via
            // `break-words` since a text input cannot break mid-token on its
            // own, but the wrapping guarantee here is about the CONTAINER
            // never growing past the card — the value itself is invisible
            // once typed past the visible width, which is standard input
            // behaviour and not a layout defect).
            value={url ?? ""}
            disabled={disabled || busy || !!file}
            onChange={(e) => onUrlChange?.(e.target.value)}
            className="min-w-0 w-full rounded-md border border-line bg-chart px-2 py-1.5 text-sm text-text outline-none focus:border-accent disabled:cursor-not-allowed disabled:opacity-60"
          />
        </label>
      )}

      {busy && (
        <div>
          <p className="text-xs text-muted" aria-live="polite">
            {BUSY_LABEL[status.phase]}
          </p>
          <div
            role="progressbar"
            aria-label="Screenshot upload"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(status.progress * 100)}
            className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-chart"
          >
            <div
              className="h-full rounded-full bg-accent transition-[width] duration-150 ease-tl"
              style={{ width: `${Math.round(status.progress * 100)}%` }}
            />
          </div>
        </div>
      )}

      {status.kind === "attached" && (
        <p className="text-xs text-positive">Screenshot attached to this trade.</p>
      )}

      {status.kind === "problem" && (
        <p role="alert" className="text-xs text-negative">
          {status.message}
        </p>
      )}
    </div>
  );
}
