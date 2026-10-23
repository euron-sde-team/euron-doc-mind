import { expect, test } from "@playwright/test";

import { WORKSPACE, signIn } from "../helpers";

test("an editor uploads, opens, renames and deletes a document", async ({ page }) => {
  const stamp = Date.now();
  const filename = `e2e-field-notes-${stamp}.md`;
  const renamed = `Field notes ${stamp}`;
  await signIn(page, "editor");
  await page.goto(`/w/${WORKSPACE}/documents`);

  await page.locator('input[type="file"]').setInputFiles({
    name: filename,
    mimeType: "text/markdown",
    buffer: Buffer.from(
      `# Field notes ${stamp}\n\n## Calibration\n\nThe Rotterdam fleet recalibrates its depth cameras every 14 days.\n`,
    ),
  });

  const row = page.getByRole("row", {
    name: new RegExp(`Field notes ${stamp}|e2e-field-notes-${stamp}`),
  });
  await expect(row.getByText("Ready")).toBeVisible({ timeout: 60_000 });

  await row.getByRole("link").first().click();
  await expect(page.getByText("recalibrates its depth cameras every 14 days")).toBeVisible();

  await page.goto(`/w/${WORKSPACE}/documents`);
  await page.getByRole("button", { name: new RegExp(`Actions for .*${stamp}`) }).click();
  await page.getByRole("menuitem", { name: "Rename" }).click();
  await page.getByRole("dialog").getByRole("textbox").fill(renamed);
  await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("link", { name: renamed })).toBeVisible();

  await page.getByRole("button", { name: `Actions for ${renamed}` }).click();
  await page.getByRole("menuitem", { name: "Delete" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();
  await expect(page.getByRole("link", { name: renamed })).toHaveCount(0);
});

test("the library filters by text and file type", async ({ page }) => {
  await signIn(page, "viewer");
  await page.goto(`/w/${WORKSPACE}/documents`);

  await page.getByLabel("Filter documents").fill("globex");
  await expect(page.getByRole("link", { name: "Globex Master Services Agreement" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Q3 2026 Board Update" })).toHaveCount(0);
});

test("viewers can read the library but not change it", async ({ page }) => {
  await signIn(page, "viewer");
  await page.goto(`/w/${WORKSPACE}/documents`);

  await expect(page.getByRole("link", { name: "Northwind Employee Handbook 2026" })).toBeVisible();
  await expect(page.getByText("Drop files here")).toHaveCount(0);
  await page.getByRole("button", { name: "Actions for Northwind Employee Handbook 2026" }).click();
  await expect(page.getByRole("menuitem", { name: "Download original" })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: "Delete" })).toHaveCount(0);
});
