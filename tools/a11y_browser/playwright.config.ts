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
  // This harness reads static files off disk. It has no business reading this
  // repository's git history, and on a `pull_request` run Playwright does more than
  // read it. Its git-info plugin calls `gitDiff`, which runs
  //
  //   git fetch origin <pr base sha> --depth=1 --no-auto-maintenance ...
  //
  // (`node_modules/playwright/lib/runner/index.js`, `gitDiff`). The harness's working
  // directory is inside this work tree, so `--depth=1` writes `.git/shallow` at the
  // repository root, naming `main`'s own tip. `tests/test_release_claims.py` then
  // refuses to read the tag list -- correctly, because a shallow checkout cannot tell
  // an untagged repository from an unfetched one -- and `make verify` fails on a branch
  // whose diff has nothing to do with any of it.
  //
  // It read as intermittent: whether it failed depended on whether pytest-xdist
  // happened to schedule tests/test_a11y_browser_gate.py before the release-claims
  // tests. Measured on a runner 2026-09-06: `.git/shallow` is absent after checkout,
  // absent after `make browser-sync`, and present the moment that one test module runs.
  //
  // The plugin keys off GITHUB_ACTIONS, not CI, which is why setting `CI: ""` in the
  // subprocess environment did not disable it. Turning both halves off here is the
  // durable fix: it holds for `npm test` and for a maintainer running the harness by
  // hand, not only for the path the Python test takes.
  captureGitInfo: { commit: false, diff: false },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
