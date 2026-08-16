# An ordinary value outside a published domain is counted, not raised

- Status: Accepted
- Date: 2026-08-15 (back-filled; the decision is as old as `records.py`)
- Deciders: Chelsea Kelly-Reif

## Context

This project fails closed in two places. A column it measures going missing
raises `SchemaDriftError`. A cell holding something that reads like a
missing-data marker, in a field that has not declared that exact marker, raises
`SentinelDriftError` rather than being guessed at. Both refusals exist because
guessing would turn an absence into a value, which is the thing this project
exists not to do.

The tempting third refusal is the symmetric one: raise when a coded field holds
a value that is not in its published coded-value domain. It looks like the same
discipline. It is the opposite.

An out-of-domain value is a real thing about the file. `ROOFCONSTRUCTION` and
`EXTERIORSIDING` in the DINS data both carry them. So does
`UTILITYMISCSTRUCTUREDISTANCE`, where CAL FIRE publishes Not Applicable spelled
`NA` for one field and `N/A` for another on the same form, and the acquired file
carries both spellings; 6,787 records fall outside the domain published today.
Raising on those would mean the build cannot run at all until somebody widens a
domain, and the pressure to widen it to get a green build is exactly the pressure
that produces a fabricated measurement.

## Decision

An ordinary value outside a published domain is counted and published in its own
bucket, `outside_published_domain`. It is not an error and it is not silently
folded into "recorded value" or "recorded as unknown" either.

The distinction from `SentinelDriftError` is what the value looks like, not
whether it is in the domain. A value that reads like a missing-data marker in a
field that has not declared it still raises, because misreading a marker changes
an absence into a value. A value that reads like data still counts, because it
is data the publisher wrote down that their own domain does not describe.

## Consequences

The build survives a source that starts publishing something new, and the new
thing shows up as a number on the page rather than as a crash in a log. A reader
gets told the domain and the file disagree, per field, which is a finding rather
than a defect report: both publishers document which fields they constrain.

The cost is that `outside_published_domain` can grow quietly. Nothing alerts on
it changing, and a field whose out-of-domain count doubles between retrievals
would be visible only to somebody comparing two published artifacts. That is the
observation that should supersede this record: a threshold or a diff between
retrievals, so growth is noticed rather than merely available.
