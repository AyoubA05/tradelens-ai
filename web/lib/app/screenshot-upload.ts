import type { components } from "@/lib/api/schema";

/**
 * Attaching one chart screenshot to a trade that already exists.
 *
 * Deliberately NOT `server-only`: this is the browser half of the
 * lifecycle, and the upload component calls it directly. The three FastAPI
 * calls it makes go through `/api/trades/{id}/screenshot`, the relay, for
 * the same reason `NewTradeForm` posts to `/api/trades/create` — `callApi`
 * carries the service secret and cannot be reached from a bundle. Only the
 * PUT goes straight out, to R2, because that URL is presigned and carries
 * no credential of ours.
 *
 * The order is fixed by design decision #1: the trade is created first and
 * its id is what authorises the upload. So every function here takes a
 * `tradeId` for a trade that already exists, and none of them can create
 * one. That is the property that makes retry safe — see `attachScreenshot`.
 */
export type ScreenshotDescriptor = components["schemas"]["ScreenshotDescriptor"];
export type ScreenshotPresignResponse = components["schemas"]["ScreenshotPresignResponse"];
export type ScreenshotContentType =
  components["schemas"]["ScreenshotPresignRequest"]["content_type"];

/**
 * The content types the presign endpoint's enum accepts.
 *
 * Read off the generated schema's own union rather than retyped, so a
 * backend change that widens or narrows it fails compilation here instead
 * of being discovered by a trader whose upload is refused.
 */
export const ACCEPTED_SCREENSHOT_TYPES: readonly ScreenshotContentType[] = [
  "image/png",
  "image/jpeg",
  "image/webp",
];

/**
 * What happened to the screenshot — never to the trade.
 *
 * Every outcome other than `attached` leaves an existing trade completely
 * untouched, and callers must say so. `rejected` and `stale` are separated
 * because the backend deliberately separates them: 422 means these bytes
 * are not a usable image and picking a different file is the way forward;
 * 409 means the quarantine object is gone (a stale key, a double-finalize,
 * a retry after abandon) and the same file simply needs uploading again.
 * Collapsing either into `failed` would throw away the reason that split
 * exists.
 */
export type ScreenshotAttachResult =
  | { status: "attached"; screenshot: ScreenshotDescriptor }
  | { status: "rejected"; message: string }
  | { status: "stale"; message: string }
  | { status: "failed"; message: string };

export type UploadPhase = "presigning" | "uploading" | "validating";

export interface AttachScreenshotOptions {
  /** Progress in [0, 1] during the PUT, and phase changes around it. */
  onPhase?: (phase: UploadPhase, progress: number) => void;
  /** Injectable for tests; the default reports real upload progress. */
  put?: (
    url: string,
    file: File,
    onProgress: (fraction: number) => void,
  ) => Promise<{ ok: boolean }>;
  fetchImpl?: typeof fetch;
}

const REJECTED_MESSAGE =
  "That file was not accepted as a chart image. The trade is unchanged — pick a PNG, JPEG or WebP screenshot and try again.";
const STALE_MESSAGE =
  "The upload expired before it finished attaching. The trade is unchanged — choose the file again to re-upload it.";
const FAILED_MESSAGE =
  "The screenshot did not attach. The trade is unchanged — you can try again now or from the trade's page later.";

/**
 * A courtesy check, run before a byte leaves the browser.
 *
 * This is NOT the gate. `imaging.validate_and_normalise` caps bytes,
 * refuses non-images, guards against decompression bombs and re-encodes
 * what it keeps; that runs at finalize and is what actually decides. The
 * only thing this buys a trader is not sitting through a slow upload of a
 * file that would be refused at the end of it — which is why the message
 * talks about the upload, not about permission.
 *
 * `maxBytes` comes from the presign response (`max_bytes`), never from a
 * constant here: the server owns that number and this code must not hold a
 * second copy that can drift.
 */
export function screenshotPreflight(
  file: { type: string; size: number },
  maxBytes: number | null,
): string | null {
  if (!ACCEPTED_SCREENSHOT_TYPES.includes(file.type as ScreenshotContentType)) {
    return "Only PNG, JPEG and WebP screenshots can be uploaded.";
  }
  if (maxBytes !== null && file.size > maxBytes) {
    return `That file is larger than the ${formatMebibytes(maxBytes)} limit, so uploading it would not succeed.`;
  }
  return null;
}

function formatMebibytes(bytes: number): string {
  const mib = bytes / (1024 * 1024);
  return `${Number.isInteger(mib) ? mib : mib.toFixed(1)} MB`;
}

/** PUT the bytes to R2, reporting real progress. */
function xhrPut(
  url: string,
  file: File,
  onProgress: (fraction: number) => void,
): Promise<{ ok: boolean }> {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    // ContentType is bound into the presigned policy, so this is a rule R2
    // enforces rather than advice we give — a mismatch is refused there.
    xhr.setRequestHeader("Content-Type", file.type);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => resolve({ ok: xhr.status >= 200 && xhr.status < 300 });
    xhr.onerror = () => resolve({ ok: false });
    xhr.onabort = () => resolve({ ok: false });
    xhr.send(file);
  });
}

async function relay(
  fetchImpl: typeof fetch,
  tradeId: number,
  body: Record<string, unknown>,
): Promise<Response> {
  return fetchImpl(`/api/trades/${tradeId}/screenshot`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/**
 * Best-effort cleanup of a quarantine object nobody will ever finalize.
 *
 * A quarantine object has no download path and no `screenshots` row, so
 * nothing else in the system can name it — abandon is the only way it is
 * ever removed. It is also purely housekeeping: a failure here changes
 * nothing a trader can see, so it never becomes an error they must clear.
 */
export async function abandonScreenshotUpload(
  tradeId: number,
  key: string,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  try {
    await relay(fetchImpl, tradeId, { action: "abandon", key });
  } catch {
    // Nothing a trader can act on. Swallowed on purpose.
  }
}

/**
 * Attach one screenshot to a trade that already exists.
 *
 * This function can never create a trade, and that is the point: retry
 * after a failed upload calls exactly this, with the same `tradeId`, so a
 * trader retrying an upload cannot end up with a second trade. (The
 * fingerprint would refuse a duplicate write anyway — but the UI must not
 * offer the trader a path that looks like resubmitting the form.)
 */
export async function attachScreenshot(
  tradeId: number,
  file: File,
  options: AttachScreenshotOptions = {},
): Promise<ScreenshotAttachResult> {
  const fetchImpl = options.fetchImpl ?? fetch;
  const put = options.put ?? xhrPut;
  const phase = options.onPhase ?? (() => {});

  const typeError = screenshotPreflight(file, null);
  if (typeError) return { status: "rejected", message: typeError };

  phase("presigning", 0);
  let presigned: ScreenshotPresignResponse;
  try {
    const response = await relay(fetchImpl, tradeId, {
      action: "presign",
      content_type: file.type,
    });
    if (!response.ok) return { status: "failed", message: FAILED_MESSAGE };
    presigned = (await response.json()) as ScreenshotPresignResponse;
  } catch {
    return { status: "failed", message: FAILED_MESSAGE };
  }

  // The server's own number, now that we have it.
  const sizeError = screenshotPreflight(file, presigned.max_bytes);
  if (sizeError) {
    await abandonScreenshotUpload(tradeId, presigned.key, fetchImpl);
    return { status: "rejected", message: sizeError };
  }

  phase("uploading", 0);
  let uploaded: { ok: boolean };
  try {
    uploaded = await put(presigned.url, file, (fraction) => phase("uploading", fraction));
  } catch {
    uploaded = { ok: false };
  }
  if (!uploaded.ok) {
    await abandonScreenshotUpload(tradeId, presigned.key, fetchImpl);
    return { status: "failed", message: FAILED_MESSAGE };
  }

  phase("validating", 1);
  try {
    const response = await relay(fetchImpl, tradeId, {
      action: "finalize",
      key: presigned.key,
    });
    if (response.ok) {
      return { status: "attached", screenshot: (await response.json()) as ScreenshotDescriptor };
    }
    if (response.status === 422) {
      // Definitively refused, so the quarantine object will never be
      // promoted and is pure litter. A 409 gets no abandon: the object is
      // already gone, which is what 409 means.
      await abandonScreenshotUpload(tradeId, presigned.key, fetchImpl);
      return { status: "rejected", message: REJECTED_MESSAGE };
    }
    if (response.status === 409) return { status: "stale", message: STALE_MESSAGE };
    return { status: "failed", message: FAILED_MESSAGE };
  } catch {
    // A transient fault, not a refusal: the key may still be finalizable,
    // so it is NOT abandoned here.
    return { status: "failed", message: FAILED_MESSAGE };
  }
}
