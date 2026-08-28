import { defineConfig, devices } from "@playwright/test";

/**
 * Browser-real accessibility gate over the pages `make site-offline` builds.
 *
 * `tools/a11y.mjs` runs axe in jsdom, which does no layout and paints no pixels, so
 * four rules come back undecided there and are declared in that file with a reason.
 * A real engine decides all four. This harness is the other half: same pages, same
 * rule sets, in Chromium, plus WCAG 2.2 SC 1.4.10 Reflow, which axe does not check in
 * any engine because it is a property of the viewport rather than of the DOM.
 *
 * Nothing is served. The pages are static files with no script and no external asset,
 * so the specs read them straight off disk as `file://` URLs: no port, no server, and
 * nothing for CI to reach over the network. `PERIMETER_SITE_DIR` points the same specs
 * at another build directory, which is how `tests/test_a11y_browser_gate.py` runs them
 * against pages that must fail.
 *
 * No retries. These are static files and a flake here would be a real defect in the
 * harness, not a cold start to absorb.
 */
export default defineConfig({
  testDir: ".",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
