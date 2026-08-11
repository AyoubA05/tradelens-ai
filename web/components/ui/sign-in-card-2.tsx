"use client";

/**
 * 21.dev sign-in card, as supplied. Three changes only, all approved:
 *
 *  1. Branding — StyleMe becomes TradeLens AI, and the placeholder "S" glyph
 *     becomes the TradeLens candle mark.
 *  2. Theme — the purple palette is retargeted to the tokens already shared by
 *     the marketing site and the Streamlit app. Gradient geometry, opacity
 *     curves, blur radii and every animation duration/delay are unchanged;
 *     only hue moves.
 *  3. Wiring — the field is "Email or username", submission is delegated to an
 *     `onSubmit` prop instead of a local timeout, and the links point at real
 *     routes.
 *
 * Everything else is the component as given: the 3D mouse-tracked tilt, all
 * four travelling border beams with their staggered delays, the corner glow
 * spots, the glass card, the animated radial background, the input focus
 * transitions and the loading state.
 *
 * Two elements from the original are deliberately NOT rendered: the Google
 * button and Remember me. Both would be non-functional, and a sign-in form
 * that shows controls which do nothing — particularly one implying a security
 * choice — is worse than one that omits them until they work.
 */

import React, { useState } from "react";
import Link from "next/link";
import {
  motion,
  AnimatePresence,
  useMotionValue,
  useTransform,
} from "framer-motion";
import { Mail, Lock, Eye, EyeClosed, ArrowRight } from "lucide-react";

import { Input } from "@/components/ui/input";

type FocusTarget = "identifier" | "password" | null;

export type SignInCardProps = {
  /** Resolves when the attempt finishes. Rejecting surfaces `error`. */
  onSubmit?: (identifier: string, password: string) => Promise<void>;
  /** Generic message. Never distinguishes unknown account from wrong password. */
  error?: string | null;
  /** Server-rendered flag; no client-side env access. */
  signupEnabled?: boolean;
};

export function SignInCard({
  onSubmit,
  error = null,
  signupEnabled = true,
}: SignInCardProps) {
  const [showPassword, setShowPassword] = useState(false);
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [focusedInput, setFocusedInput] = useState<FocusTarget>(null);

  // 3D card effect — same rotation range as the source.
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);
  const rotateX = useTransform(mouseY, [-300, 300], [10, -10]);
  const rotateY = useTransform(mouseX, [-300, 300], [-10, 10]);

  const handleMouseMove = (e: React.MouseEvent) => {
    const rect = e.currentTarget.getBoundingClientRect();
    mouseX.set(e.clientX - rect.left - rect.width / 2);
    mouseY.set(e.clientY - rect.top - rect.height / 2);
  };

  const handleMouseLeave = () => {
    mouseX.set(0);
    mouseY.set(0);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (isLoading) return;
    setIsLoading(true);
    try {
      await onSubmit?.(identifier, password);
    } finally {
      setIsLoading(false);
    }
  };

  const beam =
    "absolute bg-gradient-to-r from-transparent via-accent to-transparent opacity-70";

  return (
    <div className="min-h-screen w-full bg-bg relative overflow-hidden flex items-center justify-center px-4">
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

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8 }}
        className="w-full max-w-sm relative z-10"
        style={{ perspective: 1500 }}
      >
        <motion.div
          className="relative"
          style={{ rotateX, rotateY }}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
          whileHover={{ z: 10 }}
        >
          <div className="relative group">
            <motion.div
              className="absolute -inset-px rounded-2xl opacity-0 group-hover:opacity-70 transition-opacity duration-700"
              animate={{
                boxShadow: [
                  "0 0 10px 2px rgba(255,255,255,0.03)",
                  "0 0 15px 5px rgba(255,255,255,0.05)",
                  "0 0 10px 2px rgba(255,255,255,0.03)",
                ],
                opacity: [0.2, 0.4, 0.2],
              }}
              transition={{ duration: 4, repeat: Infinity, ease: "easeInOut", repeatType: "mirror" }}
            />

            {/* Four travelling beams, staggered exactly as supplied */}
            <div className="absolute -inset-px rounded-2xl overflow-hidden">
              <motion.div
                className={`${beam} top-0 left-0 h-[3px] w-1/2`}
                initial={{ filter: "blur(2px)" }}
                animate={{ left: ["-50%", "100%"], opacity: [0.3, 0.7, 0.3], filter: ["blur(1px)", "blur(2.5px)", "blur(1px)"] }}
                transition={{
                  left: { duration: 2.5, ease: "easeInOut", repeat: Infinity, repeatDelay: 1 },
                  opacity: { duration: 1.2, repeat: Infinity, repeatType: "mirror" },
                  filter: { duration: 1.5, repeat: Infinity, repeatType: "mirror" },
                }}
              />
              <motion.div
                className="absolute top-0 right-0 h-1/2 w-[3px] bg-gradient-to-b from-transparent via-accent to-transparent opacity-70"
                initial={{ filter: "blur(2px)" }}
                animate={{ top: ["-50%", "100%"], opacity: [0.3, 0.7, 0.3], filter: ["blur(1px)", "blur(2.5px)", "blur(1px)"] }}
                transition={{
                  top: { duration: 2.5, ease: "easeInOut", repeat: Infinity, repeatDelay: 1, delay: 0.6 },
                  opacity: { duration: 1.2, repeat: Infinity, repeatType: "mirror", delay: 0.6 },
                  filter: { duration: 1.5, repeat: Infinity, repeatType: "mirror", delay: 0.6 },
                }}
              />
              <motion.div
                className={`${beam} bottom-0 right-0 h-[3px] w-1/2`}
                initial={{ filter: "blur(2px)" }}
                animate={{ right: ["-50%", "100%"], opacity: [0.3, 0.7, 0.3], filter: ["blur(1px)", "blur(2.5px)", "blur(1px)"] }}
                transition={{
                  right: { duration: 2.5, ease: "easeInOut", repeat: Infinity, repeatDelay: 1, delay: 1.2 },
                  opacity: { duration: 1.2, repeat: Infinity, repeatType: "mirror", delay: 1.2 },
                  filter: { duration: 1.5, repeat: Infinity, repeatType: "mirror", delay: 1.2 },
                }}
              />
              <motion.div
                className="absolute bottom-0 left-0 h-1/2 w-[3px] bg-gradient-to-b from-transparent via-accent to-transparent opacity-70"
                initial={{ filter: "blur(2px)" }}
                animate={{ bottom: ["-50%", "100%"], opacity: [0.3, 0.7, 0.3], filter: ["blur(1px)", "blur(2.5px)", "blur(1px)"] }}
                transition={{
                  bottom: { duration: 2.5, ease: "easeInOut", repeat: Infinity, repeatDelay: 1, delay: 1.8 },
                  opacity: { duration: 1.2, repeat: Infinity, repeatType: "mirror", delay: 1.8 },
                  filter: { duration: 1.5, repeat: Infinity, repeatType: "mirror", delay: 1.8 },
                }}
              />

              {/* Corner glow spots */}
              <motion.div className="absolute top-0 left-0 h-[5px] w-[5px] rounded-full bg-white/40 blur-[1px]" animate={{ opacity: [0.2, 0.4, 0.2] }} transition={{ duration: 2, repeat: Infinity, repeatType: "mirror" }} />
              <motion.div className="absolute top-0 right-0 h-2 w-2 rounded-full bg-white/60 blur-[2px]" animate={{ opacity: [0.2, 0.4, 0.2] }} transition={{ duration: 2.4, repeat: Infinity, repeatType: "mirror", delay: 0.5 }} />
              <motion.div className="absolute bottom-0 right-0 h-2 w-2 rounded-full bg-white/60 blur-[2px]" animate={{ opacity: [0.2, 0.4, 0.2] }} transition={{ duration: 2.2, repeat: Infinity, repeatType: "mirror", delay: 1 }} />
              <motion.div className="absolute bottom-0 left-0 h-[5px] w-[5px] rounded-full bg-white/40 blur-[1px]" animate={{ opacity: [0.2, 0.4, 0.2] }} transition={{ duration: 2.3, repeat: Infinity, repeatType: "mirror", delay: 1.5 }} />
            </div>

            <div className="absolute -inset-[0.5px] rounded-2xl bg-gradient-to-r from-white/[0.03] via-white/[0.07] to-white/[0.03] opacity-0 group-hover:opacity-70 transition-opacity duration-500" />

            {/* Glass card */}
            <div className="relative bg-bg/40 backdrop-blur-xl rounded-2xl p-6 border border-white/[0.05] shadow-2xl overflow-hidden">
              <div
                className="absolute inset-0 opacity-[0.03]"
                style={{
                  backgroundImage:
                    "linear-gradient(135deg, white 0.5px, transparent 0.5px), linear-gradient(45deg, white 0.5px, transparent 0.5px)",
                  backgroundSize: "30px 30px",
                }}
              />

              <div className="text-center space-y-1 mb-5">
                <motion.div
                  initial={{ scale: 0.5, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ type: "spring", duration: 0.8 }}
                  className="mx-auto w-10 h-10 rounded-full border border-white/10 flex items-center justify-center relative overflow-hidden"
                >
                  {/* TradeLens rising-candles mark, the site's signature motif */}
                  <svg viewBox="0 0 24 24" className="w-5 h-5" aria-hidden fill="none">
                    <rect x="3" y="13" width="3" height="7" rx="1" className="fill-accent/70" />
                    <rect x="10" y="9" width="3" height="11" rx="1" className="fill-accent/85" />
                    <rect x="17" y="4" width="3" height="16" rx="1" className="fill-accent" />
                  </svg>
                  <div className="absolute inset-0 bg-gradient-to-br from-white/10 to-transparent opacity-50" />
                </motion.div>

                <motion.h1
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.2 }}
                  className="font-display text-xl font-bold bg-clip-text text-transparent bg-gradient-to-b from-white to-white/80"
                >
                  Welcome back
                </motion.h1>

                <motion.p
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.3 }}
                  className="text-muted text-xs"
                >
                  Sign in to review your trades
                </motion.p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                {error && (
                  <p
                    role="alert"
                    className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300"
                  >
                    {error}
                  </p>
                )}

                <motion.div className="space-y-3">
                  <motion.div
                    className={`relative ${focusedInput === "identifier" ? "z-10" : ""}`}
                    whileHover={{ scale: 1.01 }}
                    transition={{ type: "spring", stiffness: 400, damping: 25 }}
                  >
                    <div className="relative flex items-center overflow-hidden rounded-lg">
                      <Mail
                        className={`absolute left-3 w-4 h-4 transition-all duration-300 ${
                          focusedInput === "identifier" ? "text-accent" : "text-muted/60"
                        }`}
                      />
                      <Input
                        name="identifier"
                        autoComplete="username"
                        placeholder="Email or username"
                        aria-label="Email or username"
                        value={identifier}
                        onChange={(e) => setIdentifier(e.target.value)}
                        onFocus={() => setFocusedInput("identifier")}
                        onBlur={() => setFocusedInput(null)}
                        className="w-full bg-white/5 border-transparent focus:border-accent/40 h-10 pl-10 pr-3 focus:bg-white/10 transition-all duration-300"
                      />
                    </div>
                  </motion.div>

                  <motion.div
                    className={`relative ${focusedInput === "password" ? "z-10" : ""}`}
                    whileHover={{ scale: 1.01 }}
                    transition={{ type: "spring", stiffness: 400, damping: 25 }}
                  >
                    <div className="relative flex items-center overflow-hidden rounded-lg">
                      <Lock
                        className={`absolute left-3 w-4 h-4 transition-all duration-300 ${
                          focusedInput === "password" ? "text-accent" : "text-muted/60"
                        }`}
                      />
                      <Input
                        name="password"
                        type={showPassword ? "text" : "password"}
                        autoComplete="current-password"
                        placeholder="Password"
                        aria-label="Password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        onFocus={() => setFocusedInput("password")}
                        onBlur={() => setFocusedInput(null)}
                        className="w-full bg-white/5 border-transparent focus:border-accent/40 h-10 pl-10 pr-10 focus:bg-white/10 transition-all duration-300"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword((v) => !v)}
                        aria-label={showPassword ? "Hide password" : "Show password"}
                        className="absolute right-3 cursor-pointer"
                      >
                        {showPassword ? (
                          <Eye className="w-4 h-4 text-muted/60 hover:text-text transition-colors duration-300" />
                        ) : (
                          <EyeClosed className="w-4 h-4 text-muted/60 hover:text-text transition-colors duration-300" />
                        )}
                      </button>
                    </div>
                  </motion.div>
                </motion.div>

                <div className="flex items-center justify-end pt-1">
                  <Link
                    href="/forgot-password"
                    className="text-xs text-muted hover:text-text transition-colors duration-200"
                  >
                    Forgot password?
                  </Link>
                </div>

                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  type="submit"
                  disabled={isLoading}
                  className="w-full relative group/button mt-5"
                >
                  <div className="absolute inset-0 bg-accent/20 rounded-lg blur-lg opacity-0 group-hover/button:opacity-70 transition-opacity duration-300" />
                  <div className="relative overflow-hidden bg-accent text-bg font-medium h-10 rounded-lg transition-all duration-300 flex items-center justify-center">
                    <motion.div
                      className="absolute inset-0 bg-gradient-to-r from-white/0 via-white/30 to-white/0 -z-10"
                      animate={{ x: ["-100%", "100%"] }}
                      transition={{ duration: 1.5, ease: "easeInOut", repeat: Infinity, repeatDelay: 1 }}
                      style={{ opacity: isLoading ? 1 : 0, transition: "opacity 0.3s ease" }}
                    />
                    <AnimatePresence mode="wait">
                      {isLoading ? (
                        <motion.div key="loading" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex items-center justify-center">
                          <div className="w-4 h-4 border-2 border-bg/70 border-t-transparent rounded-full animate-spin" />
                        </motion.div>
                      ) : (
                        <motion.span key="button-text" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex items-center justify-center gap-1 text-sm font-medium">
                          Sign in
                          <ArrowRight className="w-3 h-3 group-hover/button:translate-x-1 transition-transform duration-300" />
                        </motion.span>
                      )}
                    </AnimatePresence>
                  </div>
                </motion.button>

                {signupEnabled && (
                  <motion.p
                    className="text-center text-xs text-muted mt-4"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.5 }}
                  >
                    Don&apos;t have an account?{" "}
                    <Link href="/signup" className="relative inline-block group/signup">
                      <span className="relative z-10 text-text group-hover/signup:text-accent transition-colors duration-300 font-medium">
                        Sign up
                      </span>
                      <span className="absolute bottom-0 left-0 w-0 h-px bg-accent group-hover/signup:w-full transition-all duration-300" />
                    </Link>
                  </motion.p>
                )}
              </form>

              <p className="mt-5 border-t border-border pt-4 text-center text-[11px] leading-relaxed text-muted">
                <span className="text-text">Reflection only.</span> TradeLens
                reviews the trade you already took. It does not generate signals,
                predictions, or trade advice.
              </p>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

export default SignInCard;
