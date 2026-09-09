"use client";

import { useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import {
  ANALYTICS_FILTER_KEYS,
  parseAnalyticsFilters,
  type AnalyticsFilters,
} from "@/lib/app/analytics-filters";

/**
 * The analytics filter bar: which slice of the record the four lenses read.
 *
 * The same idiom as the journal's `FilterBar`. Filters write to the URL, never
 * to component state the URL does not reflect, so a filtered analytics view
 * stays a shareable link and the server render is the single source of what is
 * on screen. Local state holds only in-progress keystrokes between commits.
 *
 * Three text fields and nothing else — no date field of any kind. The period
 * is the global lens above this page, and a range picker here would be a
 * second window on one screen.
 *
 * The values render from `filters`, which the URL supplied, so what the fields
 * show and what the numbers were measured over cannot disagree.
 */
export function AnalyticsFilterBar({ filters }: { filters: AnalyticsFilters }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [asset, setAsset] = useState(filters.asset ?? "");
  const [session, setSession] = useState(filters.session ?? "");
  const [strategy, setStrategy] = useState(filters.strategy ?? "");

  function apply(next: AnalyticsFilters) {
    const params = new URLSearchParams(searchParams.toString());
    for (const key of ANALYTICS_FILTER_KEYS) {
      const value = next[key]?.trim();
      if (value) params.set(key, value);
      else params.delete(key);
    }
    router.replace(`${pathname}?${params.toString()}`);
  }

  const current = { asset, session, strategy };
  const active = parseAnalyticsFilters(new URLSearchParams(searchParams.toString()));
  const hasFilters = Boolean(active.asset || active.session || active.strategy);

  const fields = [
    { key: "asset", label: "Asset", value: asset, set: setAsset, placeholder: "e.g. NQ" },
    {
      key: "session",
      label: "Session",
      value: session,
      set: setSession,
      placeholder: "e.g. London",
    },
    {
      key: "strategy",
      label: "Strategy",
      value: strategy,
      set: setStrategy,
      placeholder: "e.g. Silver bullet",
    },
  ] as const;

  return (
    <form
      className="mt-4 flex flex-wrap items-end gap-3 rounded-xl border border-line bg-surface p-4"
      onSubmit={(event) => {
        event.preventDefault();
        apply(current);
      }}
    >
      {fields.map((field) => (
        <label key={field.key} className="flex flex-col gap-1 text-xs text-muted">
          {field.label}
          <input
            type="text"
            value={field.value}
            onChange={(event) => field.set(event.target.value)}
            onBlur={() => apply({ ...current, [field.key]: field.value })}
            placeholder={field.placeholder}
            className="w-36 rounded-md border border-line bg-chart px-2 py-1.5 text-sm text-text outline-none focus:border-accent"
          />
        </label>
      ))}
      {hasFilters && (
        <button
          type="button"
          onClick={() => {
            setAsset("");
            setSession("");
            setStrategy("");
            apply({});
          }}
          className="rounded-md border border-line-strong px-3 py-1.5 text-sm text-muted transition-colors duration-150 ease-tl hover:bg-surface-2 hover:text-text"
        >
          Clear filters
        </button>
      )}
    </form>
  );
}
