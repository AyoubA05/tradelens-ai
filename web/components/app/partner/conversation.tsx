"use client";

import { useRef, useState } from "react";

import {
  applyReply,
  EMPTY_CONVERSATION,
  failureMessage,
  newClientTurnId,
  type PartnerConversation,
  type PartnerFailure,
  type PartnerReply,
} from "@/lib/app/partner-conversation";

/**
 * One partner conversation — the global one in the drawer, or one about a
 * single trade in the trade panel. Same component, different endpoint.
 *
 * Three things this does NOT do, each deliberate:
 *
 * 1. It does not stream. The whole answer is checked against the scope guard
 *    server-side before any of it is shown, and a guard that runs after the
 *    trader has read the text is not a guard.
 * 2. It does not let a sent question be edited. Every turn is signed; an
 *    edited transcript is refused, so an edit affordance would only produce
 *    a 409 the trader could not act on.
 * 3. It does not retry on its own. Each turn is a paid model call, and a
 *    retry the trader did not ask for is money they did not agree to spend.
 *    "Ask that again" is a NEW attempt with a fresh client turn id (plan D5):
 *    the server refuses a failed attempt's id for good, so reusing it would
 *    jam the conversation. A double-click is stopped before it is sent.
 */

export type PartnerConversationProps = {
  /** The relay path — the trade, when there is one, is in the path. */
  endpoint: string;
  /** Ask the server to attach this trade's own screenshot. Never an id. */
  includeScreenshot?: boolean;
  /** What the empty conversation says it is for. */
  intro: string;
  placeholder: string;
};

const MAX_QUESTION_CHARS = 2000;

export function PartnerConversation({
  endpoint,
  includeScreenshot,
  intro,
  placeholder,
}: PartnerConversationProps) {
  const [conversation, setConversation] =
    useState<PartnerConversation>(EMPTY_CONVERSATION);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<PartnerFailure | null>(null);
  // Set synchronously on the first click, so a second click in the same frame
  // is refused here rather than sent. `pending` is state and would only be
  // seen by the NEXT render — both clicks would pass a check on it.
  const inFlight = useRef(false);
  // The question the last attempt carried, so "Ask that again" re-sends that
  // question — never whatever is in the box by the time the trader clicks.
  const lastAsked = useRef("");

  const ended = failure?.endsConversation ?? false;

  async function ask(text: string) {
    if (!text.trim() || inFlight.current) return;
    inFlight.current = true;
    lastAsked.current = text;
    // A fresh id for EVERY attempt (plan D5). The server keeps an attempt's
    // ticket after it fails and answers that id with `duplicate_turn` from
    // then on, so an id reused for a retry — or for the next question — is
    // refused forever and the conversation jams. Double-submits are stopped
    // by `inFlight` above; the server's duplicate check still covers two
    // tabs racing one id.
    const clientTurnId = newClientTurnId();
    setPending(true);
    setFailure(null);
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          question: text,
          conversation_id: conversation.conversationId,
          transcript: conversation.turns,
          client_turn_id: clientTurnId,
          ...(includeScreenshot === undefined
            ? {}
            : { include_screenshot: includeScreenshot }),
        }),
      });

      if (response.ok) {
        const reply = (await response.json()) as PartnerReply;
        const next = applyReply(conversation, reply);
        if (next === null) {
          // The server answered about a conversation this tab does not have.
          // Every later turn built on the local copy would be refused, so it
          // is retired here rather than silently repaired.
          setFailure(failureMessage(409, "transcript_invalid"));
          return;
        }
        setConversation(next);
        // Only the question that was answered leaves the box. A retry of an
        // earlier question must not wipe what the trader has typed since.
        setDraft((current) => (current === text ? "" : current));
        return;
      }

      const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
      setFailure(failureMessage(response.status, body.detail));
    } catch {
      // A dropped connection may still have been answered and billed; the
      // trader decides whether to ask again, and that attempt is a new one.
      setFailure(failureMessage(0, null));
    } finally {
      inFlight.current = false;
      setPending(false);
    }
  }

  function startOver() {
    setConversation(EMPTY_CONVERSATION);
    setFailure(null);
    setDraft("");
    lastAsked.current = "";
  }

  return (
    <div data-testid="partner-conversation" className="flex flex-1 flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {conversation.turns.length === 0 ? (
          <p className="text-sm text-muted">{intro}</p>
        ) : (
          <ol className="flex flex-col gap-4">
            {conversation.turns.map((turn) => (
              <li
                key={turn.mac}
                data-testid={`partner-turn-${turn.role}`}
                className={
                  turn.role === "user"
                    ? "self-end rounded-lg rounded-br-sm bg-surface-2 px-3 py-2 text-sm text-text"
                    : "rounded-lg rounded-bl-sm border border-line px-3 py-2 text-sm text-text"
                }
              >
                <span className="sr-only">
                  {turn.role === "user" ? "You asked:" : "The partner answered:"}
                </span>
                <p className="whitespace-pre-wrap">{turn.text}</p>
              </li>
            ))}
          </ol>
        )}

        {conversation.evidence.length > 0 ? (
          <div data-testid="partner-evidence" className="mt-4 border-t border-line pt-3">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">
              What this answer read
            </h3>
            <ul className="mt-2 flex flex-col gap-1">
              {conversation.evidence.map((source, i) => (
                <li key={`${source.kind}-${source.trade_id ?? i}`} className="text-xs text-muted">
                  {source.trade_id === null ? (
                    source.label
                  ) : (
                    <a
                      href={`/app/trades/${source.trade_id}`}
                      className="underline underline-offset-2 hover:text-text"
                    >
                      {source.label}
                    </a>
                  )}
                  {source.occurred_on ? ` · ${source.occurred_on}` : ""}
                </li>
              ))}
            </ul>
            {conversation.screenshotAttached ? (
              <p className="mt-2 text-xs text-muted">Your screenshot for this trade.</p>
            ) : null}
          </div>
        ) : null}

        <p aria-live="polite" className="mt-3 text-sm">
          {pending ? <span className="text-muted">Thinking…</span> : null}
          {failure ? <span className="text-negative">{failure.text}</span> : null}
        </p>

        {failure && !ended ? (
          <button
            type="button"
            // Read in the handler, not during render: the retry re-sends the
            // question that failed, not whatever is in the box now.
            onClick={() => ask(lastAsked.current)}
            disabled={pending}
            className="mt-2 min-h-[44px] rounded-lg border border-line-strong px-3 py-1.5 text-sm text-text transition-colors duration-150 ease-tl hover:bg-surface-2 disabled:opacity-60"
          >
            Ask that again
          </button>
        ) : null}

        {ended ? (
          <button
            type="button"
            onClick={startOver}
            className="mt-2 min-h-[44px] rounded-lg border border-line-strong px-3 py-1.5 text-sm text-text transition-colors duration-150 ease-tl hover:bg-surface-2"
          >
            Start a new conversation
          </button>
        ) : null}
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void ask(draft);
        }}
        className="border-t border-line px-5 py-4"
      >
        <label htmlFor="partner-question" className="sr-only">
          Ask the partner about a trade you have logged
        </label>
        <textarea
          id="partner-question"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          maxLength={MAX_QUESTION_CHARS}
          rows={3}
          disabled={ended}
          placeholder={placeholder}
          className="w-full resize-none rounded-lg border border-line bg-bg px-3 py-2 text-sm text-text placeholder:text-muted focus:border-line-strong focus:outline-none disabled:opacity-60"
        />
        <div className="mt-2 flex items-center justify-between">
          <span className="text-xs text-muted">
            {`${draft.length} / ${MAX_QUESTION_CHARS}`}
          </span>
          <button
            type="submit"
            disabled={pending || ended || !draft.trim()}
            className="min-h-[44px] rounded-lg border border-line-strong px-4 py-1.5 text-sm text-text transition-colors duration-150 ease-tl hover:bg-surface-2 disabled:opacity-60"
          >
            {pending ? "Asking…" : "Ask"}
          </button>
        </div>
      </form>
    </div>
  );
}
