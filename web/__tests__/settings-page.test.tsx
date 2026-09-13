import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PreferencesSection } from "@/components/app/settings/preferences-section";
import { ProfileSection } from "@/components/app/settings/profile-section";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => vi.unstubAllGlobals());

describe("profile (S1: display-only)", () => {
  it("shows the email and its verification but offers no way to change it", () => {
    render(
      <ProfileSection
        account={{ username: "trader", email: "t@example.com", email_verified: true }}
        resetEmailConfigured
      />,
    );
    expect(screen.getByText("t@example.com")).toBeInTheDocument();
    expect(screen.getByText("Verified")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("says when the email is not verified and when there is none", () => {
    const { rerender } = render(
      <ProfileSection
        account={{ username: "trader", email: "t@example.com", email_verified: false }}
        resetEmailConfigured
      />,
    );
    expect(screen.getByText("Not verified yet")).toBeInTheDocument();
    rerender(
      <ProfileSection account={{ username: "trader", email: null, email_verified: false }} resetEmailConfigured />,
    );
    expect(screen.getByText("No email on this account")).toBeInTheDocument();
  });

  it("warns when outgoing email is not configured", () => {
    render(
      <ProfileSection
        account={{ username: "trader", email: "t@example.com", email_verified: true }}
        resetEmailConfigured={false}
      />,
    );
    expect(screen.getByText(/outgoing email is not configured/i)).toBeInTheDocument();
  });
});

describe("preferences", () => {
  const timezone = { current: "UTC", options: ["America/New_York", "UTC"] };

  it("saves a timezone change through the relay and confirms beside the control", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
    render(<PreferencesSection timezone={timezone} ai={{ state: "enabled" }} demoMode={false} />);
    await act(async () => {
      fireEvent.change(screen.getByLabelText(/trading timezone/i), {
        target: { value: "America/New_York" },
      });
    });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/settings/timezone");
    expect(fetchMock.mock.calls[0][1].method).toBe("PUT");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ timezone: "America/New_York" });
    expect(screen.getByRole("status")).toHaveTextContent("Trading timezone saved — America/New_York.");
    expect(screen.getByLabelText(/trading timezone/i)).toHaveValue("America/New_York");
  });

  it("restores the previous zone and names the rule when the server refuses", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ ok: false, detail: [{ field: "timezone", problem: "unsupported" }] }),
    });
    render(<PreferencesSection timezone={timezone} ai={{ state: "enabled" }} demoMode={false} />);
    await act(async () => {
      fireEvent.change(screen.getByLabelText(/trading timezone/i), {
        target: { value: "America/New_York" },
      });
    });
    expect(screen.getByRole("status")).toHaveTextContent("Choose one of the listed timezones.");
    expect(screen.getByLabelText(/trading timezone/i)).toHaveValue("UTC");
  });

  it("keeps showing a legacy stored zone that is not one of the options", () => {
    render(
      <PreferencesSection
        timezone={{ current: "Pacific/Kiritimati", options: ["UTC"] }}
        ai={{ state: "enabled" }}
        demoMode={false}
      />,
    );
    expect(screen.getByLabelText(/trading timezone/i)).toHaveValue("Pacific/Kiritimati");
  });

  it.each([
    ["enabled", /AI features are enabled/],
    ["demo", /Demo mode/],
    ["unavailable", /AI features are unavailable/],
  ] as const)("describes the %s AI state without secret instructions (S2)", (state, copy) => {
    render(<PreferencesSection timezone={timezone} ai={{ state }} demoMode={state === "demo"} />);
    expect(screen.getByText(copy)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/ANTHROPIC_API_KEY|secrets\.toml|\.env|console\.anthropic/i);
  });

  it("shows demo status only as a line (S3)", () => {
    render(<PreferencesSection timezone={timezone} ai={{ state: "demo" }} demoMode />);
    expect(screen.getByText("This deployment is running in demo mode.")).toBeInTheDocument();
  });
});
