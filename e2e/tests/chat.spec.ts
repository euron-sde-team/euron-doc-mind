import { expect, test } from "@playwright/test";

import { WORKSPACE, signIn } from "../helpers";

test.describe.configure({ mode: "serial" });

test("an answer streams in with citations that open the cited passage", async ({ page }) => {
  await signIn(page, "editor");
  await page.goto(`/w/${WORKSPACE}/chat`);

  await page
    .getByRole("textbox", { name: "Question" })
    .fill("How much notice is needed to terminate the Globex agreement?");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByText("90 days").first()).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`/w/${WORKSPACE}/chat/[0-9a-f-]+`));
  const citation = page.getByRole("button", { name: /^Source 1:.*Globex/ }).first();
  await expect(citation).toBeVisible();

  await citation.click();
  await expect(page.getByText("Open in document")).toBeVisible();
  await page.getByText("Open in document").click();

  await expect(page).toHaveURL(new RegExp(`/w/${WORKSPACE}/documents/[0-9a-f-]+`));
  await expect(
    page.getByRole("heading", { name: "Globex Master Services Agreement" }),
  ).toBeVisible();
  await expect(page.locator("mark").first()).toBeVisible();
});

test("a follow-up question uses the conversation so far", async ({ page }) => {
  await signIn(page, "editor");
  await page.goto(`/w/${WORKSPACE}/chat`);

  await page.getByRole("textbox", { name: "Question" }).fill("What is the parental leave policy?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("26 weeks").first()).toBeVisible();

  await page.getByRole("textbox", { name: "Question" }).fill("How long does it last?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("26 weeks")).toHaveCount(2);

  // The conversation is listed under its first question.
  await expect(
    page.getByRole("link", { name: /What is the parental leave policy/ }).first(),
  ).toBeVisible();
});

test("questions the documents cannot answer say so instead of guessing", async ({ page }) => {
  await signIn(page, "viewer");
  await page.goto(`/w/${WORKSPACE}/chat`);

  await page
    .getByRole("textbox", { name: "Question" })
    .fill("What is the airspeed velocity of an unladen swallow?");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByText("I could not find a clear answer").first()).toBeVisible();
});
