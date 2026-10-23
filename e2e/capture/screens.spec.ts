/**
 * README screenshots (1440x900 at 2x) and tour frames, from the seeded demo workspace.
 * Every image shows the real stack: nothing here is mocked.
 */
import { mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { WORKSPACE, settle, signIn } from "../helpers";

const SHOTS = path.resolve(__dirname, "../../docs/assets/screenshots");
const FRAMES = path.resolve(__dirname, "../.capture/frames");
mkdirSync(SHOTS, { recursive: true });
mkdirSync(FRAMES, { recursive: true });

let frame = 0;
async function shot(page: Page, name: string): Promise<void> {
  await settle(page);
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
}
async function tourFrame(page: Page, holdMs = 1600): Promise<void> {
  frame += 1;
  const file = path.join(FRAMES, `${String(frame).padStart(3, "0")}-${holdMs}.png`);
  await page.screenshot({ path: file, scale: "css" });
}

test.describe.configure({ mode: "serial" });
// Captures run on a busy laptop as often as on CI: allow slow answers rather than flake.
test.setTimeout(240_000);

test("sign-in page", async ({ page }) => {
  await page.goto("/login");
  await settle(page);
  await page.screenshot({ path: path.join(SHOTS, "01-sign-in.png") });
  await tourFrame(page, 1400);
});

test("chat, citations, viewer, library, search, insights and settings", async ({ page }) => {
  await signIn(page, "owner");
  await page.goto(`/w/${WORKSPACE}/chat`);
  await settle(page);
  await shot(page, "02-new-chat");
  await tourFrame(page, 1400);

  // A live question, captured while it streams and when it lands.
  await page
    .getByRole("textbox", { name: "Question" })
    .fill("What are the biggest risks the board should know about?");
  await tourFrame(page, 900);
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("LiDAR supply").first()).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText(/tokens/).first()).toBeVisible();
  await settle(page);
  await shot(page, "03-chat-answer");
  await tourFrame(page, 2600);

  await page
    .getByRole("button", { name: /^Source 1:/ })
    .first()
    .click();
  await expect(page.getByText("Open in document")).toBeVisible();
  await shot(page, "04-citation-preview");
  await tourFrame(page, 2200);

  await page.getByText("Open in document").click();
  await expect(page.locator("mark").first()).toBeVisible();
  await page.waitForTimeout(800);
  await shot(page, "05-document-viewer");
  await tourFrame(page, 2200);

  await page.goto(`/w/${WORKSPACE}/documents`);
  await expect(page.getByText("Q3 2026 Board Update").first()).toBeVisible();
  await shot(page, "06-documents");
  await tourFrame(page, 2000);

  await page.goto(`/w/${WORKSPACE}/search`);
  await page.getByLabel("Search query").fill("parental leave");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.locator("mark").first()).toBeVisible();
  await shot(page, "07-search");
  await tourFrame(page, 2000);

  await page.goto(`/w/${WORKSPACE}/insights`);
  await expect(page.getByText("Tokens saved")).toBeVisible();
  await page.waitForTimeout(900);
  await shot(page, "08-insights");
  await tourFrame(page, 2600);

  await page.goto(`/w/${WORKSPACE}/settings`);
  await page.getByRole("tab", { name: "Answering" }).click();
  await shot(page, "09-settings-answering");
  await page.getByRole("tab", { name: "API keys" }).click();
  await expect(page.getByText("Demo integration")).toBeVisible();
  await shot(page, "10-api-keys");
  await tourFrame(page, 1600);
});

test("dark theme", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await signIn(page, "owner");
  await page.goto(`/w/${WORKSPACE}/chat`);
  const latest = page.locator(`a[href*="/w/${WORKSPACE}/chat/"]`).first();
  await latest.click();
  await expect(page.getByText(/saved/).first()).toBeVisible();
  await shot(page, "11-dark-chat");
});
