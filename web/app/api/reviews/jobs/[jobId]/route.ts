import { NextResponse } from "next/server";

import { fetchReviewJob } from "@/lib/app/reviews";
import {
  authorizeReviewsRelay,
  REVIEWS_NO_STORE,
  reviewsRelayFailure,
} from "@/lib/app/reviews-relay";

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
  const auth = await authorizeReviewsRelay(request);
  if (auth instanceof NextResponse) return auth;

  const jobId = parseJobId((await params).jobId);
  if (jobId === null) {
    return NextResponse.json({ ok: false }, { status: 404, headers: REVIEWS_NO_STORE });
  }

  try {
    const job = await fetchReviewJob(auth.token, jobId);
    return NextResponse.json(job, { status: 200, headers: REVIEWS_NO_STORE });
  } catch (error) {
    return reviewsRelayFailure(error);
  }
}
