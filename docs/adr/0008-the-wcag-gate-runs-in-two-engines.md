# The WCAG gate runs in two engines, and the browser one declares nothing undecidable

- Status: Accepted
- Date: 2026-08-27
- Deciders: Chelsea Kelly-Reif

## Context

ADR-0004 established that a check is not adopted until it has been seen to fail.
`tools/a11y.mjs` was then rewritten so that a rule axe runs and cannot decide
fails the gate unless it is declared with a reason and with where the rule's
subject is checked instead. That was the right fix for the gate that existed, and
it left four rules declared as undecidable in jsdom, one of which,
`target-size`, was covered by nothing at all and appeared in `README.md` under
"what still needs a person". SC 1.4.10 Reflow was on that list too.

The reasoning for reflow was that it needs a viewport and therefore needs eyes.
The first half is right and the second does not follow. A headless browser has a
viewport, and `ledger` already runs exactly this as a blocking gate.

What was not anticipated is what the second engine would find. Run in Chromium
against the same three pages, axe reported `scrollable-region-focusable` as a
serious violation on both measurement pages. Every wide table on these pages sits
in a container with `overflow-x: auto`, which is the conforming answer to SC
1.4.10, and a container that scrolls and cannot be focused is a SC 2.1.1 Keyboard
failure: it scrolls for a pointer and not for a keyboard, so a sighted keyboard
user cannot read the columns past the right edge. No amount of DOM inspection
finds this, because whether a container scrolls is a fact about layout. The gate
that had been green for three weeks could not have found it, and neither could
any amount of care in writing the markup.

## Decision

The WCAG gate runs in two engines and both are kept.

`tools/a11y.mjs` in jsdom is the floor. It needs no browser binary, it runs
wherever node does, and its declared-undecidable list is the honest record of
what a DOM-only engine cannot settle.

`tools/a11y_browser` in Chromium is the ceiling, and it declares nothing. There
is no undecidable list, because there is no rule this engine cannot decide: a
violation fails it and so does an undecided rule. It also carries SC 1.4.10
Reflow at 320 by 256, which no engine decides from a DOM because it is a property
of the viewport rather than of the document.

Both read the built pages off disk as `file://` URLs. Nothing is served, no port
is opened, and CI reaches the network only to fetch the browser.

`tests/test_a11y_browser_gate.py` is the failure evidence ADR-0004 requires:
eleven cases, including a page that scrolls sideways at 320 pixels, text that
spills out of a correctly sized block, an unfocusable scroll container, text
below the contrast threshold, an 8-pixel pointer target, an empty directory and a
missing one.

Nothing is suppressed anywhere after this, so this repository has no
`waivers.yml`. An empty registry would be a file saying nothing; the absence is
the claim, and the standards row in `README.md` states it.

## Consequences

`make verify` is slower and needs a browser binary. On a cold machine that is a
download; afterwards it is cached. The local gate stays byte-for-byte identical
to CI, which is what `CONTRIBUTING.md` promises, so the cost is paid in both
places or neither.

Two engines can disagree, and when they do the disagreement has to be read rather
than resolved by preference. Today they agree everywhere except where jsdom
abstains. If a future rule fails in one and passes in the other, that is a
finding about the rule or the engines and belongs in this log, not in a
suppression.

The manual list in `README.md` is shorter and now names things that genuinely
need a person: print, focus appearance against real backgrounds, a screen reader,
and looking at the layout. Those are not automatable and saying otherwise would
be the same error in the other direction.

What would supersede this record is a third surface. These are three static
pages with no script and no state, so one browser at one viewport is enough. A
page with interaction, or a second breakpoint worth asserting, would need the
matrix this deliberately does not have.
