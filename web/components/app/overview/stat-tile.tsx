/**
 * One figure, its label, and an optional line of context.
 *
 * Tone tints the value, but never carries meaning alone: the sign lives in the
 * text. Measured against a dark surface, the positive and negative tokens are
 * ΔE 2.3 apart under deuteranopia — indistinguishable to the most common
 * colour-vision deficiency, and obviously different to everyone else, which is
 * how that ships unnoticed.
 */
export function StatTile({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "positive" | "negative" | "neutral";
}) {
  const toneClass =
    tone === "positive" ? "text-positive" : tone === "negative" ? "text-negative" : "text-text";
  return (
    <div className="border-l border-line px-4 py-3 first:border-l-0 first:pl-0">
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{label}</div>
      <div className={`mt-1 font-mono text-xl ${toneClass}`}>{value}</div>
      {hint && <div className="mt-0.5 font-mono text-[11px] text-muted">{hint}</div>}
    </div>
  );
}
