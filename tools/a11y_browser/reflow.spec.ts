import { expect, test, type Page } from "@playwright/test";

import { SITE_DIR, pagesUnderTest, urlFor } from "./pages";

/**
 * WCAG 2.2 SC 1.4.10 Reflow (AA), the one criterion axe cannot decide in any engine.
 *
 * axe evaluates the DOM it is handed and has no opinion about the viewport that DOM was
 * laid out in, so a page can pass every axe rule and still force a reader to scroll
 * sideways to read each line at 320 CSS pixels. README.md listed this under "what still
 * needs a person" on the reasoning that reflow needs a viewport. The first half is
 * right; the second does not follow, because a headless browser has one.
 *
 * 320 x 256 is the criterion's own reference: 1280 x 1024 at 400% zoom. It is where a
 * reader at 400% browser zoom lands, and it is most phones.
 *
 * SC 1.4.10 allows horizontal scrolling for content that genuinely needs a second
 * dimension. These pages carry wide data tables, which is the canonical example, and
 * they already sit inside `overflow-x: auto` containers, which is the conforming
 * pattern. Flagging their cells would be flagging the fix, so an element inside a
 * scroller is exempt. What the criterion forbids is the *page* scrolling, and that is
 * asserted absolutely.
 */

const REFLOW_VIEWPORT = { width: 320, height: 256 } as const;

/** One CSS pixel of slack for sub-pixel layout rounding, not for overflow. */
const ROUNDING_SLACK_PX = 1;

test.use({ viewport: REFLOW_VIEWPORT });

type Overflow = { selector: string; right: number; width: number };

async function auditReflow(page: Page, name: string): Promise<void> {
  const response = await page.goto(urlFor(name));
  expect(response, `no response for ${name}`).not.toBeNull();

  const documentOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(
    documentOverflow,
    `${name} scrolls horizontally at ${REFLOW_VIEWPORT.width}px: content is ` +
      `${documentOverflow}px wider than the viewport (WCAG 2.2 SC 1.4.10 Reflow)`,
  ).toBeLessThanOrEqual(ROUNDING_SLACK_PX);

  const spilling: Overflow[] = await page.evaluate((slack) => {
    const limit = document.documentElement.clientWidth + slack;
    const describe = (el: Element): string => {
      const id = el.id ? `#${el.id}` : "";
      const cls =
        typeof el.className === "string" && el.className
          ? `.${el.className.trim().split(/\s+/).join(".")}`
          : "";
      return `${el.tagName.toLowerCase()}${id}${cls}`;
    };
    const insideScroller = (el: Element): boolean => {
      for (
        let node = el.parentElement;
        node && node !== document.body;
        node = node.parentElement
      ) {
        const overflowX = getComputedStyle(node).overflowX;
        if (overflowX === "auto" || overflowX === "scroll") return true;
      }
      return false;
    };
    const out: Array<{ selector: string; right: number; width: number }> = [];
    for (const el of Array.from(document.body.querySelectorAll("*"))) {
      const box = el.getBoundingClientRect();
      // A zero-area node is collapsed or hidden and cannot be what a reader is
      // scrolling to reach.
      if (box.width === 0 || box.height === 0) continue;
      if (insideScroller(el)) continue;
      // Two shapes of one failure, and the second is the one a layout inspector hides:
      // the element's box is wider than the viewport, or the box fits and its content
      // does not, which is a long unbreakable string inside a correctly sized block.
      const contentSpills =
        getComputedStyle(el).overflowX === "visible" &&
        el.scrollWidth > el.clientWidth + slack;
      if (box.right > limit || contentSpills) {
        out.push({
          selector: describe(el),
          right: Math.round(Math.max(box.right, box.left + el.scrollWidth)),
          width: Math.round(Math.max(box.width, el.scrollWidth)),
        });
      }
    }
    // An overflowing child drags every ancestor with it, and a hundred repetitions of
    // one fact is not a hundred findings.
    const seen = new Set<string>();
    return out.filter((o) => (seen.has(o.selector) ? false : (seen.add(o.selector), true)));
  }, ROUNDING_SLACK_PX);

  const detail = spilling
    .map((o) => `  ${o.selector} right edge ${o.right}px, width ${o.width}px`)
    .join("\n");
  expect(
    spilling,
    `${name}: element(s) extend past a ${REFLOW_VIEWPORT.width}px viewport ` +
      `(WCAG 2.2 SC 1.4.10 Reflow):\n${detail}`,
  ).toEqual([]);
}

test(`the build in ${SITE_DIR} holds pages to check`, () => {
  expect(pagesUnderTest().length).toBeGreaterThan(0);
});

for (const name of pagesUnderTest()) {
  test(`reflow at 320px: ${name}`, async ({ page }) => {
    await auditReflow(page, name);
  });
}
