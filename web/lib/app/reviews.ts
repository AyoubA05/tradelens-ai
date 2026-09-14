import "server-only";

import { callApi } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

/**
 * The AI Reviews page's server-only bridge to `/v1/reviews`.
 *
 * `callApi` carries the service secret, so the page (a Server Component) calls
 * `fetchReviews` directly and generation goes through the relays under
 * `app/api/reviews/`. Nothing here names an owner or a review id: the owner is
 * the session, and a generate body carries only its period (FastAPI validates
 * it strictly).
 */
export type ReviewsResponse = components["schemas"]["ReviewsResponse"];
export type ReviewJobAccepted = components["schemas"]["ReviewJobAccepted"];
export type ReviewJobStatus = components["schemas"]["ReviewJobStatus"];
export type SavedNote = components["schemas"]["SavedNote"];
export type PeriodStats = components["schemas"]["PeriodStats"];
export type PatternInsight = components["schemas"]["PatternInsight"];

export async function fetchReviews(
  sessionToken: string,
  { week, day }: { week?: string; day?: string } = {},
): Promise<ReviewsResponse> {
  const params = new URLSearchParams();
  if (week) params.set("week", week);
  if (day) params.set("day", day);
  const query = params.toString();
  return callApi<ReviewsResponse>(`/v1/reviews${query ? `?${query}` : ""}`, sessionToken);
}

export async function enqueueWeeklyRecap(
  sessionToken: string,
  body: unknown,
): Promise<ReviewJobAccepted> {
  return callApi<ReviewJobAccepted>("/v1/reviews/weekly", sessionToken, { method: "POST", body });
}

export async function enqueueDailyDebrief(
  sessionToken: string,
  body: unknown,
): Promise<ReviewJobAccepted> {
  return callApi<ReviewJobAccepted>("/v1/reviews/daily", sessionToken, { method: "POST", body });
}

export async function fetchReviewJob(sessionToken: string, jobId: number): Promise<ReviewJobStatus> {
  return callApi<ReviewJobStatus>(`/v1/reviews/jobs/${jobId}`, sessionToken);
}
