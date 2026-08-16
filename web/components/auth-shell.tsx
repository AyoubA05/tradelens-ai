"use client";

import Link from "next/link";
import { motion } from "framer-motion";

import { AuroraBackdrop } from "@/components/ui/aurora-backdrop";
import { GlowFrame } from "@/components/ui/glow-frame";

/**
 * Frame for every auth page that is not the sign-in card: verification,
 * forgot/reset, onboarding, signup, and the continuation step.
 *
 * These used to be deliberately quieter than the sign-in card — flat surface,
 * no backdrop, no beams. In isolation that reasoning held; in sequence it did
 * not. Signing up meant leaving a lit, animated front door and landing on a
 * page that looked like a different product's form, and the last screen before
 * the app dropped the treatment again. The flow now wears one skin: same
 * backdrop, same beam-bordered glass, same accent.
 *
 * `tilt` is off here by default. See `GlowFrame` — the 3D rotation belongs on a
 * short card, not under a form someone is filling in.
 *
 * A client component so the entrance animation matches the card's. Children
 * are still rendered by their server-component parents and passed in, so the
 * pages keep doing their session checks on the server before anything renders.
 */
export function AuthShell({
  title,
  intro,
  children,
  footer,
  centered = false,
  tilt = false,
}: {
  title: string;
  intro?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  /** Centres the card's own header and shows the candle mark, as the sign-in
   *  card does. For short status cards; forms read better left-aligned. */
  centered?: boolean;
  tilt?: boolean;
}) {
  return (
    <main className="relative min-h-screen bg-bg text-text flex items-center justify-center overflow-hidden px-4 py-12">
      <AuroraBackdrop />

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8 }}
        className="relative z-10 w-full max-w-md"
        style={{ perspective: 1500 }}
      >
        <Link href="/" className="mb-8 flex items-center justify-center gap-2.5">
          <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden fill="none">
            <rect x="3" y="13" width="3" height="7" rx="1" className="fill-accent/70" />
            <rect x="10" y="9" width="3" height="11" rx="1" className="fill-accent/85" />
            <rect x="17" y="4" width="3" height="16" rx="1" className="fill-accent" />
          </svg>
          <span className="font-display text-base font-semibold tracking-tight">
            TradeLens <span className="text-accent">AI</span>
          </span>
        </Link>

        <GlowFrame tilt={tilt}>
          {centered && (
            <motion.div
              initial={{ scale: 0.5, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ type: "spring", duration: 0.8 }}
              className="mx-auto mb-3 flex h-10 w-10 items-center justify-center overflow-hidden rounded-full border border-white/10 relative"
            >
              <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden fill="none">
                <rect x="3" y="13" width="3" height="7" rx="1" className="fill-accent/70" />
                <rect x="10" y="9" width="3" height="11" rx="1" className="fill-accent/85" />
                <rect x="17" y="4" width="3" height="16" rx="1" className="fill-accent" />
              </svg>
              <div className="absolute inset-0 bg-gradient-to-br from-white/10 to-transparent opacity-50" />
            </motion.div>
          )}

          <motion.h1
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className={`font-display text-xl font-semibold tracking-tight ${centered ? "text-center" : ""}`}
          >
            {title}
          </motion.h1>

          {intro && (
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.3 }}
              className={`mt-1.5 text-sm leading-relaxed text-muted ${centered ? "text-center" : ""}`}
            >
              {intro}
            </motion.p>
          )}

          <div className="mt-6">{children}</div>
        </GlowFrame>

        {footer && <div className="mt-5 text-center text-xs text-muted">{footer}</div>}

        <p className="mt-8 text-center text-[11px] leading-relaxed text-muted">
          <span className="text-text">Reflection only.</span> TradeLens reviews the
          trade you already took. It does not generate signals, predictions, or
          trade advice.
        </p>
      </motion.div>
    </main>
  );
}
