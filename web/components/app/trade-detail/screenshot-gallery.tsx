"use client";

import { useState } from "react";
import { ImageOff } from "lucide-react";

import type { ScreenshotDescriptor } from "@/lib/app/trades";

/**
 * One screenshot. `url` is `null` when `presign_download` could not resolve
 * this object (design decision #6), and a URL that resolved a moment ago can
 * still 404 by the time the browser fetches it — the presigned link is
 * short-lived on purpose. Both cases render the same graceful placeholder
 * rather than a broken-image icon, because a trader cannot tell "this object
 * is gone" from "this link expired" and the copy should not pretend to know
 * either.
 */
function Frame({ shot, asset }: { shot: ScreenshotDescriptor; asset: string }) {
  const [failed, setFailed] = useState(false);
  const alt = `Chart screenshot for the ${asset} trade`;

  if (!shot.url || failed) {
    return (
      <div
        role="img"
        aria-label={`${alt} is not available right now`}
        className="flex aspect-video flex-col items-center justify-center gap-2 rounded-xl border border-line bg-surface text-muted"
      >
        <ImageOff className="h-5 w-5" aria-hidden="true" />
        <span className="text-xs">Image not available right now</span>
      </div>
    );
  }

  return (
    // A presigned R2 URL is opaque and short-lived; Next's image optimizer
    // would need to fetch and cache a link that is deliberately not meant to
    // be reusable.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={shot.url}
      alt={alt}
      loading="lazy"
      width={shot.width ?? undefined}
      height={shot.height ?? undefined}
      onError={() => setFailed(true)}
      className="aspect-video w-full rounded-xl border border-line bg-surface object-contain"
    />
  );
}

/**
 * The Trade Detail screenshot gallery.
 *
 * Screenshots come already presigned on `TradeDetail.screenshots` (Task A3) —
 * this component never fetches or proxies image bytes itself (design
 * decision #6: proxying through Next.js would put a serverless invocation on
 * every page view).
 */
export function ScreenshotGallery({
  screenshots,
  asset,
}: {
  screenshots: ScreenshotDescriptor[];
  asset: string;
}) {
  if (screenshots.length === 0) return null;

  return (
    <section className="mt-8">
      <h2 className="font-display text-sm font-semibold text-text">Screenshots</h2>
      <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
        {screenshots.map((shot) => (
          <Frame key={shot.id} shot={shot} asset={asset} />
        ))}
      </div>
    </section>
  );
}
