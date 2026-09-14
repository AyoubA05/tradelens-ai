"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import type { components } from "@/lib/api/schema";
import { EmptyState } from "@/components/app/states/empty-state";
import { PeriodStrip } from "@/components/app/reviews/period-strip";
import {
  ReviewNote,
  sampleConfidence,
  SMALL_SAMPLE_LIMITATION,
} from "@/components/app/reviews/review-note";
import { useReviewJob } from "@/components/app/reviews/use-review-job";

type SavedNote = components["schemas"]["SavedNote"];

/**
 * Daily Debrief: one trading day, read back.
 *
 * Generated only from the explicit button. The lens holds no per-day count;
 * the API refuses a day with nothing logged (`empty_period`). A saved debrief
 * stays on screen until a successful regeneration replaces it.
 */
export function DailyLens({
  days,
  selectedDay,
  saved,
  aiAvailable,
}: {
  days: string[];
  selectedDay: string | null;
  saved: SavedNote | null;
  aiAvailable: boolean;
}) {
  const router = useRouter();
  const job = useReviewJob("/api/reviews/daily");

  if (days.length === 0 || !selectedDay) {
    return (
      <div className="mt-6">
        <EmptyState
          title="No trading day to review"
          description="A daily debrief reads one day with journaled trades. Log trades and the day appears here."
          action={{ href: "/app/journal", label: "Open the Journal" }}
        />
      </div>
    );
  }

  const note = job.note ?? saved;
  const running = job.state === "running";
  const showButton = aiAvailable && job.state !== "rate_limited";
  const options = days.includes(selectedDay) ? days : [selectedDay, ...days];

  return (
    <div className="mt-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <label className="flex min-w-0 flex-col gap-1 text-sm text-muted">
          Trading day
          <select
            value={selectedDay}
            onChange={(event) =>
              router.push(`/app/reviews?lens=daily&day=${encodeURIComponent(event.target.value)}`)
            }
            className="min-h-11 w-full rounded-lg border border-line bg-surface px-3 text-sm text-text sm:w-auto"
          >
            {options.map((day) => (
              <option key={day} value={day}>
                {day}
              </option>
            ))}
          </select>
        </label>
        {showButton && (
          <button
            type="button"
            onClick={() => void job.start({ day: selectedDay })}
            disabled={running}
            aria-busy={running}
            className="min-h-11 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-background disabled:cursor-wait disabled:opacity-60"
          >
            {saved || job.note
              ? `Regenerate debrief for ${selectedDay}`
              : `Generate debrief for ${selectedDay}`}
          </button>
        )}
      </div>

      {!aiAvailable && (
        <p className="mt-4 text-sm text-muted">
          AI reviews are unavailable right now. Saved debriefs are still shown.
        </p>
      )}
      {running && (
        <p role="status" className="mt-4 text-sm text-muted">
          Writing the debrief for this day. Anything already saved stays here until it is ready.
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
            title="Day in review"
            sample={`${note.period} · ${note.reviewed_trades} trades reviewed`}
            content={note.content_md}
            confidence={sampleConfidence(note.reviewed_trades)}
            limitation={note.reviewed_trades < 5 ? SMALL_SAMPLE_LIMITATION : undefined}
          />
          <Link
            href={`/app/journal?from=${note.period}&to=${note.period}`}
            className="mt-4 inline-flex min-h-11 items-center text-sm text-accent hover:underline"
          >
            Open these trades in the Journal
          </Link>
        </>
      ) : (
        <p className="mt-6 text-sm text-muted">No debrief is saved for this day yet.</p>
      )}
    </div>
  );
}
