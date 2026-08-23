import "@testing-library/jest-dom/vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

const replace = vi.fn();
let currentParams = "";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/app/journal",
  useSearchParams: () => new URLSearchParams(currentParams),
}));

import { FilterBar } from "@/components/app/trades/filter-bar";

beforeEach(() => {
  replace.mockReset();
  currentParams = "";
});

describe("FilterBar", () => {
  it("writes the asset filter to the URL on blur, resetting offset", () => {
    currentParams = "from=2026-08-01&to=2026-08-31&offset=50";
    render(<FilterBar />);
    const input = screen.getByLabelText("Asset");
    fireEvent.change(input, { target: { value: "NQ" } });
    fireEvent.blur(input);

    expect(replace).toHaveBeenCalledTimes(1);
    const url = replace.mock.calls[0][0] as string;
    const params = new URLSearchParams(url.split("?")[1]);
    expect(params.get("asset")).toBe("NQ");
    expect(params.has("offset")).toBe(false);
    expect(params.get("from")).toBe("2026-08-01");
  });

  it("writes the result filter through the select", () => {
    render(<FilterBar />);
    fireEvent.change(screen.getByLabelText("Result"), { target: { value: "Win" } });
    const url = replace.mock.calls[0][0] as string;
    expect(new URLSearchParams(url.split("?")[1]).get("result")).toBe("Win");
  });

  it("removes a filter when cleared", () => {
    currentParams = "asset=NQ";
    render(<FilterBar />);
    const input = screen.getByLabelText("Asset");
    fireEvent.change(input, { target: { value: "" } });
    fireEvent.blur(input);
    const url = replace.mock.calls[0][0] as string;
    expect(new URLSearchParams(url.split("?")[1]).has("asset")).toBe(false);
  });

  it("shows a clear-filters control only once a filter is active", () => {
    const { rerender } = render(<FilterBar />);
    expect(screen.queryByRole("button", { name: /clear filters/i })).not.toBeInTheDocument();

    currentParams = "asset=NQ";
    rerender(<FilterBar />);
    expect(screen.getByRole("button", { name: /clear filters/i })).toBeInTheDocument();
  });

  it("clearing all filters drops every known filter key from the URL", () => {
    currentParams = "asset=NQ&session=London&setup=FVG&result=Win&from=2026-08-01";
    render(<FilterBar />);
    fireEvent.click(screen.getByRole("button", { name: /clear filters/i }));
    const url = replace.mock.calls[0][0] as string;
    const params = new URLSearchParams(url.split("?")[1]);
    expect(params.has("asset")).toBe(false);
    expect(params.has("session")).toBe(false);
    expect(params.has("setup")).toBe(false);
    expect(params.has("result")).toBe(false);
    expect(params.get("from")).toBe("2026-08-01");
  });
});
