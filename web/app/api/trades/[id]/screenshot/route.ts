import { NextResponse } from "next/server";

import { optionalEnv } from "@/lib/env";
import {
  appLayoutRedirect,
  authenticateSessionToken,
  sessionTokenFrom,
} from "@/lib/auth/session";
import { isSameOriginRequest } from "@/lib/security/redirect";
import { ApiError } from "@/lib/api/client";
import {
  abandonScreenshot,
  finalizeScreenshot,
  ingestScreenshotUrl,
  presignScreenshot,
} from "@/lib/app/new-trade-create";
import {
  ACCEPTED_SCREENSHOT_TYPES,
  type ScreenshotContentType,
} from "@/lib/app/screenshot-upload";

/**
 * The one bridge the screenshot upload island has to FastAPI's three
 * screenshot endpoints.
 *
 * Same security shape as `app/api/trades/[id]/route.ts` and
 * `app/api/trades/create/route.ts`: fail-shut same-origin CSRF, the session
 * resolved from the cookie and never from the body, the app-eligibility
 * gate enforced here because this route can be called directly, `no-store`,
 * and the backend's own status forwarded faithfully.
 *
 * One handler for all three steps rather than three files, because they
 * share one authorization and one trade-id parse and differ only in which
 * upstream call they make. `action` is routing, not authorization — nothing
 * a caller sends here decides who they are.
 *
 * The `key` is forwarded exactly as the browser returned it. It is a CLAIM,
 * and every upstream handler re-derives this owner's own quarantine prefix
 * and refuses anything outside it (design decision #2). This relay must not
 * grow a second, weaker copy of that check: a partial one here would be the
 * thing people trusted instead.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = {
  "Cache-Control": "no-store, private",
  "Referrer-Policy": "no-referrer",
};

/** The backend's own user-facing message, when it sent one. */
function detailFrom(body: unknown): string | undefined {
  if (typeof body === "object" && body !== null && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
  }
  return undefined;
}

/** See `app/api/trades/[id]/route.ts` for why this is a strict digit test. */
function parseTradeId(raw: string): number | null {
  if (!/^[1-9]\d{0,15}$/.test(raw)) return null;
  return Number(raw);
}

async function authorize(request: Request): Promise<{ token: string } | NextResponse> {
  const siteOrigin = optionalEnv("SITE_ORIGIN");
  // Fail shut, matching the trade-detail and create relays' deliberate
  // divergence from the nine `app/api/auth/*` routes — see the
  // trade-detail route's comment. Do not loosen this to match them.
  if (!siteOrigin || !isSameOriginRequest(request.headers, siteOrigin)) {
    return NextResponse.json({ ok: false }, { status: 403, headers: NO_STORE });
  }
  const token = sessionTokenFrom(request);
  const user = token ? await authenticateSessionToken(token) : null;
  if (!token || !user) {
    return NextResponse.json({ ok: false }, { status: 401, headers: NO_STORE });
  }
  if (appLayoutRedirect(user)) {
    return NextResponse.json({ ok: false }, { status: 403, headers: NO_STORE });
  }
  return { token };
}

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize(request);
  if (auth instanceof NextResponse) return auth;

  const tradeId = parseTradeId((await params).id);
  if (tradeId === null) return NextResponse.json({ ok: false }, { status: 404, headers: NO_STORE });

  let body: { action?: unknown; content_type?: unknown; key?: unknown; url?: unknown };
  try {
    body = (await request.json()) as typeof body;
  } catch {
    return NextResponse.json({ ok: false }, { status: 400, headers: NO_STORE });
  }

  if (body.action === "ingest-url") {
    if (typeof body.url !== "string" || body.url === "") {
      return NextResponse.json({ ok: false }, { status: 400, headers: NO_STORE });
    }
    try {
      const screenshot = await ingestScreenshotUrl(auth.token, tradeId, body.url);
      return NextResponse.json(screenshot, { status: 201, headers: NO_STORE });
    } catch (err) {
      if (err instanceof ApiError) {
        // Unlike the file-upload actions below, a rejected URL must read as
        // a plain reason (global rule 3) — `url_ingest.UrlIngestError` and
        // `UploadRejected` already produce one stable, safe phrase apiece
        // (never a stack, a host, or an address), so forwarding it here is
        // the fix for the exact defect Phase 4's create relay had: dropping
        // `detail` and showing generic text instead.
        const detail = detailFrom(err.body);
        return NextResponse.json(
          { ok: false, ...(detail ? { detail } : {}) },
          { status: err.status, headers: NO_STORE },
        );
      }
      return NextResponse.json({ ok: false }, { status: 502, headers: NO_STORE });
    }
  }

  try {
    if (body.action === "presign") {
      // The enum is the backend's; checking it here only saves a round
      // trip on an obviously-wrong value, and the upstream 422 still
      // decides for anything this lets through.
      if (!ACCEPTED_SCREENSHOT_TYPES.includes(body.content_type as ScreenshotContentType)) {
        return NextResponse.json({ ok: false }, { status: 422, headers: NO_STORE });
      }
      const presigned = await presignScreenshot(
        auth.token,
        tradeId,
        body.content_type as ScreenshotContentType,
      );
      return NextResponse.json(presigned, { status: 200, headers: NO_STORE });
    }

    if (typeof body.key !== "string" || body.key === "") {
      return NextResponse.json({ ok: false }, { status: 400, headers: NO_STORE });
    }

    if (body.action === "finalize") {
      const screenshot = await finalizeScreenshot(auth.token, tradeId, body.key);
      return NextResponse.json(screenshot, { status: 201, headers: NO_STORE });
    }
    if (body.action === "abandon") {
      await abandonScreenshot(auth.token, tradeId, body.key);
      return new NextResponse(null, { status: 204, headers: NO_STORE });
    }
    return NextResponse.json({ ok: false }, { status: 400, headers: NO_STORE });
  } catch (err) {
    if (err instanceof ApiError) {
      // Forwarded as itself, deliberately. 422 (not a usable image) and 409
      // (the quarantine object is gone) are different situations with
      // different next steps for a trader, and the client branches on
      // exactly these — flattening them into one status would make the
      // difference unrecoverable here.
      return NextResponse.json({ ok: false }, { status: err.status, headers: NO_STORE });
    }
    return NextResponse.json({ ok: false }, { status: 502, headers: NO_STORE });
  }
}
