"use client";

import React from "react";
import { motion, useMotionValue, useTransform } from "framer-motion";

import { cn } from "@/lib/utils";

/**
 * The glass card and its four travelling border beams.
 *
 * Same story as `AuroraBackdrop`: this is the sign-in card's own frame, moved
 * into one file so the rest of the auth flow can wear it instead of a second,
 * slowly-diverging copy. Beam widths, the 2.5s travel, the 0.6/1.2/1.8s
 * stagger, the corner glow spots and the hover gradients are unchanged.
 *
 * `tilt` is opt-in and defaults to off. The 3D mouse-tracked rotation is
 * lovely on a two-field sign-in card, and actively hostile on the signup form,
 * where the page tips under the cursor while someone is aiming at a native date
 * picker or a select. Short cards ask for it; forms do not.
 */
export function GlowFrame({
  children,
  className,
  tilt = false,
}: {
  children: React.ReactNode;
  className?: string;
  tilt?: boolean;
}) {
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);
  const rotateX = useTransform(mouseY, [-300, 300], [10, -10]);
  const rotateY = useTransform(mouseX, [-300, 300], [-10, 10]);

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!tilt) return;
    const rect = e.currentTarget.getBoundingClientRect();
    mouseX.set(e.clientX - rect.left - rect.width / 2);
    mouseY.set(e.clientY - rect.top - rect.height / 2);
  };

  const handleMouseLeave = () => {
    mouseX.set(0);
    mouseY.set(0);
  };

  const beam =
    "absolute bg-gradient-to-r from-transparent via-accent to-transparent opacity-70";

  return (
    <motion.div
      className="relative"
      style={tilt ? { rotateX, rotateY } : undefined}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      whileHover={tilt ? { z: 10 } : undefined}
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
        <div
          className={cn(
            "relative bg-bg/40 backdrop-blur-xl rounded-2xl p-6 border border-white/[0.05] shadow-2xl overflow-hidden",
            className,
          )}
        >
          <div
            aria-hidden
            className="absolute inset-0 opacity-[0.03]"
            style={{
              backgroundImage:
                "linear-gradient(135deg, white 0.5px, transparent 0.5px), linear-gradient(45deg, white 0.5px, transparent 0.5px)",
              backgroundSize: "30px 30px",
            }}
          />
          {/* Above the hatch overlay, which is decorative and inert. */}
          <div className="relative">{children}</div>
        </div>
      </div>
    </motion.div>
  );
}

export default GlowFrame;
