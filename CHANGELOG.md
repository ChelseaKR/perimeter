# Changelog

All notable changes to perimeter are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Three-state cell model** (`cells.py`, `schema.py`). Every measured cell is counted as a
  recorded value, a recorded unknown, or an empty cell, and the three are never collapsed.
  A non-present `Cell` will not hand over a value, so no rendering layer can read a blank
  as a zero. Coverage is a first-class output: all three counts are always published, and a
  share over an empty denominator is published as absent rather than as a number.
- **Fail-closed drift refusal.** A measured column going missing raises `SchemaDriftError`.
  A cell holding something that reads like a missing-data marker, in a field that has not
  declared that exact marker, raises `SentinelDriftError`. The reviewed registry declares
  markers per field, because the same word means different things in different columns:
  `None` is a published street-type finding and `None` in a parcel APN is not.
- **Measurement one: FRAP historical fire perimeter completeness.** 23,334 records across
  fire years 1878 to 2025 from version firep25_1. Records per year with IRWIN ID coverage
  inside each year (3,633 records carry one, 15.6%), per-field three-state counts, records
  per decade against the 10/50/300 acre figures in FRAP's published collection criteria,
  and counts of records sharing an identifier, published as candidates rather than as
  duplicates.
- **Measurement two: DINS damage inspection coverage.** 132,522 structure records across
  451 incidents. Per-field and per-incident completeness, the damage vocabulary reported
  with `No Damage` and `Inaccessible` kept distinct from blanks, and field completeness
  split between assessed records and the 591 recorded as `Inaccessible`, which is the
  measurement that separates "not inspected" from "inspected, field blank".
- **Deterministic artifacts.** `site/data/*.json` and the three pages are byte-identical
  across re-runs on the same inputs. No wall clock in any payload, integer arithmetic for
  every published share, sorted keys throughout.
- **Acquisition, kept separate from the build** (`acquire.py`). Reads the GeoServices
  endpoints listed among each dataset's own published resources, geometry excluded, with a
  User-Agent naming the project. Raises `AcquisitionBlocked` and stops if an endpoint
  declines; there is no fallback path and nothing retries under another identity. The build
  never touches the network.
- **Hand-written fixtures**, not sampled from the acquired files, because DINS records
  carry real addresses and parcel numbers. Each fixture value exercises one classification
  case: a genuine zero, an empty cell, a published unknown code, a marker word, a finding
  of absence, a value outside the published domain, a structure that could not be reached,
  and a record with no year.
- `PROVENANCE.md` with per-source endpoint, licence, version, retrieval date, record count,
  byte count and SHA-256, the publishers' own caveats quoted, and an explicit list of what
  is excluded and why. `tests/test_provenance.py` fails if it drifts from `sources.py`.

### Notes on the source files

Observations from the retrieved files, recorded because they shape how the counts read.
Neither is a defect report and neither is presented as one on the pages.

- FRAP's `CAUSE` and `C_METHOD` have no empty cells at all, and carry the published
  `Unknown` code on 10,514 and 15,081 records respectively. FRAP's firep25_1 release note
  records editing 12,097 collection methods from null to Unknown, which is exactly the kind
  of move a two-state count would hide.
- An all-zeros local incident number appears on 12,469 perimeter records across many units
  and decades. It is counted apart from recorded numbers; reading it as an identifier would
  have made thousands of unrelated fires appear to share one incident.
- Several DINS free-text fields carry marker words where a value would go, `CITY` most
  often. Each is declared per field with a note, so they are counted as markers rather than
  read as place names.
- Some DINS coded fields carry values outside their published domain, `ROOFCONSTRUCTION`
  and `EXTERIORSIDING` most often. These are counted and published as
  `outside_published_domain` rather than raising, because they are ordinary values and
  crashing on them would hide them.
