# A split publishes every population, including the one it does not show

- Status: Accepted
- Date: 2026-08-27
- Deciders: Chelsea Kelly-Reif

## Context

`completeness_by_access` reports each DINS field twice: once over records with a
damage assessment, once over records recorded as `Inaccessible`. That split is
the point of the table, and ADR-0001 is why: a blank on a structure nobody could
reach is not the same fact as a blank on one an inspector walked up to.

Both populations are read off `DAMAGE`. A record whose `DAMAGE` is blank, or
holds a marker, answers neither question, and `access_field_coverages` built its
two denominators from the two populations that answer. So such a record left the
table without appearing anywhere in it. Measured over four records, one assessed,
one inaccessible, one with a blank damage field and one holding a marker, the two
denominators summed to two, and nothing published said which two records were
missing or that any were.

`AccessSplit` has counted `damage_not_recorded` and `damage_explicit_unknown`
since it was written, precisely so that a record in that state would be reported
rather than folded into the assessed population. Both are zero in the 2026-08-07
retrieval. That is why this held for a year: every denominator happened to be
complete, and the table had no way to say so and no way to say otherwise.

This is the same shape as the coverage exclusion in ADR-0004 and the audit gate
in ADR-0006. A measurement was computed over a set that excluded part of what it
should have included, the exclusion was invisible in the output, and the check
around it was green because the excluded part was empty on the day.

## Decision

Where this project splits a population and reports the parts, it accounts for
every record it was handed, and publishes the part it does not show.

`AccessFieldCoverage` carries a third population, derived by subtraction from the
records handed in rather than by a third predicate, so the three partition the
input by construction and a damage state nobody anticipated cannot fall between
them. `counted_records` is the sum, and it is asserted equal to the record count
in the code, in the published artifact, and in the committed `site/`.

The page states what its two columns are counted over and what is in neither.
When the third population is empty it says that in words, because "every record
is in one of these two columns" is a fact worth printing and its absence is what
made this invisible.

The pages show two of the three. Showing a permanently empty pair of columns
would be worse for a reader than a sentence, and the counts are in the artifact
either way, per field.

## Consequences

A future damage value this project has not seen still lands somewhere countable,
and the page still adds up. The cost is a sentence under a table that will, on
current data, always say the same thing, and one more field in every
`completeness_by_access` row of a 1.5 MB artifact.

What this does not do is generalise. `field_coverage` already counts every record
it is handed and `dins_report` hands it all of them, which is now asserted by
`tests/test_field_notes.py`. The per-incident blocks partition the file, with the
records attributable to no incident counted separately. Those were checked while
writing this and were sound. But nothing here stops the next split from being
written the same way the first one was. The rule is stated in this record; there
is no mechanism that applies it to a split nobody has written yet.
