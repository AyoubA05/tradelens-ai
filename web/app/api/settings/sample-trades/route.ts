import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/client";
import { clearSampleTrades, loadSampleTrades } from "@/lib/app/settings";
import {
  authorizeSettingsRelay,
  settingsRelayFailure,
  SETTINGS_NO_STORE,
} from "@/lib/app/settings-relay";

/**
 * POST loads the sample trades; DELETE clears them. Neither takes a body:
 * which trades are samples is the server's `is_sample` flag, never the
 * browser's choice.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const auth = await authorizeSettingsRelay(request);
  if (auth instanceof NextResponse) return auth;
  try {
    const result = await loadSampleTrades(auth.token);
    return NextResponse.json(result, { status: 200, headers: SETTINGS_NO_STORE });
  } catch (err) {
    return settingsRelayFailure(err, ApiError);
  }
}

export async function DELETE(request: Request) {
  const auth = await authorizeSettingsRelay(request);
  if (auth instanceof NextResponse) return auth;
  try {
    const result = await clearSampleTrades(auth.token);
    return NextResponse.json(result, { status: 200, headers: SETTINGS_NO_STORE });
  } catch (err) {
    return settingsRelayFailure(err, ApiError);
  }
}
