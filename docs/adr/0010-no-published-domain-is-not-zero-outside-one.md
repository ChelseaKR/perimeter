# A field with no published domain reports absence, not zero, outside one

- Status: Accepted
- Date: 2026-09-01
- Deciders: Chelsea Kelly-Reif

## Context

ADR-0002 decided that an ordinary value outside a published coded-value domain is
counted and published in its own bucket, `outside_published_domain`, rather than
raised as an error. That is right, and it was implemented as a property of the
value rather than of the field: `FieldSpec.outside_domain` answers False for any
cell whose field has no `domain_values`, and `field_coverage` summed that answer
for every field alike.

Thirty of the fifty-four measured fields have no published domain. `FIRE_NAME`,
`UNIT_ID`, `COUNTY`, `SITEADDRESS` and twenty-six others are free text, and both
publishers say plainly which of their fields they constrain and which they do
not. Summing "is this value outside the domain?" across a field that has no
domain produced `0`, and `0` was published: on both pages as a row with no note
about the domain, and in both JSON artifacts as
`"outside_published_domain": 0` with a distinct count of `0` and an empty value
object beside it.

That zero is a measurement nobody took. It is indistinguishable in the artifact
from `CAUSE`, which does have a published domain and does hold every value in it,
and it says the file and the domain agree about a domain that does not exist. It
is the same shape ADR-0006 found in `YEARBUILT`: a counter that had nothing to
count, publishing its emptiness as a finding. `tests/test_schema.py` already
carried `test_free_text_fields_have_no_domain_to_be_outside_of`, which asserts
exactly this at the `FieldSpec` level; the fact was known and was lost one layer
up, where the counting happens.

The list of named out-of-domain values has a second, smaller version of the same
problem. It is capped at `OUTSIDE_DOMAIN_VALUE_CAP`, twelve, so a field with a
thousand spellings does not publish a thousand-key object. Nothing said the list
was capped. No field reaches the cap today, so nothing has been misread yet; a
truncated list that does not say it is truncated reads as the whole set.

## Decision

The four out-of-domain measures are absent, together, for a field the layer
publishes no domain for. In the artifacts they are `null`, the same way
`present_tenths_pct` is `null` where there is no denominator. On the pages the
row says so in words: "The layer publishes no coded-value domain for this field,
so no value here is counted as outside one."

Zero keeps its meaning, and it is now the narrow one: the domain was published,
it was read, and the file holds nothing outside it.

Silence on a row means exactly one thing, and the paragraph under every
three-state field table says which: the field has a published domain and holds
nothing outside it. The three states a row can be in are named there, so a reader
does not have to work out what a missing note means.

`outside_published_domain_values_listed` is published beside
`outside_published_domain_distinct`: how many of the values found the object
actually names. Where they differ, the list stopped at the cap.

## Consequences

Two of the artifacts' field keys change type from `int` to `int | null` and one
object key from `{}` to `null`, for the thirty fields concerned. A consumer
summing `outside_published_domain` across fields has to skip nulls, which is the
correct arithmetic and was not available before: adding thirty zeros that meant
"not measured" to twenty-four that meant "measured, none found" produced a total
nobody could interpret.

Both measurement pages gain a note on every free-text row and a paragraph under
each field table. That is thirty rows of text bought for one distinction, and the
distinction is the project's subject.

The committed `site/` was rebuilt from the acquired files for this change.
`tests/test_published_site_is_current.py` would have caught the artifacts going
stale, because the new key changes the shape it compares; it would not have
caught the pages, which change only inside `<main>`. `make site-check` is added
for that: a full rebuild from `data/raw/` diffed against `site/`, refusing
outright when the acquired files are absent. It cannot run in CI, because those
files are not in git and never will be.

The observation that should supersede this record is a field whose domain is
published for some records and not others, which neither `FieldSpec` nor this
model can express: `domain_values` is one frozen set per field, and there is no
per-record answer to "was there a domain to check this against?".
