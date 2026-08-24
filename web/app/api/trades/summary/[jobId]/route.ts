import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/client";
import { fetchTradeSummaryJob } from "@/lib/app/trades";
import {
  authorizeTradeSummaryRelay,
  SUMMARY_NO_STORE,
} from "@/lib/app/trade-summary-relay";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function parseJobId(raw: string): number | null {
  if (!/^[1-9]\d{0,15}$/.test(raw)) return null;
  return Number(raw);
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const auth = await authorizeTradeSummaryRelay(request);
  if (auth instanceof NextResponse) return auth;

  const jobId = parseJobId((await params).jobId);
  if (jobId === null) {
    return NextResponse.json(
      { ok: false },
      { status: 404, headers: SUMMARY_NO_STORE },
    );
  }

  try {
    const job = await fetchTradeSummaryJob(auth.token, jobId);
    return NextResponse.json(job, { status: 200, headers: SUMMARY_NO_STORE });
  } catch (error) {
    if (error instanceof ApiError) {
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
