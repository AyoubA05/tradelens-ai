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
  constructor(readonly status: number) {
    super(`api request failed with status ${status}`);
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

  if (!response.ok) throw new ApiError(response.status);
  return (await response.json()) as T;
}
