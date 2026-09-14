import { NextResponse } from "next/server";

import { enqueueWeeklyRecap } from "@/lib/app/reviews";
import {
  authorizeReviewsRelay,
  readJsonBody,
  REVIEWS_NO_STORE,
  reviewsRelayFailure,
} from "@/lib/app/reviews-relay";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const auth = await authorizeReviewsRelay(request);
  if (auth instanceof NextResponse) return auth;

  const parsed = await readJsonBody(request);
  if (!parsed) {
    return NextResponse.json({ ok: false }, { status: 400, headers: REVIEWS_NO_STORE });
  }

  try {
    const accepted = await enqueueWeeklyRecap(auth.token, parsed.body);
    return NextResponse.json(accepted, { status: 202, headers: REVIEWS_NO_STORE });
  } catch (error) {
    return reviewsRelayFailure(error);
  }
}
