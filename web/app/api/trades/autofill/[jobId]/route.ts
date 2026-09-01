import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/client";
import { fetchTradeAutofillJob } from "@/lib/app/trade-autofill";
import {
  authorizeTradeAutofillRelay,
  AUTOFILL_NO_STORE,
} from "@/lib/app/trade-autofill-relay";

/**
 * `GET /api/trades/autofill/{jobId}` — poll one autofill job (Task D2).
 *
 * Foreign and missing jobs are identical 404s backend-side; this relay does
 * not add a second check that could disagree with that.
 */

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
  const auth = await authorizeTradeAutofillRelay(request);
  if (auth instanceof NextResponse) return auth;

  const jobId = parseJobId((await params).jobId);
  if (jobId === null) {
    return NextResponse.json({ ok: false }, { status: 404, headers: AUTOFILL_NO_STORE });
  }

  try {
    const job = await fetchTradeAutofillJob(auth.token, jobId);
    return NextResponse.json(job, { status: 200, headers: AUTOFILL_NO_STORE });
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json({ ok: false }, { status: err.status, headers: AUTOFILL_NO_STORE });
    }
    return NextResponse.json({ ok: false }, { status: 502, headers: AUTOFILL_NO_STORE });
  }
}
