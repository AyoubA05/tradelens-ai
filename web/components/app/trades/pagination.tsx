"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

/**
 * Trades list pagination.
 *
 * Offset pagination, not cursor (design decision #1): the trader's trade
 * count is in the hundreds, not millions, so page N can be a plain,
 * shareable `?offset=` in the URL rather than an opaque cursor token. `limit`
 * is fixed per page load and only `offset` moves, so a link to "page 3"
 * keeps meaning the same thing even if new trades are logged in between —
 * offset pagination trades that consistency for shareability on purpose,
 * which is the right trade for a count this small.
 */
export function Pagination({
  total,
  limit,
  offset,
}: {
  total: number;
  limit: number;
  offset: number;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  if (total <= limit) return null;

  const page = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const hasPrev = offset > 0;
  const hasNext = offset + limit < total;

  function goTo(nextOffset: number) {
    const params = new URLSearchParams(searchParams.toString());
    const clamped = Math.max(0, nextOffset);
    if (clamped === 0) params.delete("offset");
    else params.set("offset", String(clamped));
    router.replace(`${pathname}?${params.toString()}`);
  }

  return (
    <nav
      aria-label="Trades pages"
      className="mt-4 flex items-center justify-between rounded-xl border border-line bg-surface px-4 py-3"
    >
      <span className="font-mono text-xs text-muted">
        Page {page} of {totalPages} · {total} trades
      </span>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => goTo(offset - limit)}
          disabled={!hasPrev}
          className="rounded-md border border-line-strong px-3 py-1.5 text-sm text-text transition-colors duration-150 ease-tl hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Previous
        </button>
        <button
          type="button"
          onClick={() => goTo(offset + limit)}
          disabled={!hasNext}
          className="rounded-md border border-line-strong px-3 py-1.5 text-sm text-text transition-colors duration-150 ease-tl hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </nav>
  );
}
