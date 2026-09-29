import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// The six nav surfaces and one finished research report. Each must render its
// content from the recorded API with no console errors, and pass axe's WCAG
// 2.1 A/AA rules at "serious" or worse, apart from the documented exceptions.
const REPORT_RUN = "5ba1b3f0-9531-4185-be3c-6a272f61220d"; // VRT, completed 2026-09-27

const PAGES: Array<{ path: string; expectText: RegExp }> = [
  { path: "/", expectText: /needs attention|briefing/i },
  { path: "/status", expectText: /healthy|imminent|stale|triggered|broken/i },
  { path: "/themes", expectText: /Neo-clouds/ },
  { path: "/filings", expectText: /filings/i },
  { path: "/performance", expectText: /Verdict outcomes/i },
  { path: "/library", expectText: /VRT/ },
  { path: `/pipeline/${REPORT_RUN}`, expectText: /Vertiv/ },
];

// Rules with known, tracked violations; remove an entry once it's fixed.
const KNOWN_A11Y_EXCEPTIONS: string[] = [];

for (const { path, expectText } of PAGES) {
  test(`${path} renders and passes axe`, async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });
    page.on("pageerror", (err) => errors.push(err.message));

    await page.goto(path);
    await page.waitForLoadState("networkidle");
    await expect(page.getByText(expectText).first()).toBeVisible();
    expect(errors, "console errors").toEqual([]);

    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    const blocking = results.violations
      .filter((v) => v.impact === "serious" || v.impact === "critical")
      .filter((v) => !KNOWN_A11Y_EXCEPTIONS.includes(v.id))
      .map((v) => `${v.id} (${v.impact}): ${v.nodes.length} node(s) — ${v.help}`);
    expect(blocking, "axe serious/critical violations").toEqual([]);
  });
}
