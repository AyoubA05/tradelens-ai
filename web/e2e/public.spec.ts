import { expect, test } from "@playwright/test";

import { expectNoHorizontalScroll } from "./helpers";

for (const path of ["/login", "/signup", "/forgot-password"]) {
  test(`${path} renders without horizontal scroll`, async ({ page }) => {
    const response = await page.goto(path);
    expect(response?.status()).toBeLessThan(400);
    await expect(page.locator("h1")).toBeVisible();
    await expectNoHorizontalScroll(page);
  });
}

test("an anonymous /app request is sent to sign in", async ({ page }) => {
  await page.goto("/app");
  await expect(page).toHaveURL(/\/login/);
});
