import { expect, test } from "@playwright/test";

import { WORKSPACE, signIn } from "../helpers";

test("the owner adds a member and sees their temporary password once", async ({ page }) => {
  const email = `e2e-${Date.now()}@northwind.example`;
  await signIn(page, "owner");
  await page.goto(`/w/${WORKSPACE}/settings`);
  await page.getByRole("tab", { name: "Members" }).click();

  await page.getByRole("button", { name: "Add member" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Email").fill(email);
  await dialog.getByLabel("Name").fill("Sam Rivera");
  await dialog.getByLabel("Role").selectOption("viewer");
  await dialog.getByRole("button", { name: "Add member" }).click();

  await expect(dialog.getByText("Temporary password")).toBeVisible();
  await dialog.getByRole("button", { name: "Done" }).click();
  await expect(page.getByText(email)).toBeVisible();
});

test("the owner creates an API key that is shown only once", async ({ page }) => {
  const name = `E2E key ${Date.now()}`;
  await signIn(page, "owner");
  await page.goto(`/w/${WORKSPACE}/settings`);
  await page.getByRole("tab", { name: "API keys" }).click();

  await page.getByRole("button", { name: "Create key" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Name").fill(name);
  await dialog.getByRole("button", { name: "Create key" }).click();

  await expect(dialog.getByText(/dmk_/)).toBeVisible();
  await dialog.getByRole("button", { name: "Done" }).click();
  await expect(page.getByText(name)).toBeVisible();
});

test("only owners see keys and activity", async ({ page }) => {
  await signIn(page, "viewer");
  await page.goto(`/w/${WORKSPACE}/settings`);

  await expect(page.getByRole("tab", { name: "Members" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "API keys" })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Activity" })).toHaveCount(0);
});
