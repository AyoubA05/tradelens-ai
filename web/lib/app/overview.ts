import "server-only";

import { callApi } from "@/lib/api/client";
import { periodToParams, type Period } from "@/lib/app/period";
import type { components } from "@/lib/api/schema";

/**
 * The Overview payload, typed from the generated OpenAPI schema so the shape
 * cannot drift from what the backend actually returns.
 */
export type OverviewResponse = components["schemas"]["OverviewResponse"];

/**
 * Fetch the Overview for the authenticated owner.
 *
 * Server-only. The session token is forwarded to `callApi`, which hashes it
 * into the domain-separated handle — the raw credential never leaves Next.js.
 * Nothing here names an account: the API derives the owner from the session
 * row, and a caller that could pass a user id would defeat that.
 *
 * Errors are not caught. An Overview of zeros is indistinguishable from a
 * trader who had a flat month, so a failed fetch must reach the route's error
 * boundary rather than be rendered as data.
 */
export async function fetchOverview(
  sessionToken: string,
  period: Period,
): Promise<OverviewResponse> {
  return callApi<OverviewResponse>("/v1/overview", sessionToken, {
    query: periodToParams(period).toString(),
  });
}
