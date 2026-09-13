import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/client";
import { SESSION_COOKIE } from "@/lib/auth/login";
import { deleteAccount } from "@/lib/app/settings";
import {
  authorizeSettingsRelay,
  settingsRelayFailure,
  SETTINGS_NO_STORE,
} from "@/lib/app/settings-relay";

/**
 * POST — delete this account (decision S9: the typed phrase only).
 *
 * The session cookie is cleared ONLY after the backend's 204. A blocked
 * screenshot cleanup (503) or any other failure deleted nothing, so the trader
 * stays signed in and can retry; clearing the cookie then would sign them out
 * of an account that still exists.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const auth = await authorizeSettingsRelay(request);
  if (auth instanceof NextResponse) return auth;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false }, { status: 400, headers: SETTINGS_NO_STORE });
  }

  try {
    await deleteAccount(auth.token, body);
  } catch (err) {
    return settingsRelayFailure(err, ApiError);
  }

  // The backend has already deleted every session row for this account, so
  // the cookie names nothing; clearing it stops the browser presenting it.
  const response = NextResponse.json(
    { ok: true, next: "/account-deleted" },
    { status: 200, headers: SETTINGS_NO_STORE },
  );
  response.cookies.delete(SESSION_COOKIE);
  return response;
}
