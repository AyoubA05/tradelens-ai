import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/client";
import { deleteAllTrades } from "@/lib/app/settings";
import {
  authorizeSettingsRelay,
  settingsRelayFailure,
  SETTINGS_NO_STORE,
} from "@/lib/app/settings-relay";

/**
 * POST — delete every trade this account has. The body carries only the typed
 * confirmation, forwarded unchanged; the API's `Literal["DELETE"]` is the
 * check. A blocked screenshot cleanup comes back as 503 with nothing deleted.
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
    const result = await deleteAllTrades(auth.token, body);
    return NextResponse.json(result, { status: 200, headers: SETTINGS_NO_STORE });
  } catch (err) {
    return settingsRelayFailure(err, ApiError);
  }
}
