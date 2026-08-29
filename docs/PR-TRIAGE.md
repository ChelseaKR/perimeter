# Pull request triage, 2026-08-28

Nine open pull requests, four open issues. Six of the nine are stacked in two chains of
three; three are Dependabot bumps against `main`.

Read-only triage. Nothing was committed, pushed, retargeted or merged to produce it.

## Headline findings

1. **No PR in this queue is failing CI.** All nine are `mergeStateStatus: CLEAN` with
   every check `SUCCESS`. The Actions-budget starvation seen elsewhere in this portfolio
   is not present here: every run has real steps and a real conclusion.
2. **`codeql` never ran on four of the nine.** `.github/workflows/codeql.yml` triggers on
   `pull_request: branches: [main]` only, so #27, #28, #30 and #31 have four checks where
   the `main`-targeting PRs have six. This is not a failure, but their CodeQL result is
   *absent*, not green. Retargeting them to `main` runs it for the first time.
3. **The two stacks collide.** Merging both, in any order, conflicts in `CHANGELOG.md`,
   `site/dins.html` and `src/perimeter/render.py`. The conflicts are mechanical, and the
   sizing is in "Cross-stack collisions" below.
4. **#31 arms a wall-clock time bomb.** `tests/test_data_cards.py` calls `date.today()`.
   The DINS retrieval goes stale on 2027-02-03, and from **2027-02-04** every CI run and
   every `make verify` on every branch goes red until someone re-acquires a 163 MB file.
   This is deliberate and documented. It is still the single highest-consequence thing in
   the queue and it should be a decision, not a side effect.
5. **Nothing here should be closed.** No PR is stale, duplicated or superseded. That is
   unusual for a queue written by parallel agents and it is worth saying plainly.

## The stack

```
main
 |
 +-- #29  feat/a11y-in-a-real-browser            (-> main)
 |     |
 |     +-- #30  docs/the-manifest-entry-exists   (-> feat/a11y-in-a-real-browser)
 |           |
 |           +-- #31  feat/data-cards-and-a-staleness-gate
 |                                               (-> docs/the-manifest-entry-exists)
 |
 +-- #26  fix/notes-that-claim-a-denominator     (-> main)
 |     |
 |     +-- #27  fix/yearbuilt-zero-is-not-a-year (-> fix/notes-that-claim-a-denominator)
 |           |
 |           +-- #28  fix/by-access-accounts-for-every-record
 |                                               (-> fix/yearbuilt-zero-is-not-a-year)
 |
 +-- #20  dependabot setup-uv 10.0.1             (-> main)
 +-- #21  dependabot ruff 0.16.3                 (-> main)
 +-- #22  dependabot configure-pages 6.0.0       (-> main)
```

**Auto-close exposure.** Merging a base with `--delete-branch` has already auto-closed a
dependent PR once in this repository. The exposed pairs are:

| Merging and deleting | Auto-closes |
|---|---|
| #29 `feat/a11y-in-a-real-browser` | **#30** |
| #30 `docs/the-manifest-entry-exists` | **#31** |
| #26 `fix/notes-that-claim-a-denominator` | **#27** |
| #27 `fix/yearbuilt-zero-is-not-a-year` | **#28** |

#20, #21 and #22 have no dependents and expose nothing.

## Per PR

### #26 A field note is published output, and two of them were false
- **Base:** `main`. **CI:** all six green.
- **What it does.** `FieldSpec.note` is copied verbatim into `site/data/*-coverage.json`,
  so it is published prose, not a code comment. Two DINS notes claimed the field was
  counted over "the affected subset rather than the whole file". No such subset exists;
  `field_coverage` counts every record it is handed. Rewrites both notes and adds
  `tests/test_field_notes.py`, four gates plus negative controls. Closes #23.
- **Correctness: good.** Gate 1 genuinely fails without the change: the shipped note
  contains all three of `affected subset`, `rather than the whole file` and
  `read against the`, which is exactly what the gate greps for. Verified by string
  inspection against the pre-change `schema.py`, not taken from the PR body.
  The author already identified that gates 2 and 3 pass in both states and gave each its
  own reject-this-input test rather than leaving them decorative. That is the discipline
  this portfolio usually lacks.
- **One note.** Gate 3 requires a quotation to appear on a line of `docs/MARKERS.md` that
  names the field. Both new quotations do, at `docs/MARKERS.md:181` and `:182`. Verified.
- **Overlaps:** none in source. `CHANGELOG.md` collides with stack A.
- **Recommendation: `merge`.** Merge first of the two stack bases.

### #27 Nothing was built in year 0
- **Base:** `fix/notes-that-claim-a-denominator` (#26). **CI:** four green, no CodeQL.
- **What it does.** 12,148 DINS records carry `YEARBUILT` of literal `0`, counted until
  now as a recorded construction year. Declares `0` an inferred unknown marker, adds a
  MARKERS.md section, and adds a gate requiring every numeric field publishing recorded
  zeros to be written up in the audit. Closes #24.
- **Correctness: good, and the arithmetic checks out.** `present` moves 102,091 -> 89,943,
  `explicit_unknown` 0 -> 12,148, `not_recorded` unchanged at 30,431, and the three still
  sum to 132,522. 89,943/132,522 = 67.9%, matching the README's "77.0% to 67.9%".
  Recomputed independently from both artifacts.
- **The new gate is not vacuous.** I checked the pre-change `docs/MARKERS.md` for all six
  numeric fields that publish recorded zeros (`NUMBEROFUNITPERSTRUCTURE`,
  `NOOUTBUILDINGSDAMAGED`, `NOOUTBUILDINGSNOTDAMAGED`, `NOOFCARSONPROPERTY`, `YEARBUILT`,
  `ASSESSEDIMPROVEDVALUE`). **None of the six appeared.** The gate fails on all six
  without this change and covers all six after it.
- **Two weaknesses, neither blocking.**
  - The gate is a whole-document substring test (`` `FIELD` `` anywhere in MARKERS.md),
    where #26's sibling gate is per-line. A field mentioned in passing satisfies it.
  - It is self-retiring for the field it was written for: once `0` becomes a marker,
    `recorded_zero_values` for `YEARBUILT` drops to 0 and the gate's `if not zeros:
    continue` skips it forever. The other five keep it honest.
  - `test_every_published_zero_in_a_numeric_field_is_written_up` is parametrized over both
    artifacts, and the `perimeters-coverage.json` case is vacuous because FRAP publishes no
    recorded zeros. Harmless here because the DINS case carries the test.
- **Overlaps:** conflicts with #29 in `site/dins.html` and `CHANGELOG.md`.
- **Recommendation: `merge after retargeting to main`** once #26 is in.

### #28 An access table whose denominators could hold fewer records than the file
- **Base:** `fix/yearbuilt-zero-is-not-a-year` (#27). **CI:** four green, no CodeQL.
- **What it does.** The by-access table counted assessed and inaccessible records. A record
  whose `DAMAGE` cell is blank or holds a marker is in neither, so it appeared in no
  denominator and a reader adding the columns would find the file short. Adds a third
  `undetermined` population, published per field in the JSON and stated in page prose.
- **Correctness: good.** `undetermined` is the literal complement of `is_assessed` and
  `is_inaccessible`, so the three populations partition the input by construction. The
  complement is also exactly `AccessSplit.damage_not_recorded + damage_explicit_unknown`,
  which this repository has always counted at the file level, so the change is the
  existing discipline applied one level down rather than a new claim. Verified by reading
  both predicates in `src/perimeter/dins.py:105-114`.
- **The empty-population trap is handled.** The new population is empty in the real file,
  so the `if undetermined:` branch in `render.py` is unreachable from fixtures. Rather
  than leaving dead code, `test_the_page_names_the_records_the_access_columns_leave_out`
  injects `undetermined_total=3` via `dataclasses.replace` and asserts the other branch's
  sentence is *absent*. Both branches are exercised. This is the right answer and it is
  the reason the repo's 100% branch coverage floor still holds.
- **Overlaps:** conflicts with #29 in `src/perimeter/render.py`, `site/dins.html` and
  `CHANGELOG.md`.
- **Recommendation: `merge after retargeting to main`** once #27 is in.

### #29 Run the WCAG gate in an engine that does layout, and fix what it found
- **Base:** `main`. **CI:** all six green.
- **What it does.** Adds a Playwright/Chromium harness under `tools/a11y_browser/` running
  the same axe rule sets as the jsdom gate, where nothing is undecidable, plus WCAG 2.2
  SC 1.4.10 Reflow at 320x256. It found a real serious defect: the wide-table scroll
  containers were not keyboard reachable (`scrollable-region-focusable`, WCAG 2.1.1),
  invisible to jsdom because it does no layout. Each is now a named `<section
  tabindex="0">`.
- **Correctness: strongest PR in the queue.** The specific hazards worth checking are all
  closed:
  - `pagesUnderTest()` **throws** on a missing directory and on a directory with no HTML,
    rather than returning `[]` and letting "nothing checked" read as "nothing wrong".
  - `tests/test_a11y_browser_gate.py` runs both specs against an empty directory and a
    directory that was never built, and asserts non-zero exit. This is the exact
    "rglob over a renamed directory returns empty" failure mode, tested.
  - It carries a positive control, so a harness that fails everything cannot masquerade
    as a gate.
  - Each failure mode has its own case: 900px block, unbreakable string in a correctly
    sized box, unfocusable scroller, sub-threshold contrast, 8px target.
  - It refuses to skip on CI: a missing toolchain with `CI` set raises rather than
    skipping, because a skipped gate test reads as a passing one.
  - The reflow spec exempts content *inside* a scroll container but not the container
    itself, which is the correct reading of SC 1.4.10.
- **Wiring verified.** `browser-sync` and `a11y-browser` are in both `pages:` and
  `verify:` in the `Makefile`, so the gate actually runs rather than being a file nobody
  invokes. The second dependency tree gets its own `npm audit` via `browser-audit`.
- **Nit, not a defect.** `axe.spec.ts` and `playwright.config.ts` say four rules are
  undecided in jsdom; the README says three. Both are right: `UNDECIDABLE_HERE` declares
  four, but `target-size` never fires on these pages, which `main`'s README already
  recorded. Loose wording, pre-existing, no action needed.
- **Overlaps:** conflicts with #27 and #28. Clean against #20, #21, #22.
- **Recommendation: `merge`.** Merge first overall.

### #30 The manifest entry this table said did not exist
- **Base:** `feat/a11y-in-a-real-browser` (#29). **CI:** four green, no CodeQL.
- **What it does.** The README's standards table opened by saying the applicability
  manifest had no entry for this repository, and the only test reading that sentence
  asserted it was *still present*, with the instruction "Remove this test on the day the
  manifest entry exists, not before". The entry had existed for twelve days. Replaces the
  caveat with a dated transcription and replaces the test that pinned the false claim.
- **Correctness: verified against the actual registry, not taken on trust.** The registry
  is at `/Users/chelsea/portfolio/STANDARDS/applicability.yml` and I read the `perimeter`
  entry directly. Every transcribed fact matches:
  - archetype `civic-data-tool` OK
  - publication `cleared`, public since 2026-08-08 OK
  - tier `B+C` OK
  - flags `html: true, hosted: true, dockerfile: false, llm: false, bilingual: false` OK
  - fourteen apply, AI Evaluation N/A OK (counted: CQ, SEC, CICD, OBS, A11Y, I18N, QM,
    DOC, REL, RTF, PERF, IR, DG, ADM)
  - the N/A rationale is transcribed **verbatim**: "deterministic coverage counting over
    published CAL FIRE/FRAP datasets; no LLM/model component"
  - "added 2026-08-15" OK: `git log -S` in the STANDARDS repo puts the entry in commit
    `36747be`, dated 2026-08-15.
  The Observability row correctly moves from Tier C to Tier B+C to match.
- **The self-critique in it is the valuable part.** "A test that can only fail when
  somebody edits the sentence it is pinning is not a check on the sentence" is a precise
  statement of this portfolio's dominant defect, written about itself.
- **Honest about its limits.** It states the registry lives elsewhere and that nothing in
  CI can check the transcription against the source, and has a test asserting that
  sentence is present, so the transcription cannot start reading like a live check.
- **Overlaps:** none in source; different README regions from stack B.
- **Recommendation: `merge after retargeting to main`** once #29 is in.

### #31 A retrieval that goes stale fails the build
- **Base:** `docs/the-manifest-entry-exists` (#30). **CI:** four green, no CodeQL.
- **What it does.** Adds a data card per source under `docs/data/` with the seven rows
  DG-01 requires, adds `tier`, `refresh_cadence` and `staleness_sla_days` to `Source`,
  publishes them in the artifacts, and gates on retrieval age (DG-04).
- **Correctness: the gate logic is sound.** The boundary is tested on both sides:
  `test_the_staleness_gate_fires_the_day_after_the_sla_and_not_the_day_of` asserts clean
  on the SLA day and stale the day after, which is a real off-by-one check rather than a
  restatement. `stale_sources` is a pure function of a date, run against `date(2099,1,1)`
  where it must name every source. The clock is deliberately kept out of the artifacts so
  the byte-identical-output promise survives; only the test has a clock.
- **THE THING TO DECIDE BEFORE MERGING.** `test_no_published_retrieval_is_older_than_the_sla_its_card_states`
  calls `date.today()`. Computed from the pinned 2026-08-07 retrieval:

  | Source | SLA | Last good day | Build goes red |
  |---|---|---|---|
  | DINS | 180 days | 2027-02-03 | **2027-02-04** |
  | FRAP | 400 days | 2027-09-11 | 2027-09-12 |

  From 2027-02-04 this fails `make verify` and every CI job on every branch and every
  PR, including Dependabot's, with no code change. Clearing it means re-acquiring a
  163 MB file from CAL FIRE and rebuilding `site/`, which is real work. The PR argues
  firing is the gate working, and for DG-04 that is correct. But on a public portfolio
  repository the practical outcome of an unattended fire is a permanently red CI badge.
  Worth an explicit decision now: keep 180 days, lengthen it with a reason recorded in
  the card, or accept the date and calendar the re-acquisition.
- **Latent risk checked and clear.** `test_the_card_restates_the_reviewed_record_without_drifting_from_it`
  does `assert value in text` over `source.version`. A `None` version would raise
  `TypeError` rather than fail cleanly. Both sources carry string versions
  (`firep25_1`, `POSTFIRE_MASTER_DATA_SHARE`), so this is safe today; it would bite a
  future source with no version string.
- **Overlaps:** touches only the Data Governance README row. Clean against stack B source.
- **Recommendation: `merge after retargeting to main`**, once #30 is in and the SLA
  question above has an answer.

### #20 Bump astral-sh/setup-uv 9.0.0 -> 10.0.1
- **Base:** `main`. **CI:** all six green. Three call sites in `ci.yml`, one in
  `pages.yml`, all SHA-pinned with the tag in a trailing comment.
- **Correctness:** clean. Merges cleanly against #29 (verified with `git merge-tree`).
- **Recommendation: `merge`.**

### #21 Bump ruff 0.16.2 -> 0.16.3
- **Base:** `main`. **CI:** all six green. `pyproject.toml` plus `uv.lock`.
- **Correctness:** clean. The Dependabot config uses `package-ecosystem: "uv"`, so the
  born-red `pip`-against-`uv.lock` misconfiguration seen elsewhere in this portfolio does
  not exist here. Merges cleanly against #31.
- **Recommendation: `merge`.**

### #22 Bump actions/configure-pages 5.0.0 -> 6.0.0
- **Base:** `main`. **CI:** all six green. One line in `pages.yml`, SHA-pinned.
- **Correctness:** clean. Does not touch the same lines as #20 despite both editing
  `pages.yml` (line 79 versus line 50). Merges cleanly against #29.
- **Recommendation: `merge`.**

## Cross-stack collisions

Measured with `git merge-tree`, which computes a merge without touching HEAD, the index
or the working tree. All conflicts are between stack A and stack B; the Dependabot PRs
are clean against everything.

| Merge | Result |
|---|---|
| #29 x #26 | `CHANGELOG.md` |
| #29 x #27 | `CHANGELOG.md`, `site/dins.html` |
| #29 x #28 | `CHANGELOG.md`, `site/dins.html`, `src/perimeter/render.py` |
| #31 x #26 | `CHANGELOG.md` |
| #31 x #27 | `CHANGELOG.md`, `site/dins.html` |
| #20/#21/#22 x either stack | clean |

All three are mechanical, not semantic. The `render.py` conflict is a single line: #29
closes the by-access table with `</table></section>` where #28 keeps `</table></div>` and
appends `{access_note}`. The resolution is both:

```
</tr></thead><tbody>{access_rows}</tbody></table></section>
{access_note}
```

`CHANGELOG.md` is two entries prepended to the same spot. `site/dins.html` is generated
output mirroring the `render.py` conflict.

**Rebuild `site/` after resolving.** `site/` is generated from CAL FIRE's acquired files,
which are gitignored and never in CI, so nothing in CI can prove the committed bytes are
what the merged renderer would produce. `tests/test_published_site.py` says this about
itself: "it does not prove `site/` is what the current pipeline would produce ... Only a
machine holding those files can settle that, by running `make site` and finding no diff."
A hand-resolved merge of two independently generated HTML files is exactly the case that
sentence warns about. Run `make site` on the machine holding `data/raw/` and confirm the
diff is empty before pushing the merge.

## Safe order of operations

The rule: **retarget the dependent PR to `main` before merging and deleting its base.**
Never merge a base with `--delete-branch` while a PR still points at it.

1. **Merge the three Dependabot PRs first**, in any order: **#20**, **#21**, **#22**.
   No dependents, nothing to retarget, clean against both stacks. This shrinks the queue
   from nine to six.
2. **Stack A, top down.**
   1. Retarget **#30** to `main`.
   2. Merge **#29**. Deleting its branch is now safe.
   3. Retarget **#31** to `main`.
   4. Merge **#30**. Deleting its branch is now safe.
   5. Answer the staleness-SLA question, then merge **#31**.
3. **Stack B, top down**, resolving the collisions as they arrive.
   1. Retarget **#27** to `main`.
   2. Merge **#26**. Resolve the `CHANGELOG.md` conflict.
   3. Retarget **#28** to `main`.
   4. Merge **#27**. Resolve `CHANGELOG.md` and `site/dins.html`.
   5. Merge **#28**. Resolve `CHANGELOG.md`, `site/dins.html` and `render.py`.
4. **Rebuild and verify.** On the machine holding `data/raw/`, run `make site` and confirm
   an empty diff, then `make verify`.

Stack A goes before stack B on purpose. #29 is the PR that restructures the page markup,
and taking it first means each stack B merge resolves against settled markup instead of
resolving the same `div`-to-`section` change three times.

Retargeting each dependent to `main` before merging its base also means CodeQL runs on
#27, #28, #30 and #31 for the first time. Let those runs finish before merging them.

## What was verified, and what was taken on trust

**Verified directly:**
- Every PR's base branch, mergeability and per-check conclusion, from `gh`.
- That no red CI exists, so no starved-versus-failed distinction was needed.
- That `codeql.yml` triggers only on PRs into `main`, explaining the four-check PRs.
- #26 gate 1 fails pre-change, by matching each grep phrase against the shipped note.
- #26's two quotations are on the field's own line in `docs/MARKERS.md` (`:181`, `:182`).
- #27's arithmetic, recomputed from both artifacts: 102,091 - 12,148 = 89,943, sum
  conserved at 132,522, and 67.9%.
- #27's gate is non-vacuous: none of the six numeric fields with recorded zeros appeared
  in the pre-change `docs/MARKERS.md`.
- #28's partition, by reading `is_assessed` and `is_inaccessible` and confirming the
  complement equals `AccessSplit`'s existing damage-not-present pair.
- #28 exercises both branches of the new `render.py` conditional.
- #29's harness throws rather than passing on an empty or missing directory, and its
  meta-gate tests both cases; and that `browser-sync`/`a11y-browser` are wired into
  `verify:` and `pages:`.
- #30's every factual claim, against `/Users/chelsea/portfolio/STANDARDS/applicability.yml`,
  including the verbatim AI Evaluation rationale and the 2026-08-15 entry date from the
  STANDARDS repo's own git history.
- #31's staleness fire dates, computed from the pinned retrieval date and each SLA.
- The full conflict matrix and the exact `render.py` conflict hunk, via `git merge-tree`.
- That Dependabot is configured with `package-ecosystem: "uv"`, not `pip`.
- That no committed page or doc on `main` carries an em dash or en dash.

**Taken on trust:**
- That the test suites pass as CI reports. No suite was executed; the machine is under
  heavy shared load and every PR is already green. All correctness findings above come
  from reading diffs and source, not from running tests.
- The measured figures in the PR bodies that describe *pre-change* failure output, for
  example #26's quoted 1-failed-13-passed run. The underlying claim was re-derived
  independently in each case, but the transcripts themselves were not reproduced.
- That the axe and Playwright runs behave in CI as the specs intend. The specs were read
  and their failure modes reasoned about; no browser was launched here.
- That `docs/MARKERS.md`'s transcriptions of CAL FIRE and FRAP documents are faithful to
  those documents. Checking that needs the source PDFs and is outside this triage.

## PRs I believe are actively wrong

**None.** No PR in this queue should be rejected on correctness.

That is not a rubber stamp. The specific defect this portfolio suffers from, a test that
passes in both states, was looked for in every PR that adds one, and in each case the
author had already found and closed it: #26 gives its two both-state gates their own
reject-this-input tests, #28 injects a synthetic population to reach an otherwise
unreachable branch, #29 tests the empty and missing directory cases directly, and #30
exists precisely because a test pinning a sentence had gone false without failing.

The two things to decide rather than merge blind are **#31's 2027-02-04 wall-clock
deadline** and the **`site/` rebuild** after the cross-stack merge. Neither is a defect in
a PR; both are consequences that only appear once these land together.
