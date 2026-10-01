// @vitest-environment node
import net from "node:net";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { passwordResetMessage, verificationMessage } from "@/lib/mail/messages";
import { SmtpTransport } from "@/lib/mail/transport";

/**
 * The real SMTP wire. mail.test.ts mocks nodemailer, so it proves our options
 * but not what the library does with them; this file runs the actual
 * nodemailer against an in-process fake SMTP server. It exists because a
 * nodemailer major upgrade (9 -> 10) changed the package's build, entry
 * points and, per its changelog, when requireTLS is honoured.
 *
 * Every test also asserts that no recipient, subject, body, link or
 * credential reaches any console channel: the transport promises to keep
 * only the error class name.
 */

type Mode = "ok" | "reject-rcpt" | "auth-fail";

type FakeServer = {
  port: number;
  received: string[];
  commands: string[];
  close: () => Promise<void>;
};

async function fakeSmtp(mode: Mode): Promise<FakeServer> {
  const received: string[] = [];
  const commands: string[] = [];
  const sockets = new Set<net.Socket>();
  const server = net.createServer((socket) => {
    sockets.add(socket);
    socket.on("close", () => sockets.delete(socket));
    let inData = false;
    let data = "";
    let buffer = "";
    socket.write("220 fake.smtp.test ESMTP\r\n");
    socket.on("data", (chunk) => {
      buffer += chunk.toString("utf8");
      let index: number;
      while ((index = buffer.indexOf("\r\n")) >= 0) {
        const line = buffer.slice(0, index);
        buffer = buffer.slice(index + 2);
        if (inData) {
          if (line === ".") {
            inData = false;
            received.push(data);
            data = "";
            socket.write("250 2.0.0 queued\r\n");
          } else {
            data += line + "\n";
          }
          continue;
        }
        const verb = line.split(" ")[0].toUpperCase();
        commands.push(verb);
        if (verb === "EHLO") {
          // Deliberately no STARTTLS: a send that requires TLS must refuse.
          socket.write("250-fake.smtp.test\r\n250-AUTH PLAIN LOGIN\r\n250 8BITMIME\r\n");
        } else if (verb === "HELO") {
          socket.write("250 fake.smtp.test\r\n");
        } else if (verb === "AUTH") {
          // A real server's refusal often echoes what was refused.
          socket.write(
            mode === "auth-fail"
              ? `535 5.7.8 credentials invalid: ${line.slice(5)}\r\n`
              : "235 2.7.0 accepted\r\n",
          );
        } else if (verb === "MAIL") {
          socket.write("250 2.1.0 ok\r\n");
        } else if (verb === "RCPT") {
          socket.write(
            mode === "reject-rcpt"
              ? `550 5.1.1 ${line.slice(8)} unknown recipient\r\n`
              : "250 2.1.5 ok\r\n",
          );
        } else if (verb === "DATA") {
          inData = true;
          socket.write("354 go ahead\r\n");
        } else if (verb === "QUIT") {
          socket.end("221 bye\r\n");
        } else if (verb === "RSET" || verb === "NOOP") {
          socket.write("250 ok\r\n");
        } else {
          socket.write("502 not implemented\r\n");
        }
      }
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "::", resolve));
  const port = (server.address() as net.AddressInfo).port;
  return {
    port,
    received,
    commands,
    close: () =>
      new Promise<void>((resolve) => {
        for (const s of sockets) s.destroy();
        server.close(() => resolve());
      }),
  };
}

const SMTP_KEYS = [
  "TRADELENS_SMTP_HOST",
  "TRADELENS_SMTP_PORT",
  "TRADELENS_SMTP_USER",
  "TRADELENS_SMTP_PASSWORD",
  "TRADELENS_SMTP_FROM",
] as const;

const RECIPIENT = "recipient.canary@example.test";
const SMTP_USER = "smtp-user-canary";
const SMTP_PASSWORD = "Smtp-Pass-Canary-91x";
const VERIFY_URL = "https://www.tradelensai.io/verify-email?token=CANARYTOKENverify123";
const RESET_URL = "https://www.tradelensai.io/reset-password?token=CANARYTOKENreset456";

let saved: Record<string, string | undefined> = {};
let logged: string[] = [];
let server: FakeServer | null = null;

function configure(host: string, port: number, withAuth = false) {
  process.env.TRADELENS_SMTP_HOST = host;
  process.env.TRADELENS_SMTP_PORT = String(port);
  process.env.TRADELENS_SMTP_FROM = "TradeLens AI <no-reply@example.test>";
  if (withAuth) {
    process.env.TRADELENS_SMTP_USER = SMTP_USER;
    process.env.TRADELENS_SMTP_PASSWORD = SMTP_PASSWORD;
  }
}

function expectNothingSensitiveLogged(message: { subject: string; text: string }) {
  const all = logged.join("\n");
  const secrets = [
    RECIPIENT,
    message.subject,
    VERIFY_URL,
    RESET_URL,
    "CANARYTOKEN",
    SMTP_USER,
    SMTP_PASSWORD,
    Buffer.from(SMTP_PASSWORD).toString("base64"),
    Buffer.from(`\u0000${SMTP_USER}\u0000${SMTP_PASSWORD}`).toString("base64"),
  ];
  for (const secret of secrets) expect(all).not.toContain(secret);
  // Any body line long enough to be distinctive must not appear either.
  for (const line of message.text.split("\n").filter((l) => l.trim().length > 25)) {
    expect(all).not.toContain(line.trim());
  }
}

beforeEach(() => {
  saved = {};
  for (const key of SMTP_KEYS) {
    saved[key] = process.env[key];
    delete process.env[key];
  }
  logged = [];
  for (const channel of ["log", "info", "warn", "error", "debug"] as const) {
    vi.spyOn(console, channel).mockImplementation((...args: unknown[]) => {
      logged.push(args.map((a) => (a instanceof Error ? `${a.name}: ${a.message}` : String(a))).join(" "));
    });
  }
});

afterEach(async () => {
  vi.restoreAllMocks();
  for (const key of SMTP_KEYS) {
    if (saved[key] === undefined) delete process.env[key];
    else process.env[key] = saved[key];
  }
  if (server) await server.close();
  server = null;
});

describe("SmtpTransport over a real SMTP exchange", () => {
  it.each([
    ["verification", () => verificationMessage(RECIPIENT, VERIFY_URL), VERIFY_URL],
    ["password reset", () => passwordResetMessage(RECIPIENT, RESET_URL), RESET_URL],
  ])("delivers the %s message, link intact", async (_name, build, url) => {
    server = await fakeSmtp("ok");
    configure("127.0.0.1", server.port);
    const message = build();

    const outcome = await new SmtpTransport().send(message);

    expect(outcome).toEqual({ status: "sent" });
    expect(server.received).toHaveLength(1);
    // Quoted-printable may fold long lines; undo soft breaks before looking.
    const delivered = server.received[0].replace(/=\n/g, "").replace(/=3D/g, "=");
    expect(delivered).toContain(url);
    expect(delivered).toContain(`To: ${RECIPIENT}`);
    expectNothingSensitiveLogged(message);
  });

  it("reports a rejected recipient as failed and logs only the error class", async () => {
    server = await fakeSmtp("reject-rcpt");
    configure("127.0.0.1", server.port);
    const message = passwordResetMessage(RECIPIENT, RESET_URL);

    const outcome = await new SmtpTransport().send(message);

    expect(outcome).toEqual({ status: "failed" });
    expect(server.received).toHaveLength(0);
    expect(logged.join("\n")).toMatch(/^mail: delivery failed \(\w+\)$/m);
    expectNothingSensitiveLogged(message);
  });

  it("reports refused credentials as failed without logging them", async () => {
    server = await fakeSmtp("auth-fail");
    configure("127.0.0.1", server.port, true);
    const message = verificationMessage(RECIPIENT, VERIFY_URL);

    const outcome = await new SmtpTransport().send(message);

    expect(outcome).toEqual({ status: "failed" });
    expect(server.commands).toContain("AUTH");
    expect(server.received).toHaveLength(0);
    expectNothingSensitiveLogged(message);
  });

  it("reports a connection that cannot open as failed", async () => {
    const closed = await fakeSmtp("ok");
    const port = closed.port;
    await closed.close();
    configure("127.0.0.1", port);
    const message = verificationMessage(RECIPIENT, VERIFY_URL);

    const outcome = await new SmtpTransport().send(message);

    expect(outcome).toEqual({ status: "failed" });
    expectNothingSensitiveLogged(message);
  });

  it("refuses to send off loopback when the server offers no STARTTLS", async () => {
    // "::ffff:127.0.0.1" reaches this process's server but is not in the
    // loopback allow-list, so the transport requires TLS. The fake server
    // never offers STARTTLS: the message must not be sent in clear text.
    server = await fakeSmtp("ok");
    configure("::ffff:127.0.0.1", server.port, true);
    const message = passwordResetMessage(RECIPIENT, RESET_URL);

    const outcome = await new SmtpTransport().send(message);

    expect(outcome).toEqual({ status: "failed" });
    expect(server.commands).not.toContain("DATA");
    expect(server.commands).not.toContain("AUTH");
    expect(server.received).toHaveLength(0);
    expectNothingSensitiveLogged(message);
  });
});
