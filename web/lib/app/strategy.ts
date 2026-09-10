import "server-only";

import { callApi } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

/**
 * The Strategy Profile's server-only bridge to `/v1/strategy`.
 *
 * `callApi` carries the service secret and cannot reach a bundle, so the
 * page (a Server Component) calls `fetchStrategy` directly and the editor's
 * writes go through the relays under `app/api/strategy/`.
 *
 * The profile is an owner-singleton: nothing here takes an id, and nothing
 * here decides a version. `expected_revision` is whatever the server last
 * returned, echoed back so a stale tab is refused rather than merged.
 */
export type StrategyResponse = components["schemas"]["StrategyResponse"];
export type StrategyWrite = components["schemas"]["StrategyWrite"];
export type StrategyInsightRequest = components["schemas"]["StrategyInsightRequest"];
export type StrategyFields = components["schemas"]["StrategyFields"];

export async function fetchStrategy(sessionToken: string): Promise<StrategyResponse> {
  return callApi<StrategyResponse>("/v1/strategy", sessionToken);
}

export async function saveStrategy(
  sessionToken: string,
  body: StrategyWrite,
): Promise<StrategyResponse> {
  return callApi<StrategyResponse>("/v1/strategy", sessionToken, { method: "PUT", body });
}

export async function skipStrategy(sessionToken: string): Promise<StrategyResponse> {
  return callApi<StrategyResponse>("/v1/strategy/skip", sessionToken, {
    method: "POST",
    body: {},
  });
}

export async function appendStrategyInsight(
  sessionToken: string,
  body: StrategyInsightRequest,
): Promise<StrategyResponse> {
  return callApi<StrategyResponse>("/v1/strategy/insights", sessionToken, {
    method: "POST",
    body,
  });
}
