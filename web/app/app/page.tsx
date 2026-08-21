import { EmptyState } from "@/components/app/states/empty-state";

export default function OverviewPage() {
  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-bold">Overview</h1>
      <p className="mt-2 text-muted">Where the week stands, and what deserves review next.</p>
      <div className="mt-8">
        <EmptyState
          title="The dashboard arrives next"
          description="Your KPI row, equity curve and recent trades move here in the phase after this one."
        />
      </div>
    </div>
  );
}
