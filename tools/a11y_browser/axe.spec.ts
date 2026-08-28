import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { SITE_DIR, pagesUnderTest, urlFor } from "./pages";

/**
 * The same axe rule sets `tools/a11y.mjs` runs in jsdom, run in a real engine.
 *
 * jsdom does no layout and paints no pixels, so four rules land in `incomplete` there
 * and are declared in that file with a reason and with where each is covered instead.
 * A browser computes geometry and colour, so it decides all four, and this run has no
 * declared-undecidable list at all: an undecided rule fails here, full stop. That is
 * the strongest form of the rule `tools/a11y.mjs` argues for, and it is only available
 * because something is doing layout.
 *
 * The two runs are kept rather than one replacing the other. The jsdom run needs no
 * browser binary and is the floor when one is unavailable; this run is the ceiling.
 */

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"];

test(`the build in ${SITE_DIR} holds pages to check`, () => {
  expect(pagesUnderTest().length).toBeGreaterThan(0);
});

for (const name of pagesUnderTest()) {
  test(`axe in a browser: ${name}`, async ({ page }) => {
    await page.goto(urlFor(name));
    const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();

    const violations = results.violations.map(
      (v) => `[${v.impact}] ${v.id}: ${v.help}\n    ${v.nodes.map((n) => n.target.join(" ")).join("\n    ")}`,
    );
    expect(violations, `${name}: accessibility violations`).toEqual([]);

    // An undecided rule is not a passing rule. There is nothing this engine cannot
    // decide, so anything landing here is a finding rather than a known gap.
    const undecided = results.incomplete.map(
      (v) => `${v.id}: ${v.help}\n    ${v.nodes.map((n) => n.target.join(" ")).join("\n    ")}`,
    );
    expect(
      undecided,
      `${name}: axe ran these rules in a real browser and still could not decide them. ` +
        "That is not a pass.",
    ).toEqual([]);
  });
}
