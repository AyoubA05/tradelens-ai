/**
 * The inline result of one Settings change, beside the control that made it.
 *
 * Settings are changed one at a time, so the confirmation belongs where the
 * change happened rather than in a toast in a corner the eye is not on.
 * `role="status"` so it is announced, not only seen.
 */
export function SettingStatus({ tone, text }: { tone: "ok" | "fail"; text: string }) {
  return (
    <p role="status" className={`mt-2 text-sm ${tone === "ok" ? "text-positive" : "text-negative"}`}>
      {text}
    </p>
  );
}
