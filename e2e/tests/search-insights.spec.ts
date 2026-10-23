import { expect, test } from "@playwright/test";

import { WORKSPACE, signIn } from "../helpers";

test("hybrid search highlights matches and opens the document", async ({ page }) => {
  await signIn(page, "viewer");
  await page.goto(`/w/${WORKSPACE}/search`);

  await page.getByLabel("Search query").fill("warranty batteries");
  await page.getByRole("button", { name: "Search" }).click();

  await expect(page.locator("mark").first()).toBeVisible();
  await page
    .getByRole("link", { name: /Atlas Customer Support FAQ/ })
    .first()
    .click();
  await expect(page).toHaveURL(new RegExp(`/w/${WORKSPACE}/documents/[0-9a-f-]+`));
});

test("insights show questions, tokens saved and the cache hit rate", async ({ page }) => {
  await signIn(page, "owner");
  await page.goto(`/w/${WORKSPACE}/insights`);

  for (const label of ["Questions answered", "Tokens saved", "Cache hit rate"]) {
    await expect(page.getByText(label)).toBeVisible();
  }
  await expect(page.getByText("Questions per day")).toBeVisible();
  await expect(page.locator(".recharts-surface").first()).toBeVisible();
});
