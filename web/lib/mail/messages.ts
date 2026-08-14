import "server-only";

/**
 * The transactional emails.
 *
 * Both messages exist for one reason: to carry a single credential to the
 * address that asked for it. Everything else they contain is there to help the
 * recipient decide whether they asked.
 *
 * **What is deliberately absent.** No internal username, no account id, no
 * password, no password hash, no session or handoff credential, and no
 * "account details" summary. Email is stored in plain text on servers neither
 * end controls, forwarded, and indexed by clients; the only secret worth that
 * exposure is the one the recipient needs to act, and it expires.
 *
 * **Links are built from SITE_ORIGIN, never APP_ORIGIN.** Verification and
 * reset are website flows. Pointing either at the Streamlit origin would send
 * the credential to a host with no route to consume it — and would train users
 * that a TradeLens auth link can legitimately arrive on a streamlit.app domain,
 * which is a phishing lesson worth not teaching.
 *
 * Each message is plain text plus a matching HTML alternative. The URL appears
 * once in the text part, so a client that strips HTML still shows a usable
 * link, and the capture transport can find it.
 */

import type { MailMessage } from "@/lib/mail/transport";

const BRAND = "TradeLens AI";
const TAGLINE = "Your post-trade reflection journal.";

/** Minimal escaping for the few interpolations that reach the HTML part. */
function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * One layout for both messages.
 *
 * Inline styles only, no external stylesheet, no remote image: mail clients
 * strip `<style>` blocks and block remote content by default, and a tracking
 * pixel on a password-reset email is not something to add by accident.
 */
function layout(options: {
  heading: string;
  body: string[];
  action: string;
  url: string;
  footer: string[];
}): string {
  const paragraphs = options.body
    .map(
      (line) =>
        `<p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#1f2933;">${escapeHtml(line)}</p>`,
    )
    .join("");
  const footer = options.footer
    .map(
      (line) =>
        `<p style="margin:0 0 8px;font-size:13px;line-height:1.5;color:#6b7280;">${escapeHtml(line)}</p>`,
    )
    .join("");
  const href = escapeHtml(options.url);

  return [
    '<div style="margin:0;padding:24px;background:#f5f7f8;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Helvetica,Arial,sans-serif;">',
    '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="max-width:520px;margin:0 auto;background:#ffffff;border-radius:12px;border:1px solid #e3e8ea;">',
    '<tr><td style="padding:28px 28px 0;">',
    `<p style="margin:0;font-size:17px;font-weight:600;color:#0f766e;">${BRAND}</p>`,
    `<p style="margin:4px 0 0;font-size:13px;color:#6b7280;">${TAGLINE}</p>`,
    "</td></tr>",
    '<tr><td style="padding:24px 28px 8px;">',
    `<h1 style="margin:0 0 16px;font-size:20px;line-height:1.3;color:#0b1f24;">${escapeHtml(options.heading)}</h1>`,
    paragraphs,
    `<p style="margin:24px 0;"><a href="${href}" style="display:inline-block;padding:12px 22px;background:#0f766e;color:#ffffff;text-decoration:none;border-radius:8px;font-size:15px;font-weight:600;">${escapeHtml(options.action)}</a></p>`,
    '<p style="margin:0 0 8px;font-size:13px;color:#6b7280;">If the button does not work, paste this into your browser:</p>',
    `<p style="margin:0 0 20px;font-size:13px;word-break:break-all;"><a href="${href}" style="color:#0f766e;">${href}</a></p>`,
    "</td></tr>",
    '<tr><td style="padding:0 28px 28px;border-top:1px solid #eef2f3;padding-top:16px;">',
    footer,
    "</td></tr>",
    "</table></div>",
  ].join("");
}

/**
 * Confirm an email address.
 *
 * The 24-hour expiry is stated because a link that quietly stops working reads
 * as a broken product rather than an expired credential.
 */
export function verificationMessage(to: string, url: string): MailMessage {
  const body = [
    "Confirm this address to open your TradeLens AI journal.",
  ];
  const footer = [
    "This link expires in 24 hours and can be used once.",
    "If you did not create a TradeLens AI account, ignore this message — nothing will happen.",
  ];
  return {
    to,
    subject: "Verify your email for TradeLens AI",
    text: [...body, "", url, "", ...footer].join("\n"),
    html: layout({
      heading: "Verify your email",
      body,
      action: "Verify my email",
      url,
      footer,
    }),
  };
}

/**
 * Reset a password.
 *
 * Sent only to an address that already exists and is verified — but the
 * recipient cannot know that, so the copy is written for the case where they
 * did not ask, and says plainly that ignoring it changes nothing.
 */
export function passwordResetMessage(to: string, url: string): MailMessage {
  const body = [
    "Someone asked to reset the password on your TradeLens AI account.",
    "Choose a new one here:",
  ];
  const footer = [
    "This link expires in 30 minutes and can be used once.",
    "If it was not you, ignore this message — your password has not changed and no one can sign in with this link once it expires.",
  ];
  return {
    to,
    subject: "Reset your TradeLens AI password",
    text: [...body, "", url, "", ...footer].join("\n"),
    html: layout({
      heading: "Reset your password",
      body,
      action: "Choose a new password",
      url,
      footer,
    }),
  };
}
