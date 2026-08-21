"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { CalendarRange, ChevronDown } from "lucide-react";

import {
  PERIOD_PRESETS,
  formatPeriod,
  periodFromParams,
  periodToParams,
  rangeForPreset,
  routeUsesPeriod,
} from "@/lib/app/period";

/**
 * The signature control: the window under examination, always visible.
 *
 * It is chrome rather than a page filter on purpose. A win rate over four days
 * and a win rate over four months are different claims, and a control that
 * lives inside one page lets a reader carry the wrong assumption to the next
 * one. Later phases read this from the URL instead of adding their own.
 *
 * `router.replace` rather than `push`: changing the window is refining one
 * question, not navigating, and it should not fill the back button with
 * near-identical entries.
 */
export function PeriodLens() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [open, setOpen] = useState(false);

  const period = periodFromParams(new URLSearchParams(searchParams.toString()));

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  function choose(presetId: string) {
    const today = new Date();
    const params = new URLSearchParams(searchParams.toString());
    // rangeForPreset is the one place the preset-to-range mapping lives —
    // round-tripping the result through periodFromParams means this control
    // reads back exactly what a URL carrying that range would produce,
    // rather than assuming its own idea of the shape matches the contract.
    const range = rangeForPreset(presetId, today);
    const next = periodFromParams(new URLSearchParams(range), today);
    for (const [key, value] of periodToParams(next)) params.set(key, value);
    setOpen(false);
    router.replace(`${pathname}?${params.toString()}`);
  }

  // After the hooks, never before: a conditional return above them would change
  // the hook order between routes. The lens is absent on routes the range does
  // not govern rather than disabled, because a control that looks like it
  // governs a page but does not is worse than no control at all.
  if (!routeUsesPeriod(pathname)) return null;

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex items-center gap-2 rounded-md border border-line bg-surface px-3 py-1.5 text-left transition-colors duration-150 ease-tl hover:border-line-strong"
      >
        <CalendarRange className="h-3.5 w-3.5 text-muted" aria-hidden="true" />
        <span className="sr-only">Period under review</span>
        <span className="font-mono text-xs text-text">{formatPeriod(period)}</span>
        <ChevronDown className="h-3.5 w-3.5 text-muted" aria-hidden="true" />
      </button>

      {/*
        A plain labelled group of buttons, not role="menu": the menu pattern
        promises arrow-key navigation, focus moving in on open, and focus
        returning to the trigger on Escape, and this implements none of the
        three. Tab already reaches every preset in document order, so the
        markup claims exactly the behaviour that exists.
      */}
      {open && (
        <div
          role="group"
          aria-label="Period presets"
          className="absolute right-0 z-30 mt-1.5 w-48 rounded-lg border border-line bg-surface-2 py-1 shadow-xl"
        >
          {PERIOD_PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              onClick={() => choose(preset.id)}
              className={[
                "flex w-full items-center justify-between px-3 py-2 text-left text-sm transition-colors duration-150 ease-tl hover:bg-surface-3",
                period.presetId === preset.id ? "text-accent" : "text-text",
              ].join(" ")}
            >
              {preset.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
