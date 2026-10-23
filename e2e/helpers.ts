import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import { expect, type Page } from "@playwright/test";

export const API_URL = process.env.API_URL ?? "http://localhost:8110";
export const PASSWORD = process.env.DEMO_PASSWORD ?? "";
export const WORKSPACE = "northwind-robotics";

export const PEOPLE = {
  owner: { email: "ava.martin@northwind.example", name: "Ava Martin" },
  editor: { email: "leo.chen@northwind.example", name: "Leo Chen" },
  viewer: { email: "maya.patel@northwind.example", name: "Maya Patel" },
} as const;

export function requirePassword(): string {
  if (!PASSWORD) throw new Error("Set DEMO_PASSWORD (make e2e reads it from deploy/compose/.env)");
  return PASSWORD;
}

const SESSIONS = path.resolve(__dirname, ".auth");

/** Sign in through the form, exactly as a person does. */
export async function signInWithForm(
  page: Page,
  who: keyof typeof PEOPLE = "owner",
): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(PEOPLE[who].email);
  await page.getByLabel("Password").fill(requirePassword());
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/w\/[^/]+\/chat/);
}

/**
 * A signed-in page for one demo person. The session cookie from the first form sign-in is
 * reused by later tests: the API allows ten sign-ins a minute per address, and the suites
 * would otherwise trip that limit themselves. A stale cookie (after `make down`) falls back
 * to the form.
 */
export async function signIn(page: Page, who: keyof typeof PEOPLE = "owner"): Promise<void> {
  const saved = path.join(SESSIONS, `${who}.json`);
  if (existsSync(saved)) {
    await page.context().addCookies(JSON.parse(readFileSync(saved, "utf8")));
    await page.goto("/");
    await page.waitForURL(/\/(w\/[^/]+\/chat|login)/);
    if (!page.url().includes("/login")) return;
    await page.context().clearCookies();
  }
  await signInWithForm(page, who);
  mkdirSync(SESSIONS, { recursive: true });
  writeFileSync(saved, JSON.stringify(await page.context().cookies()));
}

/** Wait until the page has settled: no pending network, fonts ready, transitions finished. */
export async function settle(page: Page): Promise<void> {
  await page.waitForLoadState("networkidle");
  await page.evaluate(async () => {
    await document.fonts.ready;
    // Spinners and pulsing dots repeat forever; only wait for animations that end.
    const finite = document
      .getAnimations()
      .filter((animation) => animation.effect?.getTiming().iterations !== Infinity);
    await Promise.all(finite.map((animation) => animation.finished.catch(() => undefined)));
  });
}
