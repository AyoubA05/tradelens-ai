/**
 * First thing in the tab order, invisible until focused.
 *
 * Without it a keyboard user tabs through every destination before reaching
 * the page on every navigation.
 */
export function SkipLink() {
  return (
    <a
      href="#main-content"
      className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-surface-2 focus:px-4 focus:py-2 focus:text-sm focus:text-text"
    >
      Skip to main content
    </a>
  );
}
