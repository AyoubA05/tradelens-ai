import { EmptyState } from "@/components/app/states/empty-state";

export default function SettingsPage() {
  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-bold">Settings</h1>
      <p className="mt-2 text-muted">Your account, your data, and how the app reads it.</p>
      <div className="mt-8">
        <EmptyState
          title="Settings are not migrated yet"
          description="Recovery email, timezone, import and export move here in a later phase."
        />
      </div>
    </div>
  );
}
