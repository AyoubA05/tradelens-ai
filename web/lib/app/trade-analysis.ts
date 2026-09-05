import "server-only";

import { callApi } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

/**
 * The per-trade AI review (Task D1): server-only bridges to the Phase 5
 * FastAPI routes.
 *
 * `callApi` carries `TL_SERVICE_SECRET` and is `server-only`, so a Client
 * Component reaches these only through the relay route handlers under
 * `app/api/trades/`. Nothing here re-implements a backend guarantee:
 * ownership, the owner-scoped ceilings, the confirmation lock and the
 * monotonic write guard all live service-side.
 *
 * Each job kind polls ONLY its own route. That is the backend's rule, not a
 * convention — a job of another kind is a 404 there — and the three
 * separate functions below are what keeps a caller from crossing them.
 */
export type AIAnalysisJobRequest = components["schemas"]["AIAnalysisJobRequest"];
export type AIJobAccepted = components["schemas"]["AIJobAccepted"];
export type AIJobStatus = components["schemas"]["AIJobStatus"];
export type AIAnalysisDetail = components["schemas"]["AIAnalysisDetail"];
export type AIAnalysisLabels = components["schemas"]["AIAnalysisLabels"];
export type AIAnalysisLabelPatch = components["schemas"]["AIAnalysisLabelPatch"];

export async function enqueueAnalysis(
  sessionToken: string,
  tradeId: number,
  screenshotId: number,
): Promise<AIJobAccepted> {
  const body: AIAnalysisJobRequest = { screenshot_id: screenshotId };
  return callApi<AIJobAccepted>(`/v1/trades/${tradeId}/analysis`, sessionToken, {
    method: "POST",
    body,
  });
}

/**
 * The journal and grade jobs take no body: both read the stored analysis,
 * and which analysis that is is not the caller's to choose.
 */
export async function enqueueJournal(
  sessionToken: string,
  tradeId: number,
): Promise<AIJobAccepted> {
  return callApi<AIJobAccepted>(`/v1/trades/${tradeId}/journal`, sessionToken, {
    method: "POST",
  });
}

export async function enqueueGrade(
  sessionToken: string,
  tradeId: number,
): Promise<AIJobAccepted> {
  return callApi<AIJobAccepted>(`/v1/trades/${tradeId}/grade`, sessionToken, {
    method: "POST",
  });
}

export async function fetchAnalysisJob(
  sessionToken: string,
  jobId: number,
): Promise<AIJobStatus> {
  return callApi<AIJobStatus>(`/v1/trades/analysis/${jobId}`, sessionToken);
}

export async function fetchJournalJob(
  sessionToken: string,
  jobId: number,
): Promise<AIJobStatus> {
  return callApi<AIJobStatus>(`/v1/trades/journal/${jobId}`, sessionToken);
}

export async function fetchGradeJob(
  sessionToken: string,
  jobId: number,
): Promise<AIJobStatus> {
  return callApi<AIJobStatus>(`/v1/trades/grade/${jobId}`, sessionToken);
}

/**
 * The stored review for one trade. A trade with no analysis is a 404 there,
 * never an empty object — "not run" and "run, and it found nothing" are
 * different states and the panel renders them differently, so the caller
 * turns that 404 into `null` rather than this function inventing a shape.
 */
export async function fetchAnalysis(
  sessionToken: string,
  tradeId: number,
): Promise<AIAnalysisDetail> {
  return callApi<AIAnalysisDetail>(`/v1/trades/${tradeId}/analysis`, sessionToken);
}

export async function patchAnalysisLabels(
  sessionToken: string,
  tradeId: number,
  patch: Partial<AIAnalysisLabelPatch>,
): Promise<AIAnalysisLabels> {
  return callApi<AIAnalysisLabels>(`/v1/trades/${tradeId}/analysis`, sessionToken, {
    method: "PATCH",
    body: patch,
  });
}
