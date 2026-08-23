import "server-only";

import { createHash } from "node:crypto";
import { signatureHeader } from "@/lib/api/sign";
import { WEBSITE_DOMAIN } from "@/lib/auth/domains";
import { requireEnv } from "@/lib/env";

/**
 * The only way the website talks to the FastAPI backend.
 *
 * Server-only, deliberately: the service secret must never reach a bundle, and
 * the backend emits no CORS headers, so a browser could not call it anyway.
 * Both facts are load-bearing and neither should be "fixed".
 *
 * A domain-separated hash of the session token is forwarded so the backend
 * can resolve and revalidate the database row itself. The raw HttpOnly-cookie
 * bearer never crosses into the API service, its traces, or its infrastructure.
 * Nothing here tells the API which account to act on — that would defeat the
 * independent database check.
 */
export class ApiError extends Error {
  /**
   * `status` is the backend's own status, never a substitute — the whole
   * error chain reads it: 404 becomes `notFound()` (the existence
   * non-disclosure property), 409 becomes the conflict view, 503 becomes
   * "nothing was deleted." `api-client.test.ts` pins that it is the real
   * status; downstream tests construct `ApiError` by hand and so can only
   * prove how a caller reacts to a status, never that the status is real.
   *
   * `body` is the parsed error payload when there was one. It is optional
   * and advisory: callers branch on `status`, and read `body` only where
   * the backend deliberately says more than the status can (the delete
   * 503's retryable/unresolvable split).
   */
  constructor(
    readonly status: number,
    readonly body?: unknown,
  ) {
    super(`api request failed with status ${status}`);
  }
}

/**
 * Read an error response's JSON body, or nothing.
 *
 * A missing or unparseable body is not itself a failure — the status is
 * what callers branch on — so this never throws over one and never lets a
 * parse error masquerade as the original fault.
 */
async function readErrorBody(response: Response): Promise<unknown> {
  if (typeof response.json !== "function") return undefined;
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}

export async function callApi<T>(
  path: string,
  sessionToken: string,
  init: { method?: string; query?: string; body?: unknown } = {},
): Promise<T> {
  const method = init.method ?? "GET";
  const query = init.query ?? "";
  const body = init.body === undefined ? "" : JSON.stringify(init.body);
  const base = requireEnv("TL_API_ORIGIN");
  const url = query ? `${base}${path}?${query}` : `${base}${path}`;
  const sessionHandle = createHash("sha256")
    .update(WEBSITE_DOMAIN + sessionToken, "utf8")
    .digest("hex");

  const response = await fetch(url, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-TL-Signature": signatureHeader(
        requireEnv("TL_SERVICE_SECRET"),
        method,
        path,
        query,
        body,
      ),
      "X-TL-Session-Handle": sessionHandle,
    },
    body: body === "" ? undefined : body,
    cache: "no-store",
  });

  if (!response.ok) throw new ApiError(response.status, await readErrorBody(response));
  // 204 (the trade-delete endpoint's success response) carries no body, and
  // `.json()` on an empty stream throws rather than returning anything a
  // caller could await — this is the first caller in the codebase that hits
  // a 204, so nothing exercised the gap until now.
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
