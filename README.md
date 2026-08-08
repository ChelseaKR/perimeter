# Perimeter

Two coverage measurements over California's public wildfire datasets, published as counts.

CAL FIRE and FRAP document the limits of these datasets carefully, in their own metadata.
What is not published alongside them is the arithmetic behind those sentences: how many records per year,
how many carry a federal identifier, how many cells in each field hold a value, how many
hold a code meaning the value could not be determined, and how many hold nothing at all.
This project counts exactly that and publishes it beside the sentence it answers.

**Unofficial. Not affiliated with or endorsed by CAL FIRE, FRAP, or any California state
agency.** This is not a review of an agency's work. Every measurement operationalizes a
limitation the publisher already states.

## The two measurements

**Historical fire perimeter completeness** (`site/perimeters.html`) over FRAP's
California Historical Fire Perimeters, version firep25_1, retrieved 2026-08-07:

- 23,334 perimeter records, covering fire years 1878 to 2025. 77 records carry no year and
  are counted as their own cohort rather than being attached to a neighbouring year.
- 3,633 records carry an IRWIN ID (15.6%), reported per year so the transition is visible
  rather than asserted. FRAP's own release note describes the new Global ID as covering
  records "pre-dating IRWIN IDs".
- Cause has no empty cells and 10,514 records carrying the published code for
  `Unknown / Unidentified`, so it is 54.9% recorded rather than complete. Collection
  method is the same shape: no empty cells, 15,081 recorded as `Unknown`, 35.4% recorded.
  Counting only nulls would call both fields complete.
- 12,469 records carry an all-zeros local incident number, counted apart from the 9,910
  recorded numbers.
- Records sharing an identifier, counted as candidates: 8 IRWIN IDs used by more than one
  record, covering 23 records.
- Surviving records counted per decade against the 10, 50 and 300 acre figures in FRAP's
  published collection criteria.

**Damage inspection coverage** (`site/dins.html`) over CAL FIRE's DINS data, retrieved
2026-08-07:

- 132,522 structure records across 451 incidents.
- Damage is recorded on every record. 54,414 of them (41.1%) say `No Damage`, which is an
  inspection finding rather than a null and rather than a zero. 591 say `Inaccessible`:
  identified, could not be reached.
- Field completeness reported separately for assessed records and inaccessible ones, so a
  blank on a structure nobody could get to is not counted as the same fact as a blank on
  one that was inspected.
- Construction attributes are where the three-state split matters most. Eaves is recorded
  on 56.6% of records, carries `Unknown` on 52,364, and is blank on 5,214.
- Per-incident completeness for every incident, because an average across the file
  describes no incident in particular.

## How absence is handled

Every measured cell is counted in one of three states, and the three are never collapsed:

| State | Meaning |
|---|---|
| **Recorded value** | A value the agency wrote down. Includes a genuine zero, and includes findings of absence such as `No Damage`, `No Eaves` or `Not Applicable`, which are observations. |
| **Recorded as unknown** | A published code or a reviewed marker meaning the value could not be determined. Somebody recorded that determination failed. |
| **Empty cell** | Nothing was written. CAL FIRE states for DINS that "Attributes with null values could not be determined." |

A null is not a zero. A structure not inspected is not a structure without damage. Where a
share would have no denominator, the output says so in words instead of printing a number.

The build fails closed. A column this project measures going missing raises
`SchemaDriftError`. A cell holding something that reads like a missing-data marker, in a
field that has not declared that exact marker, raises `SentinelDriftError` rather than
being guessed at. Every marker currently declared was read in its own field's context and
carries a note saying why: `None` is a published street-type finding, while `None` in a
parcel APN is a marker standing in for an absent parcel match.

An ordinary value outside a published domain is deliberately *not* an error. It is counted
and published as `outside_published_domain`, because it is a real thing about the file and
crashing on it would hide it.

## Build

```sh
uv sync
make verify          # lint, format, types, tests, audit
make site-offline    # build from committed fixtures; runs anywhere, no network
```

To build from CAL FIRE's real files, acquire them first (see `PROVENANCE.md`):

```sh
uv run python -m perimeter.acquire --out data/raw
make site
```

Output is deterministic: the same inputs produce byte-identical JSON and HTML. There is no
wall clock anywhere in the artifacts, retrieval dates come from the reviewed constants in
`src/perimeter/sources.py`, and every published share is computed with integer arithmetic.

`data/raw/` is gitignored and CI never touches the network. A build from fixtures stamps
`is_fixture: true` and publishes `null` for every acquisition fact, so fixture output
cannot pass itself off as a measurement of the real files.

## Scope

Coverage measurement only. This project does not model fire risk, does not track
incidents, does not compute damage or loss totals, and does not republish any address,
parcel number or assessed value. Those lanes are well served by others. What is measured
here is how much of each published field is actually filled in, and what the blanks mean.

## Layout

| Path | |
|---|---|
| `src/perimeter/cells.py` | The three states, and the rule that a non-present cell will not hand over a value |
| `src/perimeter/schema.py` | The reviewed field registry: every domain, marker and finding-of-absence, per field |
| `src/perimeter/records.py` | Classify every measured cell at the edge, or refuse the file |
| `src/perimeter/perimeters.py` | FRAP year cohorts, duplicate signals, acreage against the published criteria |
| `src/perimeter/dins.py` | DINS incident grouping and the assessed/inaccessible split |
| `src/perimeter/coverage.py` | The two reports |
| `src/perimeter/artifacts.py` | Deterministic JSON |
| `src/perimeter/render.py` | The static pages |
| `src/perimeter/acquire.py` | The only code that touches the network. Run by hand, never in CI |
| `site/` | The built pages and their JSON artifacts |
| `PROVENANCE.md` | Per-source detail, quoted caveats, and what is excluded |

## Licence

Apache-2.0. Source data is published by CAL FIRE under a Creative Commons Attribution
licence and is reproduced here only as counts.
