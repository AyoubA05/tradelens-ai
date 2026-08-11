import * as React from "react";
import { cn } from "@/lib/utils";

/** shadcn-style input, retoned for the TradeLens dark surface. */
export function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "flex h-9 w-full min-w-0 rounded-md border border-border bg-transparent px-3 py-1",
        "text-base text-text placeholder:text-muted/60 shadow-sm outline-none",
        "transition-[color,box-shadow] md:text-sm",
        "disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
        "focus-visible:border-accent focus-visible:ring-[3px] focus-visible:ring-accent/40",
        "aria-invalid:border-red-500 aria-invalid:ring-red-500/30",
        className,
      )}
      {...props}
    />
  );
}
