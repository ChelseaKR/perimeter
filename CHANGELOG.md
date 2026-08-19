# Changelog

All notable changes to perimeter are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed, the WCAG gate called a rule it could not decide a rule that passed

- **`tools/a11y.mjs` read only axe's `violations` bucket.** axe returns four: `passes`,
  `violations`, `inapplicable`, and `incomplete`, the rules it ran and could not decide.
  Anything undecided was invisible to the gate, which printed `ok <page>` and a closing
  `N page(s) clean against 6 rule sets`, and exited 0. Measured 2026-08-18 against a page
  carrying a focusable link inside `aria-hidden="true"`, a real 4.1.2 problem that axe
  files as undecided in jsdom: the gate reported the page as clean and exited 0. Same for
  an `<iframe>` axe could not reach into, whose contents were therefore never checked at
  all. This is the repository's own subject, "could not determine" rendered as a
  recorded value, in the check that backs its accessibility claim. An undecided rule now
  fails the gate unless it is declared in `UNDECIDABLE_HERE` with the reason and with
  where the rule's subject is checked instead.
- **What was not decided is now printed on every run, passing or failing.** The gate's
  only output format said "clean against 6 rule sets" while three rules per page were
  undecided and named nowhere. Each page's line now carries its undecided count and rule
  ids, and the run ends with every declared rule, why it cannot be decided here, and
  where it is covered. A declared rule axe never reports is marked as such, so a
  declaration that has stopped matching anything does not sit in the file looking like
  coverage.
- **The gate had no failure evidence at all**, while `tools/determinism.sh` had thirteen
  cases and ADR 0004 requires it. `tests/test_a11y_gate.py` runs it against fourteen
  inputs: no argument, a missing directory, a directory with no pages, an image with no
  alt text, a page with no `lang`, one bad page among good ones, a focusable link inside
  `aria-hidden`, an untested frame, and the disclosure a clean run owes.
- **`make verify` runs `node-sync` before `test`.** The new gate tests need
  `node_modules` present, and without this they would skip, and a skipped gate test reading
  as a passing one being the same failure. They refuse to skip when `CI` is set. Make
  builds each target once per invocation, so `pages` naming `node-sync` too costs
  nothing.
- **README's Accessibility conformance row said "two axe rules suppressed for want of a
  renderer", which was wrong in both halves.** Measured: three rules come back undecided
  on all three pages (`color-contrast`, `landmark-one-main`, `page-has-heading-one`), and
  `target-size`, named as one of the two, appears in neither `violations` nor
  `incomplete` on any page. It was never suppressed; it never fires. Two of the three
  are decided from the markup in `tests/test_pages_html.py`, so the substantive gap is
  one rule, not two.

### Changed, the conformance table is now readable by the thing that reads it

- **`make sync` installs with `uv sync --locked`.** `make lock-check` still runs first
  inside `make verify` and is unchanged, but `make sync` is also documented as an entry
  point on its own, and run that way `--frozen` had no drift gate in front of it.
  `--locked` makes the same comparison `uv lock --check` makes and exits 1 the same way.
- **The Standards Conformance table's verdicts were in a form the portfolio's
  conformance reader rejects.** That reader takes a verdict only when the character
  straight after `Applies` is whitespace, `:`, `(`, `-` or an em dash, so `Applies.`,
  `Applies, not met.`, `Applies, Tier C.`, `Applies, L1.` and `Not applicable.` all read
  as invalid, and fifteen accurately written rows scored as one broken cell. The
  verdicts are now `Applies:`, `Applies (not met).`, `Applies (Tier C).`,
  `Applies (L1).` and `N/A (...)`. Not one row's meaning changed, and no gap changed
  state. `tests/test_standards_conformance.py` enforces the new grammar and says why the
  punctuation is load-bearing.

### Fixed, a download that could come back short and say nothing

- **The paging walk stepped its offset by the page it asked for, not the page it got.**
  `resultOffset` means "skip this many records", so a layer that caps a page below
  `PAGE_SIZE` and sets `exceededTransferLimit` leaves a block of records between the end
  of the page and the next offset. Stepping by `PAGE_SIZE` walked over that block and the
  walk still ended normally: against a layer holding 5,000 records and capping pages at
  1,000, the acquisition collected 3,000 and reported success. The published counts would
  have described three fifths of a layer as the whole of it, with a hash and a retrieval
  date beside them. Both layers publish `maxRecordCount` 2000 today, which is why the
  acquisition on record is complete: the layers' own `returnCountOnly` totals, read
  2026-08-16, are 23,334 and 132,522, exactly the counts in `sources.py`. The walk now
  advances by the length of the page it was handed.
- **An acquisition is checked against the layer's own record total before anything is
  written.** `layer_record_count` asks the layer how many records match the same
  predicate the walk uses, and `acquire` refuses, writing no file, when the two disagree.
  Short reads of any cause now stop instead of arriving as a smaller dataset.
- **Schema drift is checked on every row, not on the first one.** The check read
  `rows[0]` alone, so it could not fail on any file whose first row was intact: a column
  that disappeared further down was classified as an empty cell for every later record
  and published as a field nobody filled in. Measured at DINS scale the per-row check
  costs nothing detectable, 4.56s against 4.58s over 132,522 rows.
- **The published artifacts must have measured every record they say was acquired.**
  `records` and `source.acquired_record_count` are two counts of the same file taken at
  two different moments, and nothing compared them.
- **`tests/test_acquire.py` enforces its own claim** that the real endpoints are never
  contacted. It was a convention; an autouse fixture now fails any test that reaches for
  a socket.

### Changed, gates that could not fail

- **The determinism check is a script with its own tests.** The inlined version could not
  fail: a workflow `run:` block uses `bash -e` without `pipefail`, so `find` on a missing
  directory exited 1 into a pipeline that reported success, and with no files to hash both
  runs came out identical, so an empty build passed. Both runs also went into the same
  directory. `tools/determinism.sh` compares two trees, refuses an empty or missing one,
  and `tests/test_determinism_gate.py` runs it against thirteen cases that should fail it.
- **`make lock-check` is the lockfile-drift gate**, running `uv lock --check`.
  `uv sync --frozen` was doing that job and cannot: measured 2026-08-15 against a
  `pyproject.toml` this lockfile does not satisfy, `uv lock --check` exits 1,
  `uv sync --locked` exits 1, `uv sync --frozen` exits 0. Every target after it runs
  `uv run`, which rewrites `uv.lock`, so the old arrangement went green and then repaired
  what it was checking. `uv sync --frozen` stays as the install.
- **The coverage floor no longer omits the module that touches the network.**
  `src/perimeter/acquire.py` was excluded, which moved the reported figure from 88% to
  100% and let the 90% floor pass over the one module carrying this project's promises
  about somebody else's server. `tests/test_acquire.py` exercises those promises offline
  with `urlopen` substituted: HTTPS only, the honest User-Agent, stopping on 401, 403 and
  429 rather than working around them, refusing a non-JSON challenge page, refusing an
  ArcGIS error payload, the pause between pages, and the paging walk. Nothing is omitted
  and the tree is genuinely at 100%.
- **`ci.yml` no longer calls its gates merge-blocking.** `main` has no ruleset and no
  branch protection, so `verify`, `secret-scan` and `sast` report and block nothing. The
  header says that. `.github/rulesets/main.json` carries the `protect-main` profile that
  would make the old sentence true, committed and deliberately not applied.

### Added, workflow scanning and standards onboarding

- **zizmor and CodeQL.** Nothing in this repository read `.github/workflows/` until now,
  which is why five dependabot pull requests that change nothing but `pages.yml` carry
  green checks from jobs that never open the file. zizmor runs online, because its offline
  default silently skips the audits that need the API. CodeQL covers actions, python and
  javascript-typescript, and fails when there is no SARIF to read as well as when there
  are findings.
- **`docs/adr/`**, which had existed and been empty since the scaffold while the decisions
  it should hold were argued in prose. Back-filled: the three-state cell model, counting an
  out-of-domain value rather than raising on it, and the published-versus-inferred marker
  basis. Plus a new one, ADR-0004, on what it takes to adopt a gate here.
- **A Standards Conformance table in `README.md`** and a `.standards-version` pin, read by
  `tests/test_standards_conformance.py` so neither is decoration. The table records the
  gaps as gaps, and states that the standards program's applicability manifest has no
  entry for this repository, so the scoping is this table's reading rather than the
  registry's.
- `.github/CODEOWNERS`, routing workflows, the ruleset directory, dependabot config and
  the two reviewed registries.

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
