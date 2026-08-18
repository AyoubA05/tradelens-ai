import { EmptyState } from "@/components/app/states/empty-state";

export default function NewTradePage() {
  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-bold">Log completed trade</h1>
      <p className="mt-2 text-muted">Five steps. Your draft is kept as you move between them.</p>
      <div className="mt-8">
        <EmptyState
          title="The form is not migrated yet"
          description="Screenshot upload, AI autofill and the review step move here in a later phase."
        />
      </div>
    </div>
  );
}
