import { EmptyState } from "@/components/app/states/empty-state";

/**
 * Rendered by `notFound()` in `page.tsx`.
 *
 * `GET /v1/trades/{id}` returns 404 byte-identical for "not yours" and
 * "does not exist" (Task A3) so a stranger cannot use the response to learn
 * whether a given id belongs to someone. This copy preserves that on the
 * UI side too — it never says or implies "you don't have permission,"
 * which would itself confirm the row exists.
 */
export default function TradeNotFound() {
  return (
    <div className="mx-auto max-w-6xl pt-6">
      <EmptyState
        title="Trade not found"
        description="It may have been deleted, or the link may be incorrect."
        action={{ href: "/app/journal", label: "Back to journal" }}
      />
    </div>
  );
}
