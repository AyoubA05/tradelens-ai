import { NextResponse } from "next/server";

import { optionalEnv } from "@/lib/env";
import { SESSION_COOKIE, revokeWebsiteSession } from "@/lib/auth/login";
import { sessionTokenFromCookieHeader } from "@/lib/auth/session";
import { isSameOriginRequest } from "@/lib/security/redirect";
import { logAuthEvent } from "@/lib/security/responses";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Sign out. Revokes the row, then clears the cookie — in that order.
 *
 * Clearing the cookie alone is the defect this whole session design exists to
 * fix: it makes the browser forget a credential that is still perfectly valid
 * to anyone who kept a copy.
 */
export async function POST(request: Request) {
  const siteOrigin = optionalEnv("SITE_ORIGIN");
  if (siteOrigin && !isSameOriginRequest(request.headers, siteOrigin)) {
    return NextResponse.json({ ok: false }, { status: 403 });
  }
  const token = sessionTokenFromCookieHeader(request.headers.get("cookie"));
  const revoked = await revokeWebsiteSession(token);
  logAuthEvent("logout", revoked ? "success" : "invalid_token");

  const response = NextResponse.json({ ok: true }, { status: 200, headers: { "Cache-Control": "no-store, private" } });
  response.cookies.delete(SESSION_COOKIE);
  return response;
}
