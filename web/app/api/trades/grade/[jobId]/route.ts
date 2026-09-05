import { NextResponse } from "next/server";

import { fetchGradeJob } from "@/lib/app/trade-analysis";
import {
  analysisRelayError,
  ANALYSIS_NO_STORE,
  authorizeTradeAnalysisRelay,
  parseRelayId,
} from "@/lib/app/trade-analysis-relay";

/**
 * `GET /api/trades/grade/{jobId}` — poll one grade job.
 *
 * One route per kind, because the backend enforces the kind: a job of any
 * other kind is a 404 there. Collapsing the three into a single relay would
 * be the client-side half of the mistake that check exists to prevent —
 * reporting one kind's job as another's.
 *
 * Foreign and missing jobs are identical 404s backend-side; this relay adds
 * no second check that could disagree with that, and forwards no body.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const auth = await authorizeTradeAnalysisRelay(request);
  if (auth instanceof NextResponse) return auth;

  const jobId = parseRelayId((await params).jobId);
  if (jobId === null) {
    return NextResponse.json({ ok: false }, { status: 404, headers: ANALYSIS_NO_STORE });
  }

  try {
    const job = await fetchGradeJob(auth.token, jobId);
    return NextResponse.json(job, { status: 200, headers: ANALYSIS_NO_STORE });
  } catch (err) {
    return analysisRelayError(err);
  }
}
