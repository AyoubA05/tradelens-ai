import { EmptyState } from "@/components/app/states/empty-state";

export default function AnalyticsPage() {
  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-bold">Analytics</h1>
      <p className="mt-2 text-muted">One question at a time, with the evidence behind the answer.</p>
      <div className="mt-8">
        <EmptyState
          title="Analytics is not migrated yet"
          description="The four lenses and their charts move here once the journal is in place."
        />
      </div>
    </div>
  );
}
