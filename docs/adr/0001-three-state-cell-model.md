# Count every cell in one of three states, and never collapse them

- Status: Accepted
- Date: 2026-08-15 (back-filled; the decision is as old as `cells.py`)
- Deciders: Chelsea Kelly-Reif

## Context

The obvious way to measure completeness is two-valued: a cell either has a value
or it does not, and the completeness figure is the share that do. Applied to
these two datasets that produces figures that are arithmetically correct and
substantively false.

FRAP's `CAUSE` has no empty cells at all. It carries the published code for
`Unknown / Unidentified` on 10,514 of 23,334 records. `C_METHOD` is the same
shape, with 15,081 recorded as `Unknown`. A two-state count calls both fields
100% complete. FRAP's own firep25_1 release note records editing 12,097
collection methods from null to `Unknown`, which is a data-quality improvement
that a two-state count would read as no change at all, or as a jump to
completeness.

The opposite error is available too. CAL FIRE's DINS damage field records
`No Damage` on 54,414 structures and `Inaccessible` on 591. `No Damage` is an
inspector's finding. Treating it as an absence would erase the inspection.

## Decision

Every measured cell is classified into exactly one of three states, and all
three counts are always published:

- **Recorded value.** Something was written down. Includes a genuine zero and
  includes findings of absence such as `No Damage`, `No Eaves` and
  `Not Applicable`, which are observations.
- **Recorded as unknown.** A published code or a reviewed marker meaning the
  value could not be determined. Somebody recorded that determination failed.
- **Empty cell.** Nothing was written.

The type system enforces the separation rather than trusting a convention: a
`Cell` that is not present raises `MissingValueError` from `value()`, so no
rendering layer can read a blank as a zero by accident. `cells.py` holds the
model; `schema.py` holds the per-field registry that decides which state a given
literal maps to.

A share whose denominator is empty is published as absent, in words, rather than
as a number.

## Consequences

Every field needs a reviewed decision about which of its literals mean "could
not be determined", which is real work and is the subject of ADR-0003. There is
no generic completeness number for a field; there are three, and a reader has to
look at all three. The figures are lower than a two-state count would give and
harder to put in a headline, which is the point: "54.9% recorded" is the sentence
FRAP's own metadata supports and "100% complete" is not.

This record is worth superseding if a source appears whose absence semantics do
not fit three states. A field that distinguishes "not applicable to this
structure" from "applicable but undetermined" is already being squeezed: both
land in `recorded value` and `recorded as unknown` respectively today, and the
per-field notes in `docs/MARKERS.md` carry the difference in prose rather than in
the counts.
