import { expect, test } from "@playwright/test";

import { expectNoHorizontalScroll, signIn } from "./helpers";

const email = process.env.E2E_EMAIL;
const password = process.env.E2E_PASSWORD;

test.skip(!email || !password, "E2E_EMAIL and E2E_PASSWORD are owner-supplied; never committed");

const SECTIONS: { path: string; heading: RegExp }[] = [
  { path: "/app", heading: /overview/i },
  { path: "/app/journal", heading: /journal/i },
  { path: "/app/trades/new", heading: /new trade/i },
  { path: "/app/analytics", heading: /analytics/i },
  { path: "/app/reviews", heading: /ai reviews/i },
  { path: "/app/strategy", heading: /strategy/i },
  { path: "/app/settings", heading: /settings/i },
];

test.beforeEach(async ({ page }) => {
  await signIn(page, email as string, password as string);
});

for (const section of SECTIONS) {
  test(`${section.path} renders its heading, no error state, no horizontal scroll`, async ({
    page,
  }) => {
    await page.goto(section.path);
    await expect(page.getByRole("heading", { level: 1, name: section.heading })).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
    await expectNoHorizontalScroll(page);
  });
}
