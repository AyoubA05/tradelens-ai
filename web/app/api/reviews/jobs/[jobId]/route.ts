import { NextResponse } from "next/server";

import { fetchReviewJob } from "@/lib/app/reviews";
import {
  authorizeReviewsRelay,
  REVIEWS_NO_STORE,
  reviewsRelayFailure,
} from "@/lib/app/reviews-relay";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const REVIEW_OUT_OF_DATE = "This review is out of date. Generate it again.";

/**
 * Only one job error is ever shown to the trader: the fixed out-of-date
 * sentence on a superseded job. Every other status, and any other text, is
 * relayed as `error: null` — a stored job error is backend text.
 */
function relayableJob<T extends { status?: unknown; error?: unknown }>(job: T): T {
  const error =
    job.status === "superseded" && job.error === REVIEW_OUT_OF_DATE ? REVIEW_OUT_OF_DATE : null;
  return { ...job, error };
}

function parseJobId(raw: string): number | null {
  if (!/^[1-9]\d{0,15}$/.test(raw)) return null;
  return Number(raw);
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const auth = await authorizeReviewsRelay(request);
  if (auth instanceof NextResponse) return auth;

  const jobId = parseJobId((await params).jobId);
  if (jobId === null) {
    return NextResponse.json({ ok: false }, { status: 404, headers: REVIEWS_NO_STORE });
  }

  try {
    const job = await fetchReviewJob(auth.token, jobId);
    return NextResponse.json(relayableJob(job), { status: 200, headers: REVIEWS_NO_STORE });
  } catch (error) {
    return reviewsRelayFailure(error);
  }
}
