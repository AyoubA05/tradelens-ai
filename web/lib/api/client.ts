import "server-only";

import { signatureHeader } from "@/lib/api/sign";
import { requireEnv } from "@/lib/env";

/**
 * The only way the website talks to the FastAPI backend.
 *
 * Server-only, deliberately: the service secret must never reach a bundle, and
 * the backend emits no CORS headers, so a browser could not call it anyway.
 * Both facts are load-bearing and neither should be "fixed".
 *
 * The session token is forwarded so the backend can resolve the user itself.
 * Nothing here tells it which account to act on — that would defeat the point.
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
      "X-TL-Session": sessionToken,
    },
    body: body === "" ? undefined : body,
    cache: "no-store",
  });

  if (!response.ok) throw new ApiError(response.status);
  return (await response.json()) as T;
}
