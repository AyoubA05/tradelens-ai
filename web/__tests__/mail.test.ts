import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Mail: the transport's honesty properties, its TLS floor, and what the two
 * transactional messages are allowed to contain.
 *
 * The interesting tests here are the negative ones. A template test that only
 * checks the link is present would pass on a message that also leaked the
 * account's internal username, and a transport test that only checks the happy
 * path would pass on one that reports "sent" for a connection that never
 * opened.
 */

const sendMail = vi.fn();
// Typed parameter, not an inferred zero-arg mock: without it the call-args
// tuple types as `[]` and every assertion about what was passed to nodemailer
// fails typecheck while the suite still goes green.
const createTransport = vi.fn((options: Record<string, unknown>) => {
  void options;
  return { sendMail };
});

vi.mock("nodemailer", () => ({
  default: { createTransport },
}));

import {
  CaptureTransport,
  FailingTransport,
  SmtpTransport,
  isLoopbackHost,
  smtpSettings,
} from "@/lib/mail/transport";
import {
  passwordResetMessage,
  verificationMessage,
} from "@/lib/mail/messages";

const SMTP_KEYS = [
  "TRADELENS_SMTP_HOST",
  "TRADELENS_SMTP_PORT",
  "TRADELENS_SMTP_USER",
  "TRADELENS_SMTP_PASSWORD",
  "TRADELENS_SMTP_FROM",
] as const;

let saved: Record<string, string | undefined> = {};

beforeEach(() => {
  saved = {};
  for (const key of SMTP_KEYS) {
    saved[key] = process.env[key];
    delete process.env[key];
  }
  sendMail.mockReset().mockResolvedValue({ accepted: ["a@b.co"] });
  createTransport.mockClear();
});

afterEach(() => {
  for (const key of SMTP_KEYS) {
    if (saved[key] === undefined) delete process.env[key];
    else process.env[key] = saved[key];
  }
});

function configure(overrides: Partial<Record<string, string>> = {}) {
  process.env.TRADELENS_SMTP_HOST = "smtp.example.test";
  process.env.TRADELENS_SMTP_PORT = "587";
  process.env.TRADELENS_SMTP_FROM = "TradeLens AI <no-reply@tradelensai.io>";
  for (const [key, value] of Object.entries(overrides)) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
}

const MESSAGE = { to: "trader@example.test", subject: "s", text: "t" };

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

describe("smtpSettings", () => {
  it("is null when unconfigured", () => {
    expect(smtpSettings()).toBeNull();
  });

  it("is null with a host but no from address", () => {
    process.env.TRADELENS_SMTP_HOST = "smtp.example.test";
    expect(smtpSettings()).toBeNull();
  });

  it("treats an unparseable port as unconfigured rather than guessing", () => {
    configure({ TRADELENS_SMTP_PORT: "not-a-port" });
    expect(smtpSettings()).toBeNull();
  });

  it("rejects a port outside the valid range", () => {
    configure({ TRADELENS_SMTP_PORT: "99999" });
    expect(smtpSettings()).toBeNull();
  });

  it("defaults to submission port 587", () => {
    configure({ TRADELENS_SMTP_PORT: undefined });
    expect(smtpSettings()?.port).toBe(587);
  });

  it("uses implicit TLS on 465", () => {
    configure({ TRADELENS_SMTP_PORT: "465" });
    expect(smtpSettings()?.secure).toBe(true);
  });

  it("requires TLS for a remote host", () => {
    configure();
    expect(smtpSettings()?.requireTls).toBe(true);
  });

  it("allows plaintext for loopback only", () => {
    configure({ TRADELENS_SMTP_HOST: "127.0.0.1", TRADELENS_SMTP_PORT: "1025" });
    expect(smtpSettings()?.requireTls).toBe(false);
  });

  it("does not treat a lookalike hostname as loopback", () => {
    // The exception is loopback, matched exactly. A prefix or suffix test would
    // let an attacker-controlled domain opt out of encryption.
    expect(isLoopbackHost("localhost.attacker.example")).toBe(false);
    expect(isLoopbackHost("notlocalhost")).toBe(false);
    expect(isLoopbackHost("127.0.0.1.example.test")).toBe(false);
    expect(isLoopbackHost("LOCALHOST")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Delivery
// ---------------------------------------------------------------------------

describe("SmtpTransport", () => {
  it("reports unavailable — never sent — when unconfigured", async () => {
    const outcome = await new SmtpTransport().send(MESSAGE);
    expect(outcome).toEqual({ status: "unavailable", reason: "not_configured" });
    expect(createTransport).not.toHaveBeenCalled();
  });

  it("sends through the configured server", async () => {
    configure();
    const outcome = await new SmtpTransport().send(MESSAGE);

    expect(outcome).toEqual({ status: "sent" });
    const options = createTransport.mock.calls[0][0];
    expect(options.host).toBe("smtp.example.test");
    expect(options.port).toBe(587);
    expect(options.secure).toBe(false);
    expect(options.requireTLS).toBe(true);
    expect(sendMail).toHaveBeenCalledTimes(1);
  });

  it("omits auth entirely when no credentials are configured", async () => {
    configure();
    await new SmtpTransport().send(MESSAGE);
    const options = createTransport.mock.calls[0][0];
    expect(options.auth).toBeUndefined();
  });

  it("authenticates when both a user and a password are configured", async () => {
    configure({
      TRADELENS_SMTP_USER: "apikey",
      TRADELENS_SMTP_PASSWORD: "s3cret",
    });
    await new SmtpTransport().send(MESSAGE);
    const options = createTransport.mock.calls[0][0];
    expect(options.auth).toEqual({ user: "apikey", pass: "s3cret" });
  });

  it("reports failed — never sent — when the server rejects", async () => {
    configure();
    sendMail.mockRejectedValueOnce(new Error("550 mailbox unavailable"));
    const outcome = await new SmtpTransport().send(MESSAGE);
    expect(outcome).toEqual({ status: "failed" });
  });

  it("keeps the server's error text out of the log", async () => {
    configure({ TRADELENS_SMTP_PASSWORD: "s3cret" });
    const banner = "535 auth failed for apikey with password s3cret";
    sendMail.mockRejectedValueOnce(new Error(banner));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});

    await new SmtpTransport().send(MESSAGE);

    const logged = warn.mock.calls.flat().join(" ");
    expect(logged).not.toContain("s3cret");
    expect(logged).not.toContain(banner);
    expect(logged).toContain("Error");
    warn.mockRestore();
  });
});

describe("test transports stay separate from delivery", () => {
  it("captures instead of sending", async () => {
    const capture = new CaptureTransport();
    await capture.send(MESSAGE);
    expect(capture.last()?.to).toBe("trader@example.test");
    expect(sendMail).not.toHaveBeenCalled();
  });

  it("exercises the failure path without a server", async () => {
    expect(await new FailingTransport().send(MESSAGE)).toEqual({
      status: "failed",
    });
  });
});

// ---------------------------------------------------------------------------
// Message content
// ---------------------------------------------------------------------------

const VERIFY_URL = "https://www.tradelensai.io/verify-email?token=abc123";
const RESET_URL = "https://www.tradelensai.io/reset-password?token=def456";

describe("transactional messages", () => {
  const cases = [
    { name: "verification", message: verificationMessage("t@e.test", VERIFY_URL), url: VERIFY_URL },
    { name: "reset", message: passwordResetMessage("t@e.test", RESET_URL), url: RESET_URL },
  ];

  for (const { name, message, url } of cases) {
    describe(name, () => {
      it("identifies TradeLens AI", () => {
        expect(message.subject).toContain("TradeLens AI");
        expect(message.html).toContain("TradeLens AI");
      });

      it("carries the credential once in the text part", () => {
        const occurrences = message.text.split(url).length - 1;
        expect(occurrences).toBe(1);
      });

      it("offers the action in the HTML part too", () => {
        expect(message.html).toContain(url);
      });

      it("carries no other credential and no account internals", () => {
        const body = `${message.subject}\n${message.text}\n${message.html ?? ""}`;
        for (const forbidden of [
          "password_hash",
          "passwordHash",
          "user_id",
          "username",
          "session",
          "handoff",
        ]) {
          expect(body.toLowerCase()).not.toContain(forbidden.toLowerCase());
        }
      });

      it("never points at the Streamlit origin", () => {
        const body = `${message.text}\n${message.html ?? ""}`;
        expect(body).not.toContain("streamlit");
      });

      it("embeds no remote content", () => {
        // A blocked-by-default image is a tracking pixel on a security email.
        expect(message.html).not.toMatch(/<img\b/i);
        expect(message.html).not.toMatch(/<link\b/i);
        expect(message.html).not.toMatch(/<script\b/i);
      });

      it("states the expiry and what to do if it was not you", () => {
        expect(message.text).toMatch(/expires in \d+ (?:minutes|hours)/);
        expect(message.text.toLowerCase()).toContain("ignore this message");
      });
    });
  }

  it("uses the two different TTLs the tables actually enforce", () => {
    expect(verificationMessage("t@e.test", VERIFY_URL).text).toContain("24 hours");
    expect(passwordResetMessage("t@e.test", RESET_URL).text).toContain("30 minutes");
  });

  it("escapes a URL that carries HTML-significant characters", () => {
    const nasty = 'https://site.test/verify-email?token=a"><script>alert(1)</script>';
    const html = verificationMessage("t@e.test", nasty).html ?? "";
    expect(html).not.toContain("<script>alert(1)</script>");
    expect(html).toContain("&lt;script&gt;");
  });
});
