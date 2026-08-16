"use client";

import { motion } from "framer-motion";

/**
 * The animated background the whole auth flow sits on.
 *
 * Lifted verbatim from the sign-in card so there is exactly one definition of
 * it. Every hue, opacity curve, blur radius, duration and delay is the value
 * that card already shipped — this file moved the markup, it did not retune it.
 * That matters because the alternative was copying a hundred lines of animation
 * into the second page, after which the two would drift the first time either
 * was touched.
 *
 * One deliberate difference from the original: the layers are `fixed`, not
 * `absolute`. The sign-in card is shorter than the viewport so the two render
 * identically there, but signup is taller than the viewport, and an absolute
 * backdrop would scroll away and leave the lower half of that form sitting on
 * flat #0d1117.
 */
export function AuroraBackdrop() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 overflow-hidden">
      {/* Background gradient — teal where the source was purple */}
      <div className="absolute inset-0 bg-gradient-to-b from-accent/20 via-accent/10 to-bg" />

      {/* Noise texture, unchanged */}
      <div
        className="absolute inset-0 opacity-[0.03] mix-blend-soft-light"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E")`,
          backgroundSize: "200px 200px",
        }}
      />

      {/* Radial glows — same geometry and timings */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[120vh] h-[60vh] rounded-b-[50%] bg-accent/10 blur-[80px]" />
      <motion.div
        className="absolute top-0 left-1/2 -translate-x-1/2 w-[100vh] h-[60vh] rounded-b-full bg-accent/10 blur-[60px]"
        animate={{ opacity: [0.15, 0.3, 0.15], scale: [0.98, 1.02, 0.98] }}
        transition={{ duration: 8, repeat: Infinity, repeatType: "mirror" }}
      />
      <motion.div
        className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[90vh] h-[90vh] rounded-t-full bg-accent/10 blur-[60px]"
        animate={{ opacity: [0.3, 0.5, 0.3], scale: [1, 1.1, 1] }}
        transition={{ duration: 6, repeat: Infinity, repeatType: "mirror", delay: 1 }}
      />
      <div className="absolute left-1/4 top-1/4 w-96 h-96 bg-white/5 rounded-full blur-[100px] animate-pulse opacity-40" />
      <div className="absolute right-1/4 bottom-1/4 w-96 h-96 bg-white/5 rounded-full blur-[100px] animate-pulse delay-1000 opacity-40" />
    </div>
  );
}

export default AuroraBackdrop;
