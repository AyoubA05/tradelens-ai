import "server-only";

import { callApi } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

/**
 * The analytics payload, typed from the generated OpenAPI schema so the shape
 * cannot drift from what the backend actually returns.
 *
 * One request for all four lenses, by design: they answer four questions
 * about the same filtered sample, and four requests would give four chances
 * for one of them to be computed over a slightly different frame.
 */
export type AnalyticsResponse = components["schemas"]["AnalyticsResponse"];
export type MetricValue = components["schemas"]["MetricValue"];

/**
 * The period and filters an analytics read is measured over.
 *
 * No owner field, and there never may be one: the API derives the account
 * from the session row, and a caller that could name a user would defeat
 * that.
 */
export type AnalyticsParams = {
  from: string;
  to: string;
  asset?: string;
  session?: string;
  strategy?: string;
};

/**
 * Fetch the analytics payload for the authenticated owner.
 *
 * Server-only. The session token is forwarded to `callApi`, which hashes it
 * into the domain-separated handle — the raw credential never leaves Next.js.
 *
 * Errors are not caught. A page of zeros is indistinguishable from a trader
 * who had a flat month, so a failed fetch must reach the caller rather than
 * be rendered as data.
 */
export async function fetchAnalytics(
  sessionToken: string,
  params: AnalyticsParams,
): Promise<AnalyticsResponse> {
  const query = new URLSearchParams({ from: params.from, to: params.to });
  // Absent and empty are the same thing here — "no filter" — and an empty
  // string forwarded as a value would be a filter the backend must reject.
  if (params.asset) query.set("asset", params.asset);
  if (params.session) query.set("session", params.session);
  if (params.strategy) query.set("strategy", params.strategy);
  return callApi<AnalyticsResponse>("/v1/analytics", sessionToken, {
    query: query.toString(),
  });
}
