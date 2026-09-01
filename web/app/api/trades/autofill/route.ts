import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/client";
import { enqueueTradeAutofill } from "@/lib/app/trade-autofill";
import {
  authorizeTradeAutofillRelay,
  AUTOFILL_NO_STORE,
} from "@/lib/app/trade-autofill-relay";

/**
 * `POST /api/trades/autofill` — enqueue one AI autofill job (Task D2).
 *
 * `screenshot_id` is the only input, and it names a screenshot the caller
 * must already own; ownership and the owner-scoped rate limit both live
 * service-side (design decisions #4 and #6). This relay's job is the
 * session token and the backend's status, nothing more.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const auth = await authorizeTradeAutofillRelay(request);
  if (auth instanceof NextResponse) return auth;

  let body: { screenshot_id?: unknown };
  try {
    body = (await request.json()) as typeof body;
  } catch {
    return NextResponse.json({ ok: false }, { status: 400, headers: AUTOFILL_NO_STORE });
  }
  const screenshotId = Number(body.screenshot_id);
  if (!Number.isInteger(screenshotId) || screenshotId <= 0) {
    return NextResponse.json({ ok: false }, { status: 400, headers: AUTOFILL_NO_STORE });
  }

  try {
    const accepted = await enqueueTradeAutofill(auth.token, screenshotId);
    return NextResponse.json(accepted, { status: 202, headers: AUTOFILL_NO_STORE });
  } catch (err) {
    if (err instanceof ApiError) {
      // 429 carries the backend's own cost-discipline message (design
      // decision #6) — the same "forward the one status whose body says
      // something actionable" rule the summary and create relays follow.
      if (err.status === 429) {
        const detail =
          typeof err.body === "object" &&
          err.body !== null &&
          "detail" in err.body &&
          typeof (err.body as { detail: unknown }).detail === "string"
            ? (err.body as { detail: string }).detail
            : undefined;
        return NextResponse.json(
          { ok: false, error: "rate_limited", detail },
          { status: 429, headers: AUTOFILL_NO_STORE },
        );
      }
      return NextResponse.json({ ok: false }, { status: err.status, headers: AUTOFILL_NO_STORE });
    }
    return NextResponse.json({ ok: false }, { status: 502, headers: AUTOFILL_NO_STORE });
  }
}
