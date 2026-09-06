# A field measured as a number refuses a value that is not one

- Status: Accepted
- Date: 2026-09-06
- Deciders: Chelsea Kelly-Reif

## Context

Nine of the fifty-four measured fields declare `numeric=True`. That flag decides
two things: that a recorded zero is a value rather than a blank, and that
`recorded_zero_values` is published for the field so a reader can apply their own
reading to those zeros. It has never decided that the field's cells are numbers.

Exactly one of the nine was ever parsed as a number. `GIS_ACRES` is read through
`perimeters.acres_of`, which calls `records.float_value`, which raises
`SchemaDriftError` on a value it cannot parse. `float_value` has that one caller
and `integer_value` has none outside the tests. The other eight are DINS fields
(`NUMBEROFUNITPERSTRUCTURE`, `NOOUTBUILDINGSDAMAGED`,
`NOOUTBUILDINGSNOTDAMAGED`, `NOOFCARSONPROPERTY`, `YEARBUILT`,
`ASSESSEDIMPROVEDVALUE`, `LATITUDE`, `LONGITUDE`) and nothing in the pipeline
parses any of them. `acquire.py` validates no field types, and
`FieldSpec.classify` sent any non-empty, non-marker string straight to `PRESENT`.

The only place a parse failure could land was inside `field_coverage`:

```python
if spec.numeric:
    try:
        if float(value) == 0:
            zeros += 1
    except ValueError:  # pragma: no cover - numeric drift raises at read time
        pass
```

The comment states the reason the branch is unreachable, and that reason was true
of one field in nine. Measured against the committed DINS fixture: setting
`ASSESSEDIMPROVEDVALUE` to `1,250,000`, `NOOFCARSONPROPERTY` to `two` and
`LATITUDE` to `38.5N` on all ten records raised nothing, and every mutated cell
came out `present`. An upstream export that starts writing thousands separators,
a units suffix, or a stray letter would have been published as a full set of
recorded measurements on both pages and in both artifacts, silently.

Two things followed, and the second is worse than the first. The pages would
report a reformatted column as completely recorded, which is the exact misreading
this project exists to refuse. And `recorded_zero_values` would silently read 0
for such a field, because every failed parse was discarded before it could be
counted; the ADR-0006 zero gate skips any field publishing no recorded zeros, so
the audit would go quiet at the moment that field's numbers stopped meaning
anything.

The `# pragma: no cover` is what makes this load-bearing rather than merely
unproven. It waives the branch off the 100% branch-coverage floor, so the one
mechanism that would otherwise ask "has anybody shown this can happen?" was
switched off on the strength of a reason that was false for eight fields.

The tempting alternative was to classify an unparseable value as a fourth state
rather than raise: `not_recorded`, or a new bucket beside `explicit_unknown`.
It was rejected below.

## Decision

`FieldSpec.classify` refuses a recorded value that is not a number in a field
declared `numeric=True`, raising `SchemaDriftError` with the same message
`float_value` already raises for `GIS_ACRES`:

```
{where}.{field}: {text!r} is not a number; this field is measured as one
```

The refusal is at the edge, in `classify`, not at the count. `records.py` states
the contract this follows: parsing happens once, at the edge, and a row that
cannot be classified stops there rather than reaching a page. A check inside
`field_coverage` could only decide what to do with a value that has already been
classified as a recorded measurement, which is one layer too late, and it would
have to be repeated by every other consumer of a numeric cell.

Order is preserved: a blank is still `not_recorded` and a declared marker is
still `explicit_unknown`, both decided before this check. `YEARBUILT`'s `0` is
the case that matters, and it stays a marker rather than being read as the number
zero. A declared `recorded_absence` on a numeric field would be refused, and
there is no such declaration today; the check sits on the one helper both present
paths return through, so a future one cannot slip past it.

The `try` and its pragma come off `field_coverage`. The parse there cannot fail,
and that claim is now true rather than asserted in a comment.

## Consequences

**A file that was published before may now be refused.** This is the point, and
it is still a cost. The acquired DINS file is 132,522 records and is not in git,
so nothing in CI can tell us whether every cell in those eight fields parses
today. If one does not, the next `make site` stops instead of publishing, and
clearing it means a decision about that value written up in `docs/MARKERS.md`,
not a code change. The published artifacts give some assurance: five of the eight
publish non-zero `recorded_zero_values`, which only counts cells that parsed.

**A refusal is a worse experience than a classification, and a better one than a
wrong number.** Classifying an unparseable value as a fourth state would keep the
build green and put the judgment on the page. It was rejected because there is no
honest reading to publish: `1,250,000` is not missing data, not an unknown
marker, and not a measurement this project can count, and inventing a state for
it would mean choosing between them without evidence. `CONTRIBUTING.md` is
explicit that this project does not guess in that position. The asymmetry that
made `GIS_ACRES` stop the build and the other eight silent was never a decision
anybody made; this makes the nine behave alike.

**The refusal cannot distinguish drift from a single typo.** One malformed cell
in 132,522 stops the whole read, exactly as it already does for `GIS_ACRES` and
for an unreviewed sentinel. That is deliberate here for the same reason it is
there: this project publishes coverage figures, and a figure computed over a file
it could not fully read is the thing it refuses to publish.

The observation that should supersede this record is a numeric field whose
publisher documents a non-numeric placeholder. That is a declared marker, not
drift, and it belongs in `unknown_markers` where `YEARBUILT`'s `0` already is;
if one arrives whose placeholder varies per record, neither `FieldSpec` nor this
record can express it.
