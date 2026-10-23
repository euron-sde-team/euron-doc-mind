import { expect, test } from "@playwright/test";

import { PEOPLE, WORKSPACE, requirePassword, signInWithForm } from "../helpers";

test("a wrong password is refused with a clear message", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(PEOPLE.owner.email);
  await page.getByLabel("Password").fill("definitely-not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});

test("signing in opens the workspace and signing out ends the session", async ({ page }) => {
  // Its own session: signing out revokes it, so it must not be one the other tests reuse.
  await signInWithForm(page, "owner");
  await expect(page.getByRole("button", { name: "Account menu" })).toBeVisible();

  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);

  // The old session no longer opens workspace pages.
  await page.goto(`/w/${WORKSPACE}/documents`);
  await expect(page).toHaveURL(/\/login\?next=/);
});

test("a signed-out visit returns to the page after signing in", async ({ page }) => {
  await page.goto(`/w/${WORKSPACE}/insights`);
  await expect(page).toHaveURL(/\/login\?next=/);

  await page.getByLabel("Email").fill(PEOPLE.owner.email);
  await page.getByLabel("Password").fill(requirePassword());
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(new RegExp(`/w/${WORKSPACE}/insights`));
});
