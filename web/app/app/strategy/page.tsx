import { EmptyState } from "@/components/app/states/empty-state";

export default function StrategyPage() {
  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-bold">Strategy Profile</h1>
      <p className="mt-2 text-muted">Your own rules, written down.</p>
      <div className="mt-8">
        <EmptyState
          title="The profile is not migrated yet"
          description="Your markets, setups and risk rules move here in a later phase."
        />
      </div>
    </div>
  );
}
