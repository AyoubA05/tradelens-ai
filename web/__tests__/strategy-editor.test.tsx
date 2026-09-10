import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PlaybookEditor } from "@/components/app/strategy/playbook-editor";
import { FirstRunBanner } from "@/components/app/strategy/first-run-banner";
import { InsightSuggestions } from "@/components/app/strategy/insight-suggestions";
import { REVISION, STARTER, emptyStrategyFixture, strategyFixture } from "./fixtures/strategy";

const refresh = vi.fn();
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, push, replace: vi.fn() }),
}));

const FIELD_KEYS = [
  "name",
  "trading_style",
  "markets",
  "timeframes",
  "entry_rules",
  "stop_rules",
  "take_profit_rules",
  "risk_rules",
  "setups_traded",
  "setups_avoided",
  "news_session_rules",
  "common_mistakes",
];

function respond(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
}

function sentBody(fetchMock: ReturnType<typeof vi.fn>) {
  return JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string);
}

beforeEach(() => {
  refresh.mockReset();
  push.mockReset();
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Saving", () => {
  it("sends exactly the twelve fields plus the version it was loaded from", async () => {
    const fetchMock = respond(200, strategyFixture({ revision: "next" }));
    vi.stubGlobal("fetch", fetchMock);
    render(<PlaybookEditor data={strategyFixture()} />);
    fireEvent.click(screen.getByRole("button", { name: "Save playbook" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/strategy");
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("PUT");
    const body = sentBody(fetchMock);
    expect(Object.keys(body).sort()).toEqual([...FIELD_KEYS, "expected_revision"].sort());
    expect(body.expected_revision).toBe(REVISION);
    expect(body.name).toBe("London Killzone Playbook");
    // Blank fields go as null, not as "".
    expect(body.entry_rules).toBeNull();
  });

  it("confirms the save and refreshes the server-rendered summary", async () => {
    vi.stubGlobal("fetch", respond(200, strategyFixture({ revision: "next" })));
    render(<PlaybookEditor data={strategyFixture()} />);
    fireEvent.click(screen.getByRole("button", { name: "Save playbook" }));
    await waitFor(() =>
      expect(screen.getByTestId("playbook-status")).toHaveTextContent(
        "Playbook saved. AI reviews will now use your rules.",
      ),
    );
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("refuses a blank name before sending anything", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<PlaybookEditor data={emptyStrategyFixture()} />);
    fireEvent.click(screen.getByRole("button", { name: "Save playbook" }));
    expect(
      await screen.findByText("Strategy name is required — it is how reviews refer to this playbook."),
    ).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("A stale tab", () => {
  it("keeps every typed character and says why the save was refused", async () => {
    vi.stubGlobal("fetch", respond(409, { ok: false, detail: "stale_profile" }));
    render(<PlaybookEditor data={strategyFixture()} />);
    const entry = screen.getByLabelText("What has to be true before you enter");
    fireEvent.change(entry, { target: { value: "My careful new rule" } });
    fireEvent.click(screen.getByRole("button", { name: "Save playbook" }));

    expect(await screen.findByTestId("playbook-conflict")).toHaveTextContent(
      "This playbook changed in another tab or device. Your edits are still here.",
    );
    expect(screen.getByLabelText("What has to be true before you enter")).toHaveValue(
      "My careful new rule",
    );
    expect(refresh).not.toHaveBeenCalled();
  });

  it("loads the saved version only after the trader confirms", async () => {
    vi.stubGlobal("fetch", respond(409, { ok: false, detail: "stale_profile" }));
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<PlaybookEditor data={strategyFixture()} />);
    fireEvent.click(screen.getByRole("button", { name: "Save playbook" }));
    fireEvent.click(await screen.findByRole("button", { name: "Load the saved version" }));
    expect(confirm).toHaveBeenCalledOnce();
    expect(refresh).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "Load the saved version" }));
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("does not let a newer server version overwrite unsaved typing", () => {
    const { rerender } = render(<PlaybookEditor data={strategyFixture()} />);
    fireEvent.change(screen.getByLabelText("Strategy Name"), { target: { value: "Typing…" } });
    rerender(
      <PlaybookEditor
        data={strategyFixture({
          revision: "someone-else",
          profile: { ...strategyFixture().profile!, name: "Other tab" },
        })}
      />,
    );
    expect(screen.getByLabelText("Strategy Name")).toHaveValue("Typing…");
  });

  it("adopts a newer server version when there is nothing unsaved", () => {
    const { rerender } = render(<PlaybookEditor data={strategyFixture()} />);
    rerender(
      <PlaybookEditor
        data={strategyFixture({
          revision: "after-insight",
          profile: { ...strategyFixture().profile!, risk_rules: "• added rule" },
        })}
      />,
    );
    expect(screen.getByLabelText("How much you risk, and how often")).toHaveValue("• added rule");
  });
});

describe("The starter playbook", () => {
  it("fills the editor and sends nothing", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const confirm = vi.spyOn(window, "confirm");
    render(<PlaybookEditor data={emptyStrategyFixture()} />);
    fireEvent.click(screen.getByRole("button", { name: "Start from the ICT/SMC starter playbook" }));
    expect(screen.getByLabelText("Strategy Name")).toHaveValue(STARTER.name);
    expect(screen.getByLabelText("How much you risk, and how often")).toHaveValue(
      STARTER.risk_rules,
    );
    expect(fetchMock).not.toHaveBeenCalled();
    expect(confirm).not.toHaveBeenCalled(); // nothing to overwrite
  });

  it("asks before replacing text, and keeps it when the trader declines", () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<PlaybookEditor data={strategyFixture()} />);
    fireEvent.click(screen.getByRole("button", { name: "Start from the ICT/SMC starter playbook" }));
    expect(screen.getByLabelText("Strategy Name")).toHaveValue("London Killzone Playbook");
  });

  it("says it is a template, not a recommendation", () => {
    render(<PlaybookEditor data={emptyStrategyFixture()} />);
    expect(screen.getByTestId("playbook-editor")).toHaveTextContent(
      "A starting template to edit into your own rules. It is not a recommendation",
    );
  });
});

describe("Limits are shown, never enforced by cutting", () => {
  it("marks a field over its limit and sends nothing", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<PlaybookEditor data={strategyFixture()} />);
    const entry = screen.getByLabelText("What has to be true before you enter");
    fireEvent.change(entry, { target: { value: "x".repeat(501) } });
    expect(entry).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("501 / 500")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save playbook" }));
    expect(fetchMock).not.toHaveBeenCalled();
    // The text itself is untouched.
    expect(entry).toHaveValue("x".repeat(501));
  });

  it("shows a legacy over-limit rule in full and asks the trader to shorten it", () => {
    const long = "legacy rule ".repeat(60);
    render(
      <PlaybookEditor
        data={strategyFixture({
          profile: { ...strategyFixture().profile!, risk_rules: long },
          over_limit: ["risk_rules"],
        })}
      />,
    );
    expect(screen.getByLabelText("How much you risk, and how often")).toHaveValue(long);
    expect(
      screen.getByText("This rule is longer than the 500-character limit. Shorten it to save."),
    ).toBeInTheDocument();
  });

  it("marks the field a 422 names, by code, without guessing", async () => {
    vi.stubGlobal(
      "fetch",
      respond(422, { ok: false, detail: [{ field: "entry_rules", problem: "invalid_characters" }] }),
    );
    render(<PlaybookEditor data={strategyFixture()} />);
    fireEvent.click(screen.getByRole("button", { name: "Save playbook" }));
    expect(await screen.findByText("Contains characters that cannot be saved.")).toBeInTheDocument();
    expect(screen.getByLabelText("What has to be true before you enter")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });
});

describe("Leaving with unsaved changes", () => {
  it("guards unload only while there is something unsaved", async () => {
    const add = vi.spyOn(window, "addEventListener");
    const remove = vi.spyOn(window, "removeEventListener");
    vi.stubGlobal("fetch", respond(200, strategyFixture({ revision: "next" })));
    render(<PlaybookEditor data={strategyFixture()} />);
    expect(add.mock.calls.some(([type]) => type === "beforeunload")).toBe(false);

    fireEvent.change(screen.getByLabelText("Strategy Name"), { target: { value: "Edited" } });
    expect(add.mock.calls.some(([type]) => type === "beforeunload")).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Save playbook" }));
    await waitFor(() =>
      expect(remove.mock.calls.some(([type]) => type === "beforeunload")).toBe(true),
    );
  });
});

describe("First run and suggestions", () => {
  it("skips first run with no body and returns to the Overview", async () => {
    const fetchMock = respond(200, emptyStrategyFixture());
    vi.stubGlobal("fetch", fetchMock);
    render(<FirstRunBanner />);
    fireEvent.click(screen.getByRole("button", { name: "I don't have a defined strategy yet" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/app"));
    expect(fetchMock).toHaveBeenCalledWith("/api/strategy/skip", { method: "POST" });
  });

  it("sends only the group key and the version, never rule text or a column", async () => {
    const fetchMock = respond(200, strategyFixture());
    vi.stubGlobal("fetch", fetchMock);
    render(
      <InsightSuggestions
        data={strategyFixture({
          suggestions: [
            { field: "bias", user_value: "bearish", count: 5, rule: "• bias: prefer bearish (x)" },
          ],
        })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Add to Risk Rules" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    expect(sentBody(fetchMock)).toEqual({
      field: "bias",
      user_value: "bearish",
      expected_revision: REVISION,
    });
    expect(await screen.findByText("Added to your Risk Rules.")).toBeInTheDocument();
  });

  it.each([
    ["no_profile", "Save a playbook first — this adds to one you have written."],
    ["rules_full", "Risk Rules are at the 500-character limit. Make room there, then add this."],
  ])("explains the %s refusal", async (code, text) => {
    vi.stubGlobal("fetch", respond(409, { ok: false, detail: code }));
    render(
      <InsightSuggestions
        data={strategyFixture({
          suggestions: [{ field: "bias", user_value: "bearish", count: 5, rule: "r" }],
        })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Add to Risk Rules" }));
    expect(await screen.findByText(text)).toBeInTheDocument();
  });
});

describe("Copy", () => {
  it("never tells a trader what to trade", () => {
    const { container } = render(
      <>
        <FirstRunBanner />
        <InsightSuggestions
          data={strategyFixture({
            suggestions: [{ field: "bias", user_value: "bearish", count: 5, rule: "r" }],
          })}
        />
        <PlaybookEditor data={strategyFixture()} />
      </>,
    );
    const text = (container.textContent ?? "").replace("It is not a recommendation", "");
    expect(text).not.toMatch(/\b(you should|buy|sell|signal|guaranteed|recommend)/i);
  });
});
