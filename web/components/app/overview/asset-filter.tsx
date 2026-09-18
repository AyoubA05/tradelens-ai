"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

/**
 * The instrument lens for the Overview period.
 *
 * Deliberately narrower than the period lens in the top bar: this scopes one
 * page's period figures, so it lives on the page rather than in the chrome. It
 * scopes the period frame only — today, the running week and the activation
 * path are lifetime facts and are computed unfiltered on the server.
 *
 * The options are the instruments this owner actually traded in the period,
 * never a static symbol list: offering an instrument the trader never traded
 * invites a scope that can only ever be empty.
 *
 * `router.push` rather than `replace`: unlike refining the date window, moving
 * between instruments is a place a trader will want to come back from.
 */
export function AssetFilter({
  asset,
  availableAssets,
}: {
  asset: string | null;
  availableAssets: string[];
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // Nothing traded in this period means nothing to filter. A control whose only
  // option is "All assets" implies a choice that does not exist.
  if (availableAssets.length === 0) return null;

  function choose(value: string) {
    const params = new URLSearchParams(searchParams.toString());
    // Cleared scope drops the parameter rather than setting it empty, so the
    // unscoped URL is the same URL a trader arrives on.
    if (value) params.set("asset", value);
    else params.delete("asset");
    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname);
  }

  return (
    <div className="mt-4 flex flex-wrap items-center gap-3">
      <label className="flex items-center gap-2 text-sm text-muted">
        <span className="sr-only">Filter by asset</span>
        <select
          aria-label="Filter by asset"
          value={asset ?? ""}
          onChange={(event) => choose(event.target.value)}
          className="min-h-[44px] rounded-md border border-line bg-surface px-3 py-2 text-sm text-text transition-colors duration-150 ease-tl hover:border-line-strong"
        >
          <option value="">All assets</option>
          {availableAssets.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
      {asset ? (
        <p className="text-sm text-muted">
          Showing {asset} only. Today and this week stay lifetime figures.
        </p>
      ) : null}
    </div>
  );
}
