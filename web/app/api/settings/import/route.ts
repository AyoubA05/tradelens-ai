import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/client";
import { importTradesCsv } from "@/lib/app/settings";
import {
  authorizeSettingsRelay,
  MAX_IMPORT_REQUEST_BYTES,
  settingsRelayFailure,
  SETTINGS_NO_STORE,
} from "@/lib/app/settings-relay";

/**
 * POST — import trades from CSV text (decision S4: synchronous, 1 MB, 5,000
 * rows). A request declaring more than the API's body cap is refused before it
 * is read, and the body is measured again after reading, so a missing or false
 * Content-Length cannot carry an oversized file to the backend.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const auth = await authorizeSettingsRelay(request);
  if (auth instanceof NextResponse) return auth;

  const declared = Number(request.headers.get("content-length") ?? "0");
  if (!Number.isFinite(declared) || declared > MAX_IMPORT_REQUEST_BYTES) {
    return NextResponse.json({ ok: false }, { status: 413, headers: SETTINGS_NO_STORE });
  }

  let raw: string;
  try {
    raw = await request.text();
  } catch {
    return NextResponse.json({ ok: false }, { status: 400, headers: SETTINGS_NO_STORE });
  }
  if (new TextEncoder().encode(raw).byteLength > MAX_IMPORT_REQUEST_BYTES) {
    return NextResponse.json({ ok: false }, { status: 413, headers: SETTINGS_NO_STORE });
  }

  let body: unknown;
  try {
    body = JSON.parse(raw);
  } catch {
    return NextResponse.json({ ok: false }, { status: 400, headers: SETTINGS_NO_STORE });
  }

  try {
    const result = await importTradesCsv(auth.token, body);
    return NextResponse.json(result, { status: 200, headers: SETTINGS_NO_STORE });
  } catch (err) {
    return settingsRelayFailure(err, ApiError);
  }
}
