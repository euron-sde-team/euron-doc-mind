/**
 * Exploratory QA crawl: every page at desktop and mobile widths, signed in as the demo owner.
 *
 * A page fails on console errors, uncaught exceptions, failed or 4xx/5xx requests, sideways
 * scrolling, broken internal links and serious or critical axe violations (WCAG 2 A and AA).
 * A full-page capture of every page lands in e2e/.qa/ for a visual review.
 */
import { mkdirSync } from "node:fs";
import path from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { API_URL, WORKSPACE, settle, signIn } from "../helpers";

const OUT = path.resolve(__dirname, "../.qa");
mkdirSync(OUT, { recursive: true });

const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "mobile", width: 390, height: 844 },
] as const;

const SETTINGS_TABS = ["General", "Answering", "Members", "API keys", "Activity"];

type Crawl = { page: Page; viewport: string; problems: string[]; links: Set<string> };

function watch(page: Page, viewport: string): Crawl {
  const crawl: Crawl = { page, viewport, problems: [], links: new Set() };
  page.on("console", (message) => {
    if (message.type() === "error") crawl.problems.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => crawl.problems.push(`uncaught: ${error.message}`));
  page.on("requestfailed", (request) => {
    const reason = request.failure()?.errorText ?? "";
    // Aborted requests are navigations away or cancelled queries, not failures.
    if (!reason.includes("ERR_ABORTED"))
      crawl.problems.push(`request failed: ${request.url()} ${reason}`);
  });
  page.on("response", (response) => {
    if (response.status() >= 400)
      crawl.problems.push(`HTTP ${response.status()}: ${response.url()}`);
  });
  return crawl;
}

async function inspect(crawl: Crawl, name: string): Promise<void> {
  const { page } = crawl;
  await settle(page);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  if (overflow > 1) crawl.problems.push(`${name}: scrolls sideways by ${overflow}px`);

  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  for (const violation of axe.violations) {
    if (violation.impact !== "serious" && violation.impact !== "critical") continue;
    const nodes = violation.nodes
      .slice(0, 3)
      .map((node) => node.target.join(" "))
      .join(" | ");
    crawl.problems.push(`${name}: axe ${violation.id} (${violation.impact}) at ${nodes}`);
  }

  const hrefs = await page.$$eval('a[href^="/"]', (anchors) =>
    anchors.map((a) => a.getAttribute("href") ?? ""),
  );
  for (const href of hrefs) crawl.links.add(href.split("#")[0]);
  await page.screenshot({ path: path.join(OUT, `${crawl.viewport}-${name}.png`), fullPage: true });
}

async function visit(crawl: Crawl, name: string, url: string): Promise<void> {
  const response = await crawl.page.goto(url);
  expect(response?.status(), url).toBeLessThan(400);
  await inspect(crawl, name);
}

async function firstId(page: Page, path: string, key: "items" | null): Promise<string> {
  const response = await page.request.get(`${API_URL}/api/v1/workspaces/${WORKSPACE}${path}`);
  expect(response.ok(), path).toBeTruthy();
  const body = await response.json();
  const items = key ? body[key] : body;
  expect(items.length, `${path} has items`).toBeGreaterThan(0);
  return items[0].id as string;
}

for (const viewport of VIEWPORTS) {
  test.describe(`${viewport.name} ${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test("signed-out pages", async ({ page }) => {
      const crawl = watch(page, viewport.name);
      await visit(crawl, "sign-in", "/login");

      expect(crawl.problems).toEqual([]);
    });

    test("every workspace page", async ({ page }) => {
      await signIn(page, "owner");
      const crawl = watch(page, viewport.name);
      const conversation = await firstId(page, "/conversations", null);
      const document = await firstId(page, "/documents", "items");

      await visit(crawl, "chat", `/w/${WORKSPACE}/chat`);
      await visit(crawl, "conversation", `/w/${WORKSPACE}/chat/${conversation}`);
      await visit(crawl, "documents", `/w/${WORKSPACE}/documents`);
      await visit(crawl, "document", `/w/${WORKSPACE}/documents/${document}`);
      await visit(crawl, "search", `/w/${WORKSPACE}/search`);
      await page.getByLabel("Search query").fill("annual leave");
      await page.getByRole("button", { name: "Search" }).click();
      await expect(page.locator("mark").first()).toBeVisible();
      await inspect(crawl, "search-results");
      await visit(crawl, "insights", `/w/${WORKSPACE}/insights`);
      await visit(crawl, "settings", `/w/${WORKSPACE}/settings`);
      for (const tab of SETTINGS_TABS) {
        await page.getByRole("tab", { name: tab }).click();
        await inspect(crawl, `settings-${tab.toLowerCase().replace(" ", "-")}`);
      }

      for (const link of crawl.links) {
        const response = await page.request.get(link);
        if (response.status() >= 400)
          crawl.problems.push(`broken link: ${link} (${response.status()})`);
      }
      expect(crawl.problems).toEqual([]);
    });
  });
}
