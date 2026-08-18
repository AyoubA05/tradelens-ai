import type { ReactNode } from "react";

import { SkipLink } from "@/components/app/skip-link";

/**
 * The frame every authenticated screen renders inside.
 *
 * It takes its regions as props rather than importing them, so it stays a
 * layout with no opinion about navigation, and so a test can render it without
 * a router.
 *
 * The sidebar is hidden below `lg` and the bottom bar above it — one of the two
 * is always present, never both, so there is a single navigation in the
 * accessibility tree at any width.
 */
export function AppShell({
  sidebar,
  top,
  drawer,
  bottomNav,
  children,
}: {
  sidebar: ReactNode;
  top: ReactNode;
  drawer: ReactNode;
  bottomNav: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="min-h-dvh bg-bg text-text">
      <SkipLink />
      <div className="lg:grid lg:grid-cols-[16rem_1fr]">
        <div className="hidden lg:block">{sidebar}</div>
        <div className="flex min-h-dvh flex-col">
          {top}
          {/*
            tabIndex -1 so the skip link actually moves focus here. Without it
            the fragment scrolls but focus stays put, and the next Tab walks
            back into the navigation the user just skipped.
            pb-20 on phones clears the fixed bottom bar.
          */}
          <main
            id="main-content"
            tabIndex={-1}
            className="flex-1 px-4 pb-20 pt-6 focus:outline-none sm:px-6 lg:px-8 lg:pb-10"
          >
            {children}
          </main>
        </div>
      </div>
      {drawer}
      <div className="lg:hidden">{bottomNav}</div>
    </div>
  );
}
