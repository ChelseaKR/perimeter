# Changelog

All notable changes to perimeter are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added, marker audit and page checks

- **`docs/MARKERS.md`, the marker audit.** Every value this project treats as a
  missing-data marker rather than as a recorded value, with its evidence, the document it
  can be checked against, its effect on the published figures and a confidence. Two
  further published sources are now cited alongside the layers' coded-value domains:
  FRAP's Wildland Fire Perimeters metadata document and CAL FIRE's DINS database
  dictionary, both linked from the dataset pages and both recorded in `PROVENANCE.md`.
- **Every field carries the basis of its markers.** `FieldSpec.basis` is `published` when
  every declared value appears in a published domain or definition, and `inferred` when at
  least one was read off the acquired file. It is in `schema.py`, in the JSON artifacts as
  `marker_basis`, and on the pages beside each field's marker list. Twelve of the
  twenty-seven fields that declare a vocabulary are published; fifteen are inferred. The
  module docstring previously said nothing in the file was inferred, which was not true of
  the free-text fields, and is corrected.
- **`marker_counterfactuals` in the perimeter artifact.** The local-incident-number
  duplicate key, recomputed with the all-zeros placeholder read as a number, so the cost
  of that judgment call is a counted number rather than a claim in prose.
- **HTML conformance and WCAG gates in CI.** `make verify` now ends in `make pages`:
  `html-validate` for HTML conformance and markup-level accessibility, and `axe-core` in a
  headless jsdom for the WCAG 2.0, 2.1 and 2.2 A and AA rule sets. Nothing is served and
  nothing is deployed; both read files off disk. `tests/test_pages_html.py` covers the same
  structural ground from Python with no toolchain beyond it, measures contrast
  arithmetically over both palettes, and asserts that every number a page prints traces to
  the pipeline output.

### Changed, marker audit

- **`UTILITYMISCSTRUCTUREDISTANCE`: `NA` and `N/A` are now one finding.** CAL FIRE
  publishes Not Applicable for this field spelled `NA`, and for the propane-tank field on
  the same form spelled `N/A`. In the acquired file the two spellings never share an
  incident and fall on opposite sides of the 2020 incidents, recorded distances appear on
  both sides of that line, and both spellings sit beside a propane Not Applicable at the
  same rate. Both are now counted as the published finding. Recorded value moves from
  31,239 (23.6%) to 37,783 (28.5%), recorded as unknown from 6,544 to 0, and
  `outside_published_domain` from 243 to 6,787, since the domain published today does not
  carry the `N/A` spelling.
- **`SITEADDRESS`: two placeholder addresses are no longer counted as addresses.** The
  marker net matches single tokens, so `No Address Available` (513 records) and a composed
  placeholder reading `NULL NULL UNKNOWN CA 00000` (160) were passing through it as
  recorded addresses. Recorded value moves from 124,811 (94.2%) to 124,138 (93.7%).
- **The all-zeros local incident number is endorsed, and relabelled.** The treatment is
  unchanged and no figure moves. Its basis is corrected from published to inferred: FRAP
  publishes no domain for `INC_NUM`, and the reading rests on the field's published
  definition, "Number assigned by the Emergency Command Center of the responsible agency
  for the fire", together with the distribution of the file.
- Pages gained a `main` landmark and a skip link, a caption and scoped headers on every
  table with a row header on every row, and the heading level the index page was skipping.
  The light-theme green moved from `#1baf7a` to `#189a6b` so the three state colours clear
  3:1 against both surfaces.
- `irwin_present_tenths_pct` per year and `damage_values_tenths_pct` are now published in
  the JSON artifacts, so every share a page prints is a share the pipeline published.

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
  have made thousands of unrelated fires appear to share one incident. FRAP publishes no
  domain for that field, so the reading is an inference; `docs/MARKERS.md` sets out the
  evidence and counts the other reading beside it.
- Several DINS free-text fields carry marker words where a value would go, `CITY` most
  often. Each is declared per field with a note, so they are counted as markers rather than
  read as place names.
- Some DINS coded fields carry values outside their published domain, `ROOFCONSTRUCTION`
  and `EXTERIORSIDING` most often. These are counted and published as
  `outside_published_domain` rather than raising, because they are ordinary values and
  crashing on them would hide them.
