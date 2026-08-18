import Link from "next/link";

/**
 * An empty screen is an invitation to act, not a shrug.
 *
 * It names what is missing and offers the one action that fills it. Anything
 * more turns a dead end into a menu.
 */
export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: { href: string; label: string };
}) {
  return (
    <div className="rounded-xl border border-line bg-surface px-6 py-12 text-center">
      <h2 className="font-display text-base font-semibold text-text">{title}</h2>
      <p className="mx-auto mt-2 max-w-sm text-sm text-muted">{description}</p>
      {action && (
        <Link
          href={action.href}
          className="mt-5 inline-flex items-center rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg transition-colors duration-150 ease-tl hover:bg-accent/90"
        >
          {action.label}
        </Link>
      )}
    </div>
  );
}
