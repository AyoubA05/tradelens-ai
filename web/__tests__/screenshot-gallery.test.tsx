import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ScreenshotGallery } from "@/components/app/trade-detail/screenshot-gallery";

describe("ScreenshotGallery", () => {
  it("renders nothing for a trade with no screenshots", () => {
    const { container } = render(<ScreenshotGallery screenshots={[]} asset="NQ" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders a lazy-loaded image with a meaningful alt for a resolved URL", () => {
    render(
      <ScreenshotGallery
        screenshots={[{ id: 1, url: "https://r2.example/a.png", width: 800, height: 450, uploaded_at: null }]}
        asset="NQ"
      />,
    );
    const img = screen.getByRole("img", { name: /NQ/i });
    expect(img).toHaveAttribute("loading", "lazy");
    expect(img).toHaveAttribute("src", "https://r2.example/a.png");
    expect(img.tagName).toBe("IMG");
  });

  it("shows a graceful placeholder, not a broken-image icon, when the URL is null", () => {
    render(
      <ScreenshotGallery
        screenshots={[{ id: 1, url: null, width: null, height: null, uploaded_at: null }]}
        asset="NQ"
      />,
    );
    // The placeholder is itself `role="img"` (an accessible description of an
    // absence, not a photo), so the real assertion is that no <img> element —
    // nothing that could 404 in a browser — is in the tree.
    expect(document.querySelector("img")).not.toBeInTheDocument();
    expect(screen.getByText(/not available right now/i)).toBeInTheDocument();
  });

  it("falls back to the placeholder when a resolved URL fails to load (expired presign)", () => {
    render(
      <ScreenshotGallery
        screenshots={[{ id: 1, url: "https://r2.example/a.png", width: 800, height: 450, uploaded_at: null }]}
        asset="NQ"
      />,
    );
    const img = screen.getByRole("img", { name: /NQ/i });
    fireEvent.error(img);
    expect(screen.getByText(/not available right now/i)).toBeInTheDocument();
  });

  it("renders one frame per screenshot", () => {
    render(
      <ScreenshotGallery
        screenshots={[
          { id: 1, url: "https://r2.example/a.png", width: null, height: null, uploaded_at: null },
          { id: 2, url: null, width: null, height: null, uploaded_at: null },
        ]}
        asset="NQ"
      />,
    );
    expect(screen.getAllByRole("img")).toHaveLength(2);
  });
});
