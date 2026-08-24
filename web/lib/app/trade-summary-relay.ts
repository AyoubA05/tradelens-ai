import "server-only";

import { NextResponse } from "next/server";

import { optionalEnv } from "@/lib/env";
import {
  appLayoutRedirect,
  authenticateSessionToken,
  sessionTokenFrom,
} from "@/lib/auth/session";
import { isSameOriginRequest } from "@/lib/security/redirect";

export const SUMMARY_NO_STORE = {
  "Cache-Control": "no-store, private",
  "Referrer-Policy": "no-referrer",
};

export async function authorizeTradeSummaryRelay(
  request: Request,
): Promise<{ token: string } | NextResponse> {
  const siteOrigin = optionalEnv("SITE_ORIGIN");
  if (!siteOrigin || !isSameOriginRequest(request.headers, siteOrigin)) {
    return NextResponse.json(
      { ok: false },
      { status: 403, headers: SUMMARY_NO_STORE },
    );
  }
  const token = sessionTokenFrom(request);
  const user = token ? await authenticateSessionToken(token) : null;
  if (!token || !user) {
    return NextResponse.json(
      { ok: false },
      { status: 401, headers: SUMMARY_NO_STORE },
    );
  }
  if (appLayoutRedirect(user)) {
    return NextResponse.json(
      { ok: false },
      { status: 403, headers: SUMMARY_NO_STORE },
    );
  }
  return { token };
}
