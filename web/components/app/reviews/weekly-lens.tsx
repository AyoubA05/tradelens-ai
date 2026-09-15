"use client";

import { useRouter } from "next/navigation";

import type { components } from "@/lib/api/schema";
import { EmptyState } from "@/components/app/states/empty-state";
import { PeriodStrip } from "@/components/app/reviews/period-strip";
import {
  ReviewNote,
  sampleConfidence,
  sampleLimitation,
} from "@/components/app/reviews/review-note";
import { useReviewJob } from "@/components/app/reviews/use-review-job";

type SavedNote = components["schemas"]["SavedNote"];

/**
 * Weekly Recap: one completed week, read back.
 *
 * Opening the lens never generates (R2) — a saved recap is shown if there is
 * one, otherwise an explicit button. The saved recap stays on screen while a
 * regeneration runs and after it fails or is superseded; only a successful
 * regeneration replaces it.
 */
export function WeeklyLens({
  weeks,
  selectedWeek,
  saved,
  completeTrades,
  tradesForReview,
  aiAvailable,
}: {
  weeks: string[];
  selectedWeek: string | null;
  saved: SavedNote | null;
  completeTrades: number;
  tradesForReview: number;
  aiAvailable: boolean;
}) {
  const router = useRouter();
  const job = useReviewJob("/api/reviews/weekly");

  if (weeks.length === 0 || !selectedWeek) {
    return (
      <div className="mt-6">
        <EmptyState
          title="No completed week to review"
          description="A weekly recap reads a week with journaled trades. Log trades and the week appears here."
          action={{ href: "/app/journal", label: "Open the Journal" }}
        />
      </div>
    );
  }

  const note = job.note ?? saved;
  const remaining = Math.max(tradesForReview - completeTrades, 0);
  const gated = remaining > 0 && !note;
  const running = job.state === "running";
  const showButton = aiAvailable && !gated && job.state !== "rate_limited";
  const options = weeks.includes(selectedWeek) ? weeks : [selectedWeek, ...weeks];

  return (
    <div className="mt-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <label className="flex min-w-0 flex-col gap-1 text-sm text-muted">
          Week starting
          <select
            value={selectedWeek}
            onChange={(event) =>
              router.push(`/app/reviews?lens=weekly&week=${encodeURIComponent(event.target.value)}`)
            }
            className="min-h-11 w-full rounded-lg border border-line bg-surface px-3 text-sm text-text sm:w-auto"
          >
            {options.map((week) => (
              <option key={week} value={week}>
                {week}
              </option>
            ))}
          </select>
        </label>
        {showButton && (
          <button
            type="button"
            onClick={() => void job.start({ week: selectedWeek })}
            disabled={running}
            aria-busy={running}
            className="min-h-11 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-background disabled:cursor-wait disabled:opacity-60"
          >
            {saved || job.note ? "Regenerate this week" : "Generate weekly recap"}
          </button>
        )}
      </div>

      {!aiAvailable && (
        <p className="mt-4 text-sm text-muted">
          AI reviews are unavailable right now. Saved recaps are still shown.
        </p>
      )}
      {aiAvailable && gated && (
        <p className="mt-4 text-sm text-muted">
          Journal {remaining} more completed trades before the first weekly recap.
        </p>
      )}
      {running && (
        <p role="status" className="mt-4 text-sm text-muted">
          Writing the recap for this week. Anything already saved stays here until it is ready.
        </p>
      )}
      {job.state === "rate_limited" && job.message && (
        <p role="status" className="mt-4 text-sm text-muted">
          {job.message}
        </p>
      )}
      {(job.state === "failed" || job.state === "superseded" || job.state === "refused") &&
        job.message && (
          <p role="alert" className="mt-4 text-sm text-negative">
            {job.message}
          </p>
        )}

      {note ? (
        <>
          <PeriodStrip stats={note.stats} />
          <ReviewNote
            title="Week in review"
            sample={`Week of ${note.period} · ${note.reviewed_trades} trades reviewed`}
            content={note.content_md}
            confidence={sampleConfidence(note.reviewed_trades)}
            limitation={sampleLimitation(note.reviewed_trades)}
          />
        </>
      ) : (
        !gated && (
          <p className="mt-6 text-sm text-muted">No recap is saved for this week yet.</p>
        )
      )}
    </div>
  );
}
