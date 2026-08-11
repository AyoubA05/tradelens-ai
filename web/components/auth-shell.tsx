import Link from "next/link";

/**
 * Frame for the auth pages that are not the sign-in card: verification,
 * forgot/reset, onboarding. Deliberately quieter than the card — these are
 * places a user reads and completes a task, not the front door.
 */
export function AuthShell({
  title,
  intro,
  children,
  footer,
}: {
  title: string;
  intro?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <main className="min-h-screen bg-bg text-text flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        <Link href="/" className="mb-8 flex items-center gap-2.5">
          <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden fill="none">
            <rect x="3" y="13" width="3" height="7" rx="1" className="fill-accent/70" />
            <rect x="10" y="9" width="3" height="11" rx="1" className="fill-accent/85" />
            <rect x="17" y="4" width="3" height="16" rx="1" className="fill-accent" />
          </svg>
          <span className="font-display text-base font-semibold tracking-tight">
            TradeLens <span className="text-accent">AI</span>
          </span>
        </Link>

        <div className="rounded-2xl border border-border bg-surface/60 p-6 backdrop-blur-xl shadow-2xl">
          <h1 className="font-display text-xl font-semibold tracking-tight">{title}</h1>
          {intro && <p className="mt-1.5 text-sm leading-relaxed text-muted">{intro}</p>}
          <div className="mt-6">{children}</div>
        </div>

        {footer && <div className="mt-5 text-center text-xs text-muted">{footer}</div>}

        <p className="mt-8 text-center text-[11px] leading-relaxed text-muted">
          <span className="text-text">Reflection only.</span> TradeLens reviews the
          trade you already took. It does not generate signals, predictions, or
          trade advice.
        </p>
      </div>
    </main>
  );
}
