"use client";

import { useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { parseFilters, type TradeFilters } from "@/lib/app/trade-filters";

const RESULT_OPTIONS = ["Win", "Loss", "Breakeven"] as const;

/**
 * The Trades filter bar.
 *
 * Filters write to the URL, never to component state that the URL doesn't
 * reflect — the URL is the filter state of record (design decision #2), so a
 * filtered view stays a shareable link. Local state here holds only the text
 * fields' in-progress keystrokes between submits; the moment a value commits
 * it goes straight through `router.replace`, and a re-render always reads
 * back from `searchParams`, never from a client cache of "what the filters
 * currently are".
 *
 * Changing a filter resets `offset` to 0: page 3 of an unfiltered list is not
 * page 3 of a filtered one, and carrying the old offset forward would either
 * strand the reader past the end of the new, smaller result set or silently
 * skip its first rows.
 */
export function FilterBar() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const filters = parseFilters(new URLSearchParams(searchParams.toString()));

  // Draft values so typing doesn't re-render the URL on every keystroke;
  // committed on blur/change/submit, matching how a native form behaves.
  const [asset, setAsset] = useState(filters.asset ?? "");
  const [session, setSession] = useState(filters.session ?? "");
  const [setup, setSetup] = useState(filters.setup ?? "");

  function apply(next: TradeFilters) {
    const params = new URLSearchParams(searchParams.toString());
    params.delete("offset");
    for (const key of ["asset", "session", "setup", "result"] as const) {
      const value = next[key];
      if (value) params.set(key, value);
      else params.delete(key);
    }
    router.replace(`${pathname}?${params.toString()}`);
  }

  function clearAll() {
    setAsset("");
    setSession("");
    setSetup("");
    apply({});
  }

  const hasFilters = Boolean(filters.asset || filters.session || filters.setup || filters.result);

  return (
    <form
      className="mt-4 flex flex-wrap items-end gap-3 rounded-xl border border-line bg-surface p-4"
      onSubmit={(event) => {
        event.preventDefault();
        apply({ ...filters, asset: asset.trim(), session: session.trim(), setup: setup.trim() });
      }}
    >
      <label className="flex flex-col gap-1 text-xs text-muted">
        Asset
        <input
          type="text"
          value={asset}
          onChange={(event) => setAsset(event.target.value)}
          onBlur={() => apply({ ...filters, asset: asset.trim() })}
          placeholder="e.g. NQ"
          className="w-28 rounded-md border border-line bg-chart px-2 py-1.5 text-sm text-text outline-none focus:border-accent"
        />
      </label>
      <label className="flex flex-col gap-1 text-xs text-muted">
        Session
        <input
          type="text"
          value={session}
          onChange={(event) => setSession(event.target.value)}
          onBlur={() => apply({ ...filters, session: session.trim() })}
          placeholder="e.g. London"
          className="w-32 rounded-md border border-line bg-chart px-2 py-1.5 text-sm text-text outline-none focus:border-accent"
        />
      </label>
      <label className="flex flex-col gap-1 text-xs text-muted">
        Setup
        <input
          type="text"
          value={setup}
          onChange={(event) => setSetup(event.target.value)}
          onBlur={() => apply({ ...filters, setup: setup.trim() })}
          placeholder="e.g. FVG"
          className="w-32 rounded-md border border-line bg-chart px-2 py-1.5 text-sm text-text outline-none focus:border-accent"
        />
      </label>
      <label className="flex flex-col gap-1 text-xs text-muted">
        Result
        <select
          value={filters.result ?? ""}
          onChange={(event) =>
            apply({ ...filters, result: event.target.value || undefined })
          }
          className="w-32 rounded-md border border-line bg-chart px-2 py-1.5 text-sm text-text outline-none focus:border-accent"
        >
          <option value="">Any</option>
          {RESULT_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
      {hasFilters && (
        <button
          type="button"
          onClick={clearAll}
          className="rounded-md border border-line-strong px-3 py-1.5 text-sm text-muted transition-colors duration-150 ease-tl hover:bg-surface-2 hover:text-text"
        >
          Clear filters
        </button>
      )}
    </form>
  );
}
