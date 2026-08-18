/**
 * A skeleton is decoration: it stands in for content that is not there yet, and
 * a screen reader gains nothing from being told about the shape of an absence.
 * The status message is what carries the information.
 */
export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse rounded-md bg-surface-2 ${className}`}
    />
  );
}

export function LoadingState({ label }: { label: string }) {
  return (
    <div role="status" className="flex items-center gap-3 py-8 text-sm text-muted">
      <span
        aria-hidden="true"
        className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-line-strong border-t-accent"
      />
      {label}
    </div>
  );
}
