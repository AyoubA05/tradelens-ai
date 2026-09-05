import { NextResponse } from "next/server";

import { enqueueGrade } from "@/lib/app/trade-analysis";
import {
  analysisRelayError,
  ANALYSIS_NO_STORE,
  authorizeTradeAnalysisRelay,
  parseRelayId,
} from "@/lib/app/trade-analysis-relay";

/**
 * `POST /api/trades/{id}/grade` — queue the grade step for one trade.
 *
 * No body: this step reads the stored analysis, and which analysis that is
 * is not the caller's to choose. A trade with no analysis yet is a 409
 * whose `detail` says so, and that sentence is forwarded because it is the
 * one thing the status code cannot say.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorizeTradeAnalysisRelay(request);
  if (auth instanceof NextResponse) return auth;

  const tradeId = parseRelayId((await params).id);
  if (tradeId === null) {
    return NextResponse.json({ ok: false }, { status: 404, headers: ANALYSIS_NO_STORE });
  }

  try {
    const accepted = await enqueueGrade(auth.token, tradeId);
    return NextResponse.json(accepted, { status: 202, headers: ANALYSIS_NO_STORE });
  } catch (err) {
    return analysisRelayError(err);
  }
}
