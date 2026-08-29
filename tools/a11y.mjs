// Run axe-core over every built page, headlessly, in a jsdom DOM.
//
// This is the WCAG gate. It loads each page into a real DOM implementation and runs
// axe-core's WCAG 2.0/2.1/2.2 A and AA rule sets plus the best-practice set, and exits
// non-zero on any violation. It is not a substitute for a human looking at the pages:
// jsdom does no layout and computes no colours, so the rules that depend on rendered
// geometry or on painted pixels cannot fire here. Those are named in README.md under
// "What still needs a person", and colour contrast is measured separately, off the
// palette itself, in tests/test_pages_html.py.
//
// axe returns four buckets, not two: `passes`, `violations`, `inapplicable`, and
// `incomplete`, the rules it ran and could not decide. This gate used to read only
// `violations`, print `ok`, and exit 0. Measured 2026-08-18 against the three built
// pages, three rules land in `incomplete` on every one of them, and a page carrying a
// focusable link inside `aria-hidden="true"`, a real 4.1.2 problem, was reported as
// `ok` and exited 0, because axe filed it as undecided rather than as a violation. An
// undecided rule is not a passing rule. Rendering "could not check" as "clean" is the
// one reading this repository exists to refuse, and it was doing it in its own gate.
//
// So: every undecided rule is named in the output on every run, and an undecided rule
// that has not been declared below, with a reason and with where it is covered instead,
// fails the gate.
//
// Since 2026-08-27 this is the floor rather than the whole gate. `make a11y-browser`
// runs the same rule sets in Chromium, where nothing is undecidable, so every rule
// declared below is now also decided by something. This run is kept because it needs no
// browser binary and because the two engines disagree in a useful direction: the
// browser run immediately found a serious 2.1.1 failure this one cannot see, since
// whether a container scrolls depends on layout and jsdom does none.
//
// Exit codes:
//   0  every page decided, no violations; the declared-undecidable rules are listed
//   1  a violation, or a rule axe could not decide that is not declared below
//   2  no directory given, or no .html files in it
//
// Usage: node tools/a11y.mjs <directory-of-html-files>

import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { JSDOM, VirtualConsole } from "jsdom";
import axe from "axe-core";

const TAGS = [
  "wcag2a",
  "wcag2aa",
  "wcag21a",
  "wcag21aa",
  "wcag22aa",
  "best-practice",
];

// Rules this environment cannot decide, each with why, and with where the thing the rule
// is about is actually checked. Left to run and read as passes they would teach a reader
// the wrong thing; deleted from the tag set they would disappear from the record. Named
// here, they are reported on every run and a reader can see the shape of the gap.
//
// A rule reaching `incomplete` that is not in this map fails the gate. That is the point
// of the map: it is a short list of known, reasoned gaps, not a mute button.
const UNDECIDABLE_HERE = new Map([
  [
    "color-contrast",
    {
      why: "jsdom does no layout and exposes no canvas, so axe cannot sample painted pixels",
      coveredBy:
        "tests/test_pages_html.py measures every foreground/background pair in both palettes against the WCAG thresholds, arithmetically, and tools/a11y_browser/axe.spec.ts decides the rule itself in Chromium",
    },
  ],
  [
    "target-size",
    {
      why: "SC 2.5.8 needs box geometry, which jsdom does not compute",
      coveredBy:
        "tools/a11y_browser/axe.spec.ts, where Chromium computes the geometry and axe decides SC 2.5.8; tests/test_a11y_browser_gate.py runs that spec against a page with 8px targets",
    },
  ],
  [
    "landmark-one-main",
    {
      why: "axe cannot confirm the main landmark is visible without layout, so it reports the page undecided rather than as having one",
      coveredBy:
        "tests/test_pages_html.py asserts exactly one main landmark per page, from the parsed markup, and tools/a11y_browser/axe.spec.ts decides the rule itself in Chromium",
    },
  ],
  [
    "page-has-heading-one",
    {
      why: "axe cannot confirm the h1 is visible without layout, so it reports the page undecided rather than as having one",
      coveredBy:
        "tests/test_pages_html.py asserts exactly one h1 per page, from the parsed markup, and tools/a11y_browser/axe.spec.ts decides the rule itself in Chromium",
    },
  ],
]);

async function checkPage(path) {
  const html = readFileSync(path, "utf8");
  // "outside-only" gives us an eval to inject axe with, without ever running a script
  // that came out of the page. These pages ship no script, and the checker should not
  // start executing one if that ever changes.
  // axe probes for a canvas to decide whether it can sample colours. jsdom has none, so
  // it reports that once per page. Everything else the page or axe says is forwarded.
  const console_ = new VirtualConsole();
  console_.forwardTo(console, { jsdomErrors: "none" });
  console_.on("jsdomError", (error) => {
    if (!/getContext\(\) method/.test(error.message)) {
      console.error(error.message);
    }
  });

  const dom = new JSDOM(html, {
    pretendToBeVisual: true,
    runScripts: "outside-only",
    virtualConsole: console_,
  });
  const { window } = dom;
  window.eval(axe.source);
  // No `resultTypes` restriction. It caps the nodes axe attaches to the buckets it was
  // not asked about, and `incomplete` is now something this gate has to be able to
  // report properly rather than merely count.
  const results = await window.axe.run(window.document, {
    runOnly: { type: "tag", values: TAGS },
  });
  dom.window.close();
  return results;
}

function reportNodes(nodes) {
  for (const node of nodes.slice(0, 5)) {
    console.error(`    at ${node.target.join(" ")}`);
    if (node.failureSummary) {
      console.error(`      ${node.failureSummary.replace(/\n/g, "\n      ")}`);
    }
  }
  if (nodes.length > 5) {
    console.error(`    ...and ${nodes.length - 5} more`);
  }
}

const dir = process.argv[2];
if (!dir) {
  console.error("usage: node tools/a11y.mjs <directory-of-html-files>");
  process.exit(2);
}

let pages;
try {
  pages = readdirSync(dir)
    .filter((name) => name.endsWith(".html"))
    .sort();
} catch (error) {
  console.error(`cannot read ${dir}: ${error.message}`);
  process.exit(2);
}

if (pages.length === 0) {
  console.error(`no .html files in ${dir}; build the site first`);
  process.exit(2);
}

let violationCount = 0;
let undeclaredCount = 0;
// Which declared entries actually turned up, so a declaration that has stopped matching
// anything is visible rather than sitting in the file looking like coverage.
const declaredSeen = new Set();

for (const name of pages) {
  const results = await checkPage(join(dir, name));
  // A rule this environment cannot decide cannot be trusted to have decided against the
  // page either, so the declared set is filtered out of violations as well.
  const violations = results.violations.filter(
    (v) => !UNDECIDABLE_HERE.has(v.id),
  );
  const declared = [];
  const undeclared = [];
  for (const rule of results.incomplete) {
    if (UNDECIDABLE_HERE.has(rule.id)) {
      declared.push(rule);
      declaredSeen.add(rule.id);
    } else {
      undeclared.push(rule);
    }
  }

  if (violations.length === 0 && undeclared.length === 0) {
    const undecided = declared.map((rule) => rule.id).sort();
    const suffix = undecided.length
      ? `, ${undecided.length} undecided (${undecided.join(", ")})`
      : ", none undecided";
    console.log(`ok   ${name}  0 violations${suffix}`);
    continue;
  }

  console.error(`FAIL ${name}`);
  violationCount += violations.length;
  for (const v of violations) {
    console.error(`  [${v.impact}] ${v.id}: ${v.help}`);
    console.error(`    ${v.helpUrl}`);
    reportNodes(v.nodes);
  }
  undeclaredCount += undeclared.length;
  for (const v of undeclared) {
    console.error(`  [undecided] ${v.id}: ${v.help}`);
    console.error(`    ${v.helpUrl}`);
    console.error(
      "    axe ran this rule and could not decide it. That is not a pass. Fix the",
    );
    console.error(
      "    page, or declare the rule in UNDECIDABLE_HERE in tools/a11y.mjs with the",
    );
    console.error("    reason and where it is checked instead.");
    reportNodes(v.nodes);
  }
}

// The disclosure block. It prints on a failing run too: what was not decided is part of
// the result whichever way the result went.
console.error("");
console.error(`not decided here, declared in tools/a11y.mjs:`);
for (const [id, { why, coveredBy }] of UNDECIDABLE_HERE) {
  const seen = declaredSeen.has(id);
  console.error(`  ${id}${seen ? "" : "  [not reported by axe on these pages]"}`);
  console.error(`    why:        ${why}`);
  console.error(`    covered by: ${coveredBy}`);
}

if (violationCount > 0 || undeclaredCount > 0) {
  const parts = [];
  if (violationCount > 0) {
    parts.push(`${violationCount} accessibility violation(s)`);
  }
  if (undeclaredCount > 0) {
    parts.push(`${undeclaredCount} undeclared undecided rule(s)`);
  }
  console.error(`\n${parts.join(" and ")}`);
  process.exit(1);
}

console.log(
  `\n${pages.length} page(s) with no violation and nothing undecided beyond the ` +
    `${UNDECIDABLE_HERE.size} declared rule(s), against ${TAGS.length} rule sets`,
);
