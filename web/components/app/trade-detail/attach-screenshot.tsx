"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import {
  ScreenshotUpload,
  type ScreenshotUploadStatus,
} from "@/components/app/new-trade/screenshot-upload";
import {
  abandonScreenshotUpload,
  attachScreenshot,
  screenshotPreflight,
} from "@/lib/app/screenshot-upload";

/**
 * Attaching a chart screenshot to a trade that ALREADY EXISTS (Task 2).
 *
 * No new endpoint and no new relay: this island drives the same
 * `attachScreenshot` helper the New Trade form uses, which posts presign /
 * finalize / abandon to `/api/trades/{id}/screenshot` — the owner-scoped
 * relay that already exists and is already tested. The trade's id is what
 * authorises the upload, and this component cannot create a trade, so a
 * retry here can never produce a second one.
 *
 * On success it does not paint the new image itself. The gallery renders
 * `TradeDetail.screenshots`, which is server data; `router.refresh()` is
 * what makes the attached screenshot appear, so the page can never show an
 * image for a file the server did not actually accept. Nothing here ever
 * renders an <img> — on any failure the gallery is left exactly as it was.
 */

const IDLE_COPY = "Attach a chart screenshot to this trade.";
const FAILURE_COPY = "That screenshot was not attached. Try again.";

export function AttachScreenshot({ tradeId }: { tradeId: number }) {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<ScreenshotUploadStatus>({ kind: "idle" });
  // A ref, not the `busy` status: two change events in the same tick would
  // both read the pre-update state and start two presigns.
  const runningRef = useRef(false);

  async function handleSelect(picked: File | null) {
    if (runningRef.current) return;
    setFile(picked);
    if (!picked) {
      setStatus({ kind: "idle" });
      return;
    }

    // The courtesy check, before a byte leaves the browser. `maxBytes` is
    // not known until the presign response, so this pass only catches the
    // wrong file type — the size check runs inside `attachScreenshot`
    // against the server's own number.
    const typeError = screenshotPreflight(picked, null);
    if (typeError) {
      setStatus({ kind: "problem", message: typeError });
      return;
    }

    runningRef.current = true;
    setStatus({ kind: "busy", phase: "presigning", progress: 0 });
    try {
      const result = await attachScreenshot(tradeId, picked, {
        onPhase: (phase, progress) => setStatus({ kind: "busy", phase, progress }),
      });
      if (result.status === "attached") {
        setFile(null);
        setStatus({ kind: "attached" });
        // The gallery reads server data; this is what shows the new image.
        router.refresh();
        return;
      }
      // A quarantine object nobody will ever finalize has no other way out.
      if (result.pendingKey) void abandonScreenshotUpload(tradeId, result.pendingKey);
      // `rejected` and `stale` say something a trader can act on; only an
      // opaque failure gets the fixed sentence.
      setStatus({
        kind: "problem",
        message: result.status === "failed" ? FAILURE_COPY : result.message,
      });
    } finally {
      runningRef.current = false;
    }
  }

  return (
    <div className="mt-4">
      <p className="text-xs text-muted">{IDLE_COPY}</p>
      <div className="mt-2">
        <ScreenshotUpload file={file} onSelect={(picked) => void handleSelect(picked)} status={status} />
      </div>
    </div>
  );
}
