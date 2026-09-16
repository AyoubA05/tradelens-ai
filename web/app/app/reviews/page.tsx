import { headers } from "next/headers";
import { redirect } from "next/navigation";

import {
  appLayoutRedirect,
  authenticateSessionToken,
  sessionTokenFromCookieHeader,
} from "@/lib/auth/session";
import { ApiError } from "@/lib/api/client";
import { fetchReviews, type ReviewsResponse } from "@/lib/app/reviews";
import { LensTabs, REVIEW_LENSES, reviewLensFrom } from "@/components/app/reviews/lens-tabs";
import { PatternsLens } from "@/components/app/reviews/patterns-lens";
import { WeeklyLens } from "@/components/app/reviews/weekly-lens";
import { DailyLens } from "@/components/app/reviews/daily-lens";
import { ErrorState } from "@/components/app/states/error-state";

export const dynamic = "force-dynamic";

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function isoParam(value: string | string[] | undefined): string | undefined {
  return typeof value === "string" && ISO_DATE.test(value) ? value : undefined;
}

/**
 * AI Reviews — Patterns, Weekly Recap, Daily Debrief.
 *
 * A Server Component that repeats the layout's authorization before fetching.
 * Rendering, prefetching or refreshing this page never starts a paid review:
 * generation happens only from an explicit click in a lens.
 *
 * A failed load renders an error and NO controls.
 */
export default async function ReviewsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const token = sessionTokenFromCookieHeader((await headers()).get("cookie"));
  if (!token) redirect("/login");
  const user = await authenticateSessionToken(token);
  if (!user) redirect("/login");
  const redirectTo = appLayoutRedirect(user);
  if (redirectTo) redirect(redirectTo);

  const raw = await searchParams;
  const lens = reviewLensFrom(typeof raw.lens === "string" ? raw.lens : undefined);
  const week = isoParam(raw.week);
  const day = isoParam(raw.day);

  let data: ReviewsResponse | null = null;
  let selectedWeek: string | null = week ?? null;
  let selectedDay: string | null = day ?? null;
  try {
    try {
      data = await fetchReviews(token, { ...(week ? { week } : {}), ...(day ? { day } : {}) });
    } catch (error) {
      // An ISO-shaped but invalid period (`?week=2026-09-09`, `?day=2026-02-30`)
      // is a 422. Drop the supplied period and read again, so the lens opens on
      // the newest period instead of an error. Any other failure, or a failure
      // of this re-read, is the error state.
      if (!(error instanceof ApiError && error.status === 422 && (week || day))) throw error;
      selectedWeek = null;
      selectedDay = null;
      data = await fetchReviews(token, {});
    }
    // Opening a lens with no period chosen reads the newest one (the API lists
    // them newest first). This is a second READ for its saved note — never a
    // generate.
    if (lens === "weekly" && !selectedWeek && data.weeks[0]) {
      selectedWeek = data.weeks[0];
      data = await fetchReviews(token, {
        week: selectedWeek,
        ...(selectedDay ? { day: selectedDay } : {}),
      });
    }
    if (lens === "daily" && !selectedDay && data.days[0]) {
      selectedDay = data.days[0];
      data = await fetchReviews(token, {
        day: selectedDay,
        ...(selectedWeek ? { week: selectedWeek } : {}),
      });
    }
  } catch {
    // Not surfaced: an upstream message can carry internal detail.
    data = null;
  }

  const question = REVIEW_LENSES.find((item) => item.id === lens)!.question;

  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-bold">AI Reviews</h1>
      <p className="mt-2 text-muted">
        Evidence-backed reading of your own journal. Reflection only — never signals or advice.
      </p>

      {data === null ? (
        <div className="mt-8">
          <ErrorState
            title="AI Reviews did not load"
            description="This is a loading failure. Nothing in your journal or your saved reviews has changed."
          />
        </div>
      ) : (
        <>
          <LensTabs active={lens} />
          <p className="mt-4 text-sm text-muted">{question}</p>
          {lens === "patterns" && (
            <PatternsLens
              patterns={data.patterns}
              completeTrades={data.complete_trades}
              tradesForReview={data.trades_for_review}
            />
          )}
          {lens === "weekly" && (
            <WeeklyLens
              key={selectedWeek ?? "none"}
              weeks={data.weeks}
              selectedWeek={selectedWeek}
              saved={data.weekly ?? null}
              completeTrades={data.complete_trades}
              tradesForReview={data.trades_for_review}
              aiAvailable={data.ai_available}
            />
          )}
          {lens === "daily" && (
            <DailyLens
              key={selectedDay ?? "none"}
              days={data.days}
              selectedDay={selectedDay}
              saved={data.daily ?? null}
              aiAvailable={data.ai_available}
            />
          )}
        </>
      )}
    </div>
  );
}
