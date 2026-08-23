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

import { Pagination } from "@/components/app/trades/pagination";

beforeEach(() => {
  replace.mockReset();
  currentParams = "";
});

describe("Pagination", () => {
  it("renders nothing when everything fits on one page", () => {
    const { container } = render(<Pagination total={10} limit={25} offset={0} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("disables Previous on the first page", () => {
    render(<Pagination total={60} limit={25} offset={0} />);
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
  });

  it("disables Next on the last page", () => {
    render(<Pagination total={60} limit={25} offset={50} />);
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Previous" })).toBeEnabled();
  });

  it("shows the current page and total", () => {
    render(<Pagination total={60} limit={25} offset={25} />);
    expect(screen.getByText(/page 2 of 3/i)).toBeInTheDocument();
    expect(screen.getByText(/60 trades/i)).toBeInTheDocument();
  });

  it("advances offset by limit on Next, preserving other params", () => {
    currentParams = "from=2026-08-01&to=2026-08-31&asset=NQ";
    render(<Pagination total={60} limit={25} offset={0} />);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    const url = replace.mock.calls[0][0] as string;
    const params = new URLSearchParams(url.split("?")[1]);
    expect(params.get("offset")).toBe("25");
    expect(params.get("asset")).toBe("NQ");
  });

  it("offers a route back when the offset is past the end of the result set", () => {
    // Narrowing a filter while on ?offset=100 can leave the offset beyond the
    // new, smaller total. Hiding the pager there strands the trader: the empty
    // table's only action is "Log completed trade".
    currentParams = "offset=100&asset=NQ";
    render(<Pagination total={12} limit={25} offset={100} />);
    fireEvent.click(screen.getByRole("button", { name: /back to first page/i }));
    const url = replace.mock.calls[0][0] as string;
    const params = new URLSearchParams(url.split("?")[1]);
    expect(params.has("offset")).toBe(false);
    expect(params.get("asset")).toBe("NQ");
  });

  it("still offers the way back when the filtered result set is empty", () => {
    currentParams = "offset=100";
    render(<Pagination total={0} limit={25} offset={100} />);
    expect(screen.getByRole("button", { name: /back to first page/i })).toBeInTheDocument();
  });

  it("keeps the way back on a multi-page list whose offset overshot the end", () => {
    currentParams = "offset=200";
    render(<Pagination total={60} limit={25} offset={200} />);
    // Previous alone would need four clicks to get back into range.
    expect(screen.getByRole("button", { name: /back to first page/i })).toBeInTheDocument();
  });

  it("still renders nothing on a single page the trader is actually on", () => {
    const { container } = render(<Pagination total={10} limit={25} offset={0} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("drops the offset param entirely when going back to page 1", () => {
    currentParams = "offset=25";
    render(<Pagination total={60} limit={25} offset={25} />);
    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    const url = replace.mock.calls[0][0] as string;
    expect(new URLSearchParams(url.split("?")[1]).has("offset")).toBe(false);
  });
});
