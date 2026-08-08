# Contributing

## Local gate

```sh
uv sync
npm ci
make verify
```

`make verify` is the single local gate and is byte-for-byte identical to the `verify` job
in `.github/workflows/ci.yml`. If it is green locally, CI is green.

It ends in `make pages`, which builds the pages from the committed fixtures and runs
`html-validate` and `axe-core` over them. That needs node; everything before it needs only
uv. The page checks are duplicated from Python in `tests/test_pages_html.py`, so the
structural floor and the contrast measurement still run if node is unavailable, but a
change to `render.py` is not finished until `make pages` is green.

## The rule that governs changes here

This project publishes counts about other people's data. Two things follow.

**Never widen a marker set to make a build pass.** If `SentinelDriftError` fires, the
source has started using a value this project has not reviewed. The fix is to read that
value in its own field's context, decide what it means, and add it to that field's
`FieldSpec` with a note saying why. Adding it to `SUSPECTED_SENTINELS` or to an unrelated
field to clear the error turns an absence into a value, which is the one thing this
project exists not to do.

**Never publish a number that was not counted.** No estimates, no interpolation across a
gap, no rate over an empty denominator. Where a share does not exist, say so in words. A
number stated in page prose is held to the same rule: `tests/test_pages_html.py` fails
unless it came from the pipeline, appears in a quote from the publisher, or is on the
reviewed list in that file with a reason beside it.

**Say what a marker rests on.** Every `FieldSpec` that declares a marker, a code or a
finding of absence carries a `basis`. Use `Basis.PUBLISHED` only when every declared value
is in the layer's coded-value domain or in the publisher's own field definitions, and
`Basis.INFERRED` otherwise, including when only one value out of several is undocumented.
Write the field up in `docs/MARKERS.md` with the evidence, the URL, the effect on the
published figures and a confidence. The tests enforce all of this; the point of it is that
the pages can say which calls a reader should lean on.

## Tone

Every page operationalizes a limitation CAL FIRE or FRAP already documents. Quote the
publisher's own sentence beside the measurement. This is not an audit and must never read
as one. Do not describe any agency's infrastructure, access controls or security posture.

## Data

Only public, openly licensed data, from the endpoints in `PROVENANCE.md`. If an endpoint
declines automated access, document a manual acquisition. Never work around bot
protection, rate limiting or any access control.

## Review

Every PR requires review sign-off before merge. PRs touching `.github/workflows/`,
`src/perimeter/schema.py` or `src/perimeter/sources.py` route to the code owner.
