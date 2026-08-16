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

**Status:** Beta. Version `0.1.0`, first signed tag not yet cut. Both measurements are
computed, tested, and published against pinned dataset retrievals (FRAP `firep25_1` and CAL
FIRE DINS, retrieved 2026-08-07). The figures move only when those retrievals are deliberately
refreshed.

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
  recorded numbers. FRAP publishes no domain for that field, so this reading is an
  inference and the page says so. Reading the value as a number instead would report
  12,230 records as sharing an incident key rather than 376. Both counts are published;
  the evidence is in `docs/MARKERS.md`.
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
- The distance from a residence to a utility or miscellaneous structure is recorded on
  37,783 records (28.5%). CAL FIRE publishes Not Applicable for that field spelled `NA`
  and publishes it for the propane-tank field spelled `N/A`; the file carries both
  spellings in the utility field, in eras that do not overlap, and both are counted as
  the published finding. See `docs/MARKERS.md`.

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

## Which judgment calls rest on what

Twenty-seven of the fifty-four measured fields declare a marker, a code or a finding of
absence. Twelve of those are **published**: the value is in the layer's own coded-value
domain, or in FRAP's metadata document, or in CAL FIRE's DINS database dictionary. The
other fifteen are **inferred**: the field is free text, or the value is one the published
domain does not carry, and this project read it off the acquired file.

Both are counted the same way, and neither is a defect in either dataset. Both publishers
document the domains they constrain and say which fields are free text. What differs is
how much weight a reader should put on the call, so every field carries its basis in
`schema.py`, in the JSON artifacts as `marker_basis`, and on the pages beside its marker
list.

`docs/MARKERS.md` is the audit: per field, the declared values, the evidence, the URL it
can be checked against, the effect on the published figures, and a confidence. Where a
call has a counterfactual worth counting, it is counted rather than described, and
published in the artifact under `marker_counterfactuals`.

## Build

```sh
uv sync
npm ci
make verify          # lockfile, lint, format, types, tests, SCA, page checks, determinism
make site-offline    # build from committed fixtures; runs anywhere, no network
```

`make verify` includes `make pages`, which builds the pages from the committed fixtures and
checks them two ways: `html-validate` for HTML conformance and the markup-level
accessibility rules, and `axe-core` in a headless DOM for the WCAG 2.0, 2.1 and 2.2 A and
AA rule sets. Nothing is served and nothing is deployed; both read the files off disk. The
same gate runs in CI.

### What the page checks cover, and what still needs a person

Gated, in CI:

- HTML conformance, heading order, duplicate ids, landmark structure, `lang`, and every
  table header carrying a `scope` and every table a caption. Checked twice, by
  `html-validate` and by parser-based assertions in `tests/test_pages_html.py`.
- The WCAG A and AA rule sets that axe-core can decide in a DOM with no layout.
- Contrast. Both palettes are data in `render.py`, so every foreground and background the
  stylesheet puts together is measured against the WCAG thresholds, in both themes,
  arithmetically. This is the one criterion axe cannot check headlessly, because jsdom
  paints nothing.
- Every number in a table cell or a tile traces to the JSON artifact, and every number in
  prose is either one of those, part of a quote from the publisher, or on a reviewed list
  in `tests/test_pages_html.py` with a reason.

**Not checked, and needing human eyes:**

- **Visual layout.** Nothing here renders the pages. Column widths, the wide tables inside
  their scroll containers, the tile grid at its wrapping points, and whether the sticky
  table headers behave are all unverified.
- **Small screens and reflow.** WCAG 2.2 SC 1.4.10 needs a viewport. The pages are built
  to reflow, and that has not been observed.
- **Print.** No print stylesheet is defined and no print output has been looked at.
- **Focus appearance in practice.** A focus ring is defined and the skip link is present
  and points at the main landmark, but SC 2.4.11 is about how the indicator looks against
  what is behind it, which needs a renderer.
- **Target size.** SC 2.5.8 needs box geometry, which jsdom does not compute.
- **A screen reader.** Conformant markup is not the same as a good listening experience.
  Nothing here substitutes for reading a page with one.

To build from CAL FIRE's real files, acquire them first (see `PROVENANCE.md`):

```sh
uv run python -m perimeter.acquire --out data/raw
make site
```

Output is deterministic: the same inputs produce byte-identical JSON and HTML. There is no
wall clock anywhere in the artifacts, retrieval dates come from the reviewed constants in
`src/perimeter/sources.py`, and every published share is computed with integer arithmetic.
`make determinism` is the check behind that sentence: two builds into two directories,
compared by `tools/determinism.sh`, which refuses an empty or missing tree rather than
calling it a match. `tests/test_determinism_gate.py` runs that script against trees that
should fail it, so the gate is known to be able to fail.

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
| `tools/a11y.mjs` | axe-core over the built pages in a headless DOM |
| `tools/determinism.sh` | Compare two build trees; refuse an empty or missing one |
| `site/` | The built pages and their JSON artifacts |
| `PROVENANCE.md` | Per-source detail, quoted caveats, and what is excluded |
| `docs/MARKERS.md` | The marker audit: every judgment call, its evidence, and what it costs |

## Standards conformance

This repository is held to the portfolio's shared engineering standards, pinned in
`.standards-version` to `v2.0.0`. Every row states what is true on 2026-08-15, not what is
intended. "Applies, not met" is a recorded gap; a blank state is a defect and
`tests/test_standards_conformance.py` fails on one.

Read one caveat first. The standards program's applicability manifest has no entry for
this repository, so nothing has ever decided which of the fifteen standards bind it. The
scoping below was derived here, from each standard's own applicability section, and it is
this table's reading rather than the registry's. A manifest entry supersedes it.

| Standard | State |
|---|---|
| Code Quality | Applies. uv, ruff, mypy `--strict`, pytest with branch coverage at 100% over `src/` with nothing omitted, against a 90% floor. `make lock-check` runs `uv lock --check`, because CQ-09's prescribed `uv sync --frozen` exits 0 on lockfile drift (measured 2026-08-15) |
| Security & Supply-Chain | Applies. semgrep, gitleaks, pip-audit, `npm audit`, CodeQL over actions/python/javascript, every action SHA-pinned, `permissions: contents: read` at the top of every workflow, `persist-credentials: false` on every checkout. Not met: no SBOM, no OpenSSF Scorecard workflow, no `osv-scanner` alongside pip-audit (SEC-11, SEC-13), no scheduled trufflehog run (SEC-19), and Dependabot alerts are disabled on the repository, so SEC-15 has nothing to read |
| CI/CD | Applies, not met. `main` has no ruleset and no branch protection, so the gates report and block nothing. The `protect-main` profile is committed at `.github/rulesets/main.json` and deliberately not applied; applying it is a live repository setting |
| Observability | Applies, Tier C. A library and a CLI writing to stdout, plus static pages with no script. No hosted service, no telemetry, no SLO surface. Not met: no operations runbook |
| Accessibility | Applies. html-validate and axe-core over the built pages in CI, contrast measured arithmetically over both palettes, and the same structural floor asserted from Python. Not met: no ACR, two axe rules suppressed for want of a renderer, and the manual checks README names under "What still needs a person" are unverified |
| Internationalization | Applies, not met. Civic data presented to the public is in scope per I18N section 1, and these pages are English only with no catalog and no `docs/I18N.md` declaration |
| AI Evaluation | Not applicable. No model, no LLM, no generated text anywhere in the pipeline or the pages |
| Quality & Metrics | Applies. Fail-closed gates throughout: schema drift, sentinel drift, the coverage floor, and page checks that fail on a number no pipeline produced. Not met: no Definition of Done and no metrics ledger |
| Documentation | Applies. README, `PROVENANCE.md`, `docs/MARKERS.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, `CITATION.cff`, a `docs/adr/` log, this table, and a `.standards-version` pin that `tests/test_standards_conformance.py` reads |
| Release & Versioning | Applies, not met. Version `0.1.0` in `pyproject.toml` and `CITATION.cff`, no tag cut, no signed tag, no release workflow, no published artifact |
| Responsible-Tech Framework | Applies. Unofficial framing on every served page, no claim about any agency's infrastructure or security posture, no address, parcel number or assessed value republished, and an acquisition path that stops rather than routing around an access control. Not met: no dated ethics, transparency or residual-risk artifacts |
| Performance | Applies, not met. Three static pages, no script shipped, no web font; that is a good starting position and it is not a measurement. No budget recorded and no Lighthouse run |
| Incident Response | Applies. `SECURITY.md` routes reports to GitHub private vulnerability reporting with a 72-hour acknowledgment SLA. Not met: no severity convention, no secret-leak runbook, no committed-postmortem requirement |
| Data Governance | Applies, L1. Openly licensed public civic data, republished only as counts. Handled defensively above the tier because the DINS file carries site addresses and parcel numbers: `data/raw/` is gitignored, fixtures are hand-written rather than sampled, and no identifying field is republished. Not met: `PROVENANCE.md` carries source, licence, version, retrieval date, record count, byte count and hash per source, but no refresh cadence, staleness SLA or stated tier |
| AI Development Measurement | Applies, not met. No baseline and no outcome metrics recorded for this repository's development stream |

## Licence

Apache-2.0. Source data is published by CAL FIRE under a Creative Commons Attribution
licence and is reproduced here only as counts.
