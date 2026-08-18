import {
  BookOpen,
  BarChart3,
  Brain,
  Flag,
  LayoutDashboard,
  Settings,
  type LucideIcon,
} from "lucide-react";

/**
 * The product's information architecture, in one place.
 *
 * The sidebar, the phone bar and the overflow sheet all read this array, so
 * they cannot drift into three different ideas of what the app contains.
 *
 * The six destinations are deliberately the same six the Streamlit journal
 * had. Moving the visual system and the navigation in one step would make any
 * regression unattributable — a complaint could mean "you moved my thing" or
 * "you broke my thing", and there would be no way to tell which.
 */
export type AppDestination = {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Shown in the phone bar rather than behind More. */
  phonePriority: boolean;
};

export const APP_DESTINATIONS: AppDestination[] = [
  { href: "/app", label: "Overview", icon: LayoutDashboard, phonePriority: true },
  { href: "/app/journal", label: "Journal", icon: BookOpen, phonePriority: true },
  { href: "/app/analytics", label: "Analytics", icon: BarChart3, phonePriority: false },
  { href: "/app/reviews", label: "AI Reviews", icon: Brain, phonePriority: true },
  { href: "/app/strategy", label: "Strategy Profile", icon: Flag, phonePriority: false },
  { href: "/app/settings", label: "Settings", icon: Settings, phonePriority: true },
];

/**
 * Logging a trade is an action, not a place. It keeps its own affordance at the
 * top of the sidebar instead of sitting in the list, because it is the one
 * thing a trader comes here to do that is not reading.
 */
export const PRIMARY_ACTION = {
  href: "/app/trades/new",
  label: "Log completed trade",
};

/**
 * Whether `href` is the destination currently being viewed.
 *
 * Overview is matched exactly. Every other destination also matches its own
 * children, so a trade detail page keeps Journal lit. Without the exact case
 * for "/app", a prefix match would light Overview up on every screen in the
 * product, and the boundary check stops "/app/journalling" matching
 * "/app/journal".
 */
export function isActiveDestination(pathname: string, href: string): boolean {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  if (href === "/app") return path === "/app";
  return path === href || path.startsWith(`${href}/`);
}
