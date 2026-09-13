import "server-only";

import { callApi } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

/**
 * The Settings page's server-only bridge to `/v1/settings`.
 *
 * `callApi` carries the service secret, so the page (a Server Component) calls
 * `fetchSettings` directly and every write goes through a relay under
 * `app/api/settings/`. Nothing here takes an owner, a trade id, a file path or
 * an object key: the owner is the session, and the two destructive writes send
 * only their typed confirmation.
 */
export type SettingsResponse = components["schemas"]["SettingsResponse"];
export type SampleTradesResponse = components["schemas"]["SampleTradesResponse"];
export type CsvExportResponse = components["schemas"]["CsvExportResponse"];
export type CsvImportResponse = components["schemas"]["CsvImportResponse"];
export type DeleteTradesResponse = components["schemas"]["DeleteTradesResponse"];

export async function fetchSettings(sessionToken: string): Promise<SettingsResponse> {
  return callApi<SettingsResponse>("/v1/settings", sessionToken);
}

export async function writeTimezone(sessionToken: string, body: unknown): Promise<SettingsResponse> {
  return callApi<SettingsResponse>("/v1/settings/timezone", sessionToken, { method: "PUT", body });
}

export async function loadSampleTrades(sessionToken: string): Promise<SampleTradesResponse> {
  return callApi<SampleTradesResponse>("/v1/settings/sample-trades", sessionToken, {
    method: "POST",
    body: {},
  });
}

export async function clearSampleTrades(sessionToken: string): Promise<SampleTradesResponse> {
  return callApi<SampleTradesResponse>("/v1/settings/sample-trades", sessionToken, {
    method: "DELETE",
  });
}

export async function exportTradesCsv(sessionToken: string): Promise<CsvExportResponse> {
  return callApi<CsvExportResponse>("/v1/settings/export", sessionToken);
}

export async function importTradesCsv(sessionToken: string, body: unknown): Promise<CsvImportResponse> {
  return callApi<CsvImportResponse>("/v1/settings/import", sessionToken, { method: "POST", body });
}

export async function deleteAllTrades(sessionToken: string, body: unknown): Promise<DeleteTradesResponse> {
  return callApi<DeleteTradesResponse>("/v1/settings/delete-trades", sessionToken, {
    method: "POST",
    body,
  });
}

/** Resolves only on the backend's 204 — the account and every session row are gone. */
export async function deleteAccount(sessionToken: string, body: unknown): Promise<void> {
  await callApi<void>("/v1/settings/delete-account", sessionToken, { method: "POST", body });
}
