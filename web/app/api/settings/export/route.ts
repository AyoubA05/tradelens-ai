import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/client";
import { exportTradesCsv } from "@/lib/app/settings";
import {
  authorizeSettingsRelay,
  settingsRelayFailure,
  SETTINGS_NO_STORE,
} from "@/lib/app/settings-relay";

/**
 * GET — the trader's trades as a CSV download. The API has already neutralised
 * spreadsheet-formula cells (decision S5); this relay only turns the JSON
 * envelope into an attachment with a fixed filename.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const auth = await authorizeSettingsRelay(request);
  if (auth instanceof NextResponse) return auth;
  try {
    const result = await exportTradesCsv(auth.token);
    return new NextResponse(result.csv, {
      status: 200,
      headers: {
        ...SETTINGS_NO_STORE,
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": 'attachment; filename="trades.csv"',
      },
    });
  } catch (err) {
    return settingsRelayFailure(err, ApiError);
  }
}
