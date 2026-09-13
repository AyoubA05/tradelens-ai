import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/client";
import { writeTimezone } from "@/lib/app/settings";
import {
  authorizeSettingsRelay,
  settingsRelayFailure,
  SETTINGS_NO_STORE,
} from "@/lib/app/settings-relay";

/**
 * PUT — save the trading timezone. The body is forwarded unchanged: the API's
 * strict schema and its six-zone allowlist (decision S6) are the check.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function PUT(request: Request) {
  const auth = await authorizeSettingsRelay(request);
  if (auth instanceof NextResponse) return auth;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false }, { status: 400, headers: SETTINGS_NO_STORE });
  }

  try {
    const result = await writeTimezone(auth.token, body);
    return NextResponse.json(result, { status: 200, headers: SETTINGS_NO_STORE });
  } catch (err) {
    return settingsRelayFailure(err, ApiError);
  }
}
