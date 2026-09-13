import "server-only";

import { NextResponse } from "next/server";

import type { ApiError } from "@/lib/api/client";
import { optionalEnv } from "@/lib/env";
import { appLayoutRedirect, authenticateSessionToken, sessionTokenFrom } from "@/lib/auth/session";
import { isSameOriginRequest } from "@/lib/security/redirect";

/**
 * Authorization and failure mapping for the Settings relays.
 *
 * The same fail-shut CSRF/session/eligibility check the Strategy and Partner
 * relays use. Two of these routes erase data, so a misconfigured
 * `SITE_ORIGIN` refuses BEFORE the session lookup: whether a deployment can
 * be driven from another origin must not depend on whether the caller happens
 * to hold a valid cookie.
 */

export const SETTINGS_NO_STORE = {
  "Cache-Control": "no-store, private",
  "Referrer-Policy": "no-referrer",
};

/** The largest request the import relay will read — the API's own body cap. */
export const MAX_IMPORT_REQUEST_BYTES = 1_048_576;

export async function authorizeSettingsRelay(
  request: Request,
): Promise<{ token: string } | NextResponse> {
  const siteOrigin = optionalEnv("SITE_ORIGIN");
  if (!siteOrigin || !isSameOriginRequest(request.headers, siteOrigin)) {
    return NextResponse.json({ ok: false }, { status: 403, headers: SETTINGS_NO_STORE });
  }
  const token = sessionTokenFrom(request);
  const user = token ? await authenticateSessionToken(token) : null;
  if (!token || !user) {
    return NextResponse.json({ ok: false }, { status: 401, headers: SETTINGS_NO_STORE });
  }
  // Authorization, not navigation: an ineligible account can call these
  // routes directly without ever rendering the page.
  if (appLayoutRedirect(user)) {
    return NextResponse.json({ ok: false }, { status: 403, headers: SETTINGS_NO_STORE });
  }
  return { token };
}

/**
 * Turn a failed Settings API call into the relay's response.
 *
 * The backend's status is forwarded unchanged. Its body is not:
 *
 *   422  {detail: [{field, problem}, ...]} — field names and codes only
 *   503  {detail: "screenshot_cleanup_failed", unresolvable: boolean}
 *
 * The cleanup 503 crosses as a fixed code plus one boolean — whether retrying
 * can help — never counts, keys or paths. Everything else is `{ok: false}`
 * with the backend's status; a non-`ApiError` fault is a 502.
 */
export function settingsRelayFailure(err: unknown, apiError: typeof ApiError): NextResponse {
  if (!(err instanceof apiError)) {
    return NextResponse.json({ ok: false }, { status: 502, headers: SETTINGS_NO_STORE });
  }
  const detail = (err.body as { detail?: unknown } | null | undefined)?.detail;

  if (err.status === 422 && Array.isArray(detail)) {
    const problems = detail.flatMap((item) => {
      const field = (item as { field?: unknown })?.field;
      const problem = (item as { problem?: unknown })?.problem;
      return typeof field === "string" && typeof problem === "string" ? [{ field, problem }] : [];
    });
    return NextResponse.json(problems.length ? { ok: false, detail: problems } : { ok: false }, {
      status: 422,
      headers: SETTINGS_NO_STORE,
    });
  }

  const cleanup = detail as { error?: unknown; unresolvable?: unknown } | null | undefined;
  if (err.status === 503 && cleanup?.error === "screenshot_cleanup_failed") {
    return NextResponse.json(
      {
        ok: false,
        detail: "screenshot_cleanup_failed",
        // An unreadable count is treated as retryable — the weaker claim.
        unresolvable: typeof cleanup.unresolvable === "number" && cleanup.unresolvable > 0,
      },
      { status: 503, headers: SETTINGS_NO_STORE },
    );
  }

  return NextResponse.json({ ok: false }, { status: err.status, headers: SETTINGS_NO_STORE });
}
