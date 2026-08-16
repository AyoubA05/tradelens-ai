import "server-only";

/**
 * Mail delivery.
 *
 * The point of this abstraction is that the application can tell the difference
 * between three states that are easy to conflate — and must never be reported
 * as "sent":
 *
 *   sent         the transport accepted the message
 *   unavailable  no transport is configured; nothing was attempted
 *   failed       a transport was configured and rejected or errored
 *
 * The distinction matters because an account whose verification mail silently
 * failed would otherwise sit waiting for a message that does not exist.
 *
 * The raw verification URL passes through here and stops here. It is never
 * logged, never written to a file, and never returned to a caller — except by
 * the capture transport, which exists only for tests.
 */

export type MailMessage = {
  to: string;
  subject: string;
  text: string;
  /** Optional HTML alternative. The plain text part is always sent. */
  html?: string;
};

export type DeliveryOutcome =
  | { status: "sent" }
  | { status: "unavailable"; reason: "not_configured" }
  | { status: "failed" };

export interface MailTransport {
  send(message: MailMessage): Promise<DeliveryOutcome>;
}

/**
 * Hosts allowed to receive mail over an unencrypted connection.
 *
 * The exception is loopback and nothing else, matched exactly rather than by
 * prefix — `localhost.attacker.example` is not localhost. Everything else must
 * negotiate TLS, and a server that will not is a failure, not a fallback:
 * silently downgrading would put a password-reset link on the wire in clear
 * text, which is the one thing the link's 30-minute TTL cannot protect against.
 */
const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);

export function isLoopbackHost(host: string): boolean {
  return LOOPBACK_HOSTS.has(host.trim().toLowerCase());
}

export type SmtpSettings = {
  host: string;
  port: number;
  from: string;
  user?: string;
  password?: string;
  /** Implicit TLS on connect (port 465). Otherwise STARTTLS is required. */
  secure: boolean;
  requireTls: boolean;
};

/**
 * Read and validate the SMTP settings, or return null when unconfigured.
 *
 * Returns the values; never logs them. An invalid port is treated as
 * unconfigured rather than coerced — mail sent to port `NaN` is not a thing to
 * guess about.
 */
export function smtpSettings(): SmtpSettings | null {
  const host = process.env.TRADELENS_SMTP_HOST?.trim();
  const from = process.env.TRADELENS_SMTP_FROM?.trim();
  if (!host || !from) return null;

  const rawPort = process.env.TRADELENS_SMTP_PORT?.trim() || "587";
  const port = Number(rawPort);
  if (!Number.isInteger(port) || port <= 0 || port > 65535) return null;

  return {
    host,
    port,
    from,
    user: process.env.TRADELENS_SMTP_USER || undefined,
    password: process.env.TRADELENS_SMTP_PASSWORD || undefined,
    secure: port === 465,
    requireTls: !isLoopbackHost(host),
  };
}

/**
 * Production transport: real outbound delivery over SMTP.
 *
 * Three properties are deliberate.
 *
 * **Unconfigured is `unavailable`, not `failed` and never `sent`.** A caller
 * can then keep the account in a recoverable unverified state and offer a
 * resend, instead of leaving someone waiting for a message that was never
 * attempted.
 *
 * **Errors are swallowed into `failed`.** An SMTP rejection carries the server
 * banner, the envelope, sometimes the recipient and occasionally the
 * credentials that were refused. None of that may reach a log line or an HTTP
 * response, so the error object stops here and the caller learns only that
 * delivery did not happen. The name of the error class is the single detail
 * kept, because "which kind of failure" is diagnosable without being
 * reusable.
 *
 * **Nothing about the message body is logged.** The verification and reset
 * URLs pass through this method and go no further.
 */
export class SmtpTransport implements MailTransport {
  async send(message: MailMessage): Promise<DeliveryOutcome> {
    const settings = smtpSettings();
    if (!settings) {
      return { status: "unavailable", reason: "not_configured" };
    }

    try {
      // Imported lazily so the module graph of a request that sends no mail
      // does not pull in an SMTP client.
      const nodemailer = (await import("nodemailer")).default;
      const transporter = nodemailer.createTransport({
        host: settings.host,
        port: settings.port,
        secure: settings.secure,
        // Refuse to deliver in clear text off loopback. `requireTLS` upgrades
        // via STARTTLS and errors if the server does not offer it.
        requireTLS: settings.requireTls,
        auth:
          settings.user && settings.password
            ? { user: settings.user, pass: settings.password }
            : undefined,
        tls: { rejectUnauthorized: settings.requireTls },
      });

      await transporter.sendMail({
        from: settings.from,
        to: message.to,
        subject: message.subject,
        text: message.text,
        html: message.html,
      });
      return { status: "sent" };
    } catch (error) {
      // Name only. See the class docstring for why the rest is dropped.
      console.warn(
        `mail: delivery failed (${(error as Error)?.name ?? "Error"})`,
      );
      return { status: "failed" };
    }
  }
}

/**
 * Test transport. Captures messages in memory so a test can read the
 * verification URL it would have emailed.
 *
 * Only ever constructed by tests and the dev integration script — never
 * selected by `mailTransport()`, so it cannot leak into a running server.
 */
export class CaptureTransport implements MailTransport {
  readonly sent: MailMessage[] = [];

  async send(message: MailMessage): Promise<DeliveryOutcome> {
    this.sent.push(message);
    return { status: "sent" };
  }

  /** The most recent message, or undefined. */
  last(): MailMessage | undefined {
    return this.sent[this.sent.length - 1];
  }

  /** Pull the verification URL out of the most recent message. */
  lastVerificationUrl(): string | undefined {
    const match = this.last()?.text.match(/https?:\/\/\S+\/verify-email\?token=\S+/);
    return match?.[0];
  }

  /** Pull the password-reset URL out of the most recent message. */
  lastResetUrl(): string | undefined {
    const match = this.last()?.text.match(/https?:\/\/\S+\/reset-password\?token=\S+/);
    return match?.[0];
  }

  clear(): void {
    this.sent.length = 0;
  }
}

/** A transport that always fails, for exercising the failure path. */
export class FailingTransport implements MailTransport {
  async send(message: MailMessage): Promise<DeliveryOutcome> {
    void message;
    return { status: "failed" };
  }
}

let override: MailTransport | null = null;

/** Inject a transport. Tests and the dev integration script only. */
export function setMailTransport(transport: MailTransport | null): void {
  override = transport;
}

export function mailTransport(): MailTransport {
  return override ?? new SmtpTransport();
}

// The message bodies live in lib/mail/messages.ts. This module is the wire.
