import "server-only";

import { NextResponse } from "next/server";

import type { ApiError } from "@/lib/api/client";
import { STRATEGY_NO_STORE } from "@/lib/app/strategy-relay";

/**
 * Turn a failed Strategy API call into the relay's response.
 *
 * The backend's status is forwarded unchanged — the editor branches on it
 * (409 keeps the trader's text, 422 marks a field). Its body is NOT: only
 * the fixed shapes this feature defines cross to the browser, so an
 * unexpected upstream message (which can carry internal detail) never does.
 *
 *   409  {detail: "stale_profile" | "no_profile" | "rules_full"}
 *   422  {detail: [{field, problem}, ...]}  — field names and codes only
 *
 * Anything that is not an `ApiError` is a 502 with no detail at all.
 */

const CONFLICT_CODES = new Set(["stale_profile", "no_profile", "rules_full"]);

function safeDetail(status: number, body: unknown): unknown {
  const detail = (body as { detail?: unknown } | null | undefined)?.detail;
  if (status === 409 && typeof detail === "string" && CONFLICT_CODES.has(detail)) {
    return detail;
  }
  if (status === 422 && Array.isArray(detail)) {
    const problems = detail.flatMap((item) => {
      const field = (item as { field?: unknown })?.field;
      const problem = (item as { problem?: unknown })?.problem;
      return typeof field === "string" && typeof problem === "string"
        ? [{ field, problem }]
        : [];
    });
    return problems.length ? problems : undefined;
  }
  return undefined;
}

export function relayFailure(err: unknown, apiError: typeof ApiError): NextResponse {
  if (err instanceof apiError) {
    const detail = safeDetail(err.status, err.body);
    return NextResponse.json(
      detail === undefined ? { ok: false } : { ok: false, detail },
      { status: err.status, headers: STRATEGY_NO_STORE },
    );
  }
  return NextResponse.json({ ok: false }, { status: 502, headers: STRATEGY_NO_STORE });
}
