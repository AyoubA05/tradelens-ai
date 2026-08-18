import { EmptyState } from "@/components/app/states/empty-state";

export default function ReviewsPage() {
  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-bold">AI Reviews</h1>
      <p className="mt-2 text-muted">Evidence-backed reading of your own journal.</p>
      <div className="mt-8">
        <EmptyState
          title="Reviews are not migrated yet"
          description="Patterns, the weekly recap and the daily debrief move here after the journal."
        />
      </div>
    </div>
  );
}
