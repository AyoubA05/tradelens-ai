import { NextResponse } from "next/server";

import { enqueueAnalysis, patchAnalysisLabels } from "@/lib/app/trade-analysis";
import type { AIAnalysisLabelPatch } from "@/lib/app/trade-analysis";
import {
  analysisRelayError,
  ANALYSIS_NO_STORE,
  authorizeTradeAnalysisRelay,
  parseRelayId,
} from "@/lib/app/trade-analysis-relay";

/**
 * `POST /api/trades/{id}/analysis` — queue AI analysis of one screenshot.
 * `PATCH /api/trades/{id}/analysis` — confirm, correct or release labels.
 *
 * `screenshot_id` names a screenshot the caller must already own; that the
 * screenshot belongs to this trade and to this owner is settled backend
 * side before anything billable is scheduled. This relay carries the
 * session token up and the backend's status back, nothing more.
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

  let body: { screenshot_id?: unknown };
  try {
    body = (await request.json()) as typeof body;
  } catch {
    return NextResponse.json({ ok: false }, { status: 400, headers: ANALYSIS_NO_STORE });
  }
  // `Number("abc")` is NaN and `Number(" 1")` is 1, so the guard is an
  // integer test on the parsed value, not a truthiness check on the input.
  const screenshotId =
    typeof body.screenshot_id === "number" ? body.screenshot_id : Number.NaN;
  if (!Number.isInteger(screenshotId) || screenshotId <= 0) {
    return NextResponse.json({ ok: false }, { status: 400, headers: ANALYSIS_NO_STORE });
  }

  try {
    const accepted = await enqueueAnalysis(auth.token, tradeId, screenshotId);
    return NextResponse.json(accepted, { status: 202, headers: ANALYSIS_NO_STORE });
  } catch (err) {
    return analysisRelayError(err);
  }
}

export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorizeTradeAnalysisRelay(request);
  if (auth instanceof NextResponse) return auth;

  const tradeId = parseRelayId((await params).id);
  if (tradeId === null) {
    return NextResponse.json({ ok: false }, { status: 404, headers: ANALYSIS_NO_STORE });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false }, { status: 400, headers: ANALYSIS_NO_STORE });
  }
  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    return NextResponse.json({ ok: false }, { status: 400, headers: ANALYSIS_NO_STORE });
  }

  // The patch body is forwarded as it arrived. Its allowlist is
  // `extra="forbid"` on the backend schema, which turns an unexpected key
  // into a 422 there — re-deriving that allowlist here would give the two a
  // way to drift, and the stricter of the two is already the server's.
  try {
    const labels = await patchAnalysisLabels(
      auth.token,
      tradeId,
      body as Partial<AIAnalysisLabelPatch>,
    );
    return NextResponse.json(labels, { status: 200, headers: ANALYSIS_NO_STORE });
  } catch (err) {
    return analysisRelayError(err);
  }
}
