import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/client";
import { fetchAnalytics } from "@/lib/app/analytics";
import {
  ANALYTICS_NO_STORE,
  authorizeAnalyticsRelay,
} from "@/lib/app/analytics-relay";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const auth = await authorizeAnalyticsRelay(request);
  if (auth instanceof NextResponse) return auth;

  const params = new URL(request.url).searchParams;

  try {
    const payload = await fetchAnalytics(auth.token, {
      from: params.get("from") ?? "",
      to: params.get("to") ?? "",
      asset: params.get("asset") ?? undefined,
      session: params.get("session") ?? undefined,
      strategy: params.get("strategy") ?? undefined,
    });
    return NextResponse.json(payload, { status: 200, headers: ANALYTICS_NO_STORE });
  } catch (error) {
    if (error instanceof ApiError) {
      // 422 is the only body worth forwarding: the period and filter
      // refusals carry an actionable sentence ("'to' must not be before
      // 'from'") that the status code alone cannot say. Every other status
      // keeps the opaque shape so nothing about the backend's own state
      // crosses to the browser.
      if (error.status === 422) {
        const body = error.body;
        const detail =
          typeof body === "object" &&
          body !== null &&
          "detail" in body &&
          typeof (body as { detail: unknown }).detail === "string"
            ? (body as { detail: string }).detail
            : undefined;
        return NextResponse.json(
          { ok: false, detail },
          { status: 422, headers: ANALYTICS_NO_STORE },
        );
      }
      return NextResponse.json(
        { ok: false },
        { status: error.status, headers: ANALYTICS_NO_STORE },
      );
    }
    // Anything that is not an `ApiError` never reached the backend, or came
    // back unreadable. It is a gateway fault and nothing about it — host,
    // address, stack — crosses to the browser.
    return NextResponse.json({ ok: false }, { status: 502, headers: ANALYTICS_NO_STORE });
  }
}
