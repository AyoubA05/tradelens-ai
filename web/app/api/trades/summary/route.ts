import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/client";
import {
  enqueueTradeSummaryRequest,
  type TradeSummaryJobRequest,
} from "@/lib/app/trades";
import {
  authorizeTradeSummaryRelay,
  SUMMARY_NO_STORE,
} from "@/lib/app/trade-summary-relay";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const auth = await authorizeTradeSummaryRelay(request);
  if (auth instanceof NextResponse) return auth;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { ok: false },
      { status: 400, headers: SUMMARY_NO_STORE },
    );
  }

  try {
    const accepted = await enqueueTradeSummaryRequest(
      auth.token,
      body as TradeSummaryJobRequest,
    );
    return NextResponse.json(accepted, {
      status: 202,
      headers: SUMMARY_NO_STORE,
    });
  } catch (error) {
    if (error instanceof ApiError) {
      // 429 carries a backend message the trader needs (limit reached, when it
      // resets, existing summaries still work) — everything else keeps the
      // opaque `{ ok: false }` shape so no other backend detail leaks through.
      if (error.status === 429) {
        const detail =
          typeof error.body === "object" &&
          error.body !== null &&
          "detail" in error.body &&
          typeof (error.body as { detail: unknown }).detail === "string"
            ? (error.body as { detail: string }).detail
            : undefined;
        return NextResponse.json(
          { ok: false, error: "rate_limited", detail },
          { status: 429, headers: SUMMARY_NO_STORE },
        );
      }
      return NextResponse.json(
        { ok: false },
        { status: error.status, headers: SUMMARY_NO_STORE },
      );
    }
    return NextResponse.json(
      { ok: false },
      { status: 502, headers: SUMMARY_NO_STORE },
    );
  }
}
