"use client";

import { useEffect, useRef } from "react";

/**
 * Submits a form once, on mount.
 *
 * This exists so a returning user is not made to click "Continue to your
 * journal" on every sign-in. It is a client effect on purpose, and it is the
 * only way to skip that screen without breaking the rule the handoff endpoint
 * is built on: **rendering must never mint a credential.** Redirecting from
 * the server, or turning the button into a link, would issue a token on
 * prefetch, on a crawler visit and on every refresh — and since only one
 * handoff per user stays redeemable, a prefetch would invalidate the token the
 * user was about to use. An effect runs for a real person in a real browser
 * and for nothing else.
 *
 * `requestSubmit`, not `submit`: it runs validation and fires the submit event
 * the way a click does, so the form behaves identically whether the person
 * pressed the button or this did.
 *
 * The guard ref matters in development, where React's strict mode mounts
 * effects twice — two POSTs would mint two tokens and the first would be dead
 * on arrival.
 */
export function AutoSubmit({ formId }: { formId: string }) {
  const fired = useRef(false);

  useEffect(() => {
    if (fired.current) return;
    fired.current = true;
    const form = document.getElementById(formId);
    if (form instanceof HTMLFormElement) form.requestSubmit();
  }, [formId]);

  return null;
}

export default AutoSubmit;
