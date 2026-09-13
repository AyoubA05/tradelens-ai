import Link from "next/link";

/**
 * Where a trader lands after deleting their account.
 *
 * Public by construction: the account and every session row are already gone,
 * and the relay has cleared the cookie, so this page reads no session and
 * names no one.
 */

export const dynamic = "force-static";

export default function AccountDeletedPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6 text-center">
      <h1 className="font-display text-2xl font-bold">Your account has been deleted.</h1>
      <p className="mt-3 text-sm text-muted">
        Everything in it has been erased. Anonymous records of what AI features cost to run are kept for
        accounting, with no link to you.
      </p>
      <Link
        href="/"
        className="mx-auto mt-6 min-h-[44px] rounded-lg border border-line-strong px-4 py-2 text-sm text-text"
      >
        Return to TradeLens
      </Link>
    </main>
  );
}
