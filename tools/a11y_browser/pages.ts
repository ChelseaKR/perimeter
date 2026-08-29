import { readdirSync, statSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { join, resolve } from "node:path";

/**
 * The directory under test, and the pages in it.
 *
 * A gate that can find nothing to examine fails rather than passing (ADR-0004), so
 * both of these throw rather than returning an empty list. Playwright reports a throw
 * at collection time as an error and exits non-zero, which is the behaviour wanted:
 * "no pages were checked" must never read as "no problems were found".
 */
export const SITE_DIR = resolve(
  process.env.PERIMETER_SITE_DIR ?? join(__dirname, "..", "..", "build", "site-offline"),
);

export function pagesUnderTest(): string[] {
  let entries: string[];
  try {
    entries = readdirSync(SITE_DIR);
  } catch (error) {
    throw new Error(
      `cannot read ${SITE_DIR}: ${(error as Error).message}. Build the pages first: make site-offline`,
    );
  }
  const pages = entries
    .filter((name) => name.endsWith(".html"))
    .filter((name) => statSync(join(SITE_DIR, name)).isFile())
    .sort();
  if (pages.length === 0) {
    throw new Error(`no .html files in ${SITE_DIR}; build the pages first: make site-offline`);
  }
  return pages;
}

export const urlFor = (name: string): string => pathToFileURL(join(SITE_DIR, name)).href;
