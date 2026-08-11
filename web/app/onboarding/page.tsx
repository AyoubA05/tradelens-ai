import { AuthShell } from "@/components/auth-shell";

/**
 * Personal onboarding closes out on the website; the Strategy Profile does NOT
 * live here. That step stays in Streamlit, gated on strategy_profile_completed,
 * because it reuses the existing Strategy Profile service and its twelve fields.
 *
 * In the approved flow the personal details are collected during signup, so
 * this route exists as the confirmation and handoff point rather than a second
 * form. The handoff itself is a later increment.
 */
export default function OnboardingPage() {
  return (
    <AuthShell
      title="You're all set"
      intro="Your account is ready. Next you'll tell the AI how you trade — that happens inside your journal."
    >
      <div className="space-y-4">
        <ol className="space-y-2.5 text-sm text-muted">
          <li className="flex gap-2.5"><span className="text-accent">1.</span> Account created</li>
          <li className="flex gap-2.5"><span className="text-accent">2.</span> Email verified</li>
          <li className="flex gap-2.5"><span className="text-text">3.</span> Set up your Strategy Profile in the journal</li>
        </ol>
        <button
          type="button"
          disabled
          className="h-10 w-full rounded-lg bg-accent/40 text-sm font-medium text-bg/70 cursor-not-allowed"
        >
          Open my journal
        </button>
        <p className="text-center text-[11.5px] text-muted">
          The secure handoff into the journal is not connected yet — it ships in a
          later increment.
        </p>
      </div>
    </AuthShell>
  );
}
