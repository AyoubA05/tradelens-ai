"use client";

import { useState } from "react";

import { SettingStatus } from "@/components/app/settings/setting-status";

/**
 * Preferences — how the app reads what you log.
 *
 * The timezone saves on change through the relay; the server's six-zone
 * allowlist (decision S6) is the check, and a refusal restores the previous
 * value. The AI line is availability only (decision S2) — never how a key is
 * configured — and demo mode is a status line (decision S3).
 */

const AI_COPY = {
  enabled: "AI features are enabled.",
  demo: "Demo mode — AI sections read cached sample responses. No key, no spend.",
  unavailable: "AI features are unavailable on this deployment right now.",
} as const;

const GENERIC_FAILURE = "That did not work. Try again.";

export function PreferencesSection({
  timezone,
  ai,
  demoMode,
}: {
  timezone: { current: string; options: string[] };
  ai: { state: keyof typeof AI_COPY };
  demoMode: boolean;
}) {
  const [current, setCurrent] = useState(timezone.current);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<{ tone: "ok" | "fail"; text: string } | null>(null);
  // A legacy stored zone outside the six is shown and kept until another is chosen.
  const options = timezone.options.includes(current)
    ? timezone.options
    : [current, ...timezone.options];

  async function save(next: string) {
    if (next === current || saving) return;
    const previous = current;
    setCurrent(next);
    setSaving(true);
    setStatus(null);
    try {
      const response = await fetch("/api/settings/timezone", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ timezone: next }),
      });
      if (response.ok) {
        setStatus({ tone: "ok", text: `Trading timezone saved — ${next}.` });
        return;
      }
      setCurrent(previous);
      setStatus({
        tone: "fail",
        text: response.status === 422 ? "Choose one of the listed timezones." : GENERIC_FAILURE,
      });
    } catch {
      setCurrent(previous);
      setStatus({ tone: "fail", text: GENERIC_FAILURE });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section aria-labelledby="settings-preferences" className="mt-10">
      <h2 id="settings-preferences" className="font-display text-xl font-bold">
        Preferences
      </h2>
      <p className="mt-1 text-sm text-muted">How the app interprets what you log.</p>
      <label htmlFor="settings-timezone" className="mt-4 block text-sm text-text">
        Trading timezone
      </label>
      <select
        id="settings-timezone"
        value={current}
        disabled={saving}
        onChange={(event) => void save(event.target.value)}
        className="mt-1 min-h-[44px] rounded-lg border border-line bg-bg px-3 text-sm text-text disabled:opacity-60"
      >
        {options.map((tz) => (
          <option key={tz} value={tz}>
            {tz}
          </option>
        ))}
      </select>
      <p className="mt-1 text-xs text-muted">
        Used to detect your killzone and session from the entry time on New Trade.
      </p>
      {status ? <SettingStatus tone={status.tone} text={status.text} /> : null}
      <p className={`mt-6 text-sm ${ai.state === "unavailable" ? "text-muted" : "text-text"}`}>
        {AI_COPY[ai.state]}
      </p>
      {demoMode ? (
        <p className="mt-1 text-xs text-muted">This deployment is running in demo mode.</p>
      ) : null}
    </section>
  );
}
