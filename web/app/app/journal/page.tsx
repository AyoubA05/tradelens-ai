import { EmptyState } from "@/components/app/states/empty-state";

export default function JournalPage() {
  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-bold">Journal</h1>
      <p className="mt-2 text-muted">Find a trade, work a month, or read one closely.</p>
      <div className="mt-8">
        <EmptyState
          title="The journal arrives next"
          description="Trades, the calendar and trade detail move here in the phase after this one."
        />
      </div>
    </div>
  );
}
