import Link from "next/link";

export const REVIEW_LENSES = [
  { id: "patterns", label: "Patterns", question: "What keeps repeating in the journal?" },
  { id: "weekly", label: "Weekly Recap", question: "How did the completed week go?" },
  { id: "daily", label: "Daily Debrief", question: "What happened on one trading day?" },
] as const;

export type ReviewLensId = (typeof REVIEW_LENSES)[number]["id"];

export function reviewLensFrom(value: string | undefined): ReviewLensId {
  return REVIEW_LENSES.some((lens) => lens.id === value) ? (value as ReviewLensId) : "patterns";
}

/**
 * The three-lens selector.
 *
 * Real links: the lens belongs in the URL so it survives a refresh and the
 * back button. Following one only navigates — opening a lens never starts a
 * review.
 */
export function LensTabs({ active }: { active: ReviewLensId }) {
  return (
    <nav aria-label="Review lenses" className="mt-6 border-b border-line">
      <div role="tablist" className="-mb-px flex flex-wrap gap-1">
        {REVIEW_LENSES.map((lens) => {
          const isActive = lens.id === active;
          return (
            <Link
              key={lens.id}
              href={`/app/reviews?lens=${lens.id}`}
              role="tab"
              aria-selected={isActive}
              className={`inline-flex min-h-11 items-center rounded-t-lg border-b-2 px-3 py-2 text-sm transition-colors duration-150 ease-tl ${
                isActive
                  ? "border-accent font-semibold text-text"
                  : "border-transparent font-medium text-muted hover:text-text"
              }`}
            >
              {lens.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
