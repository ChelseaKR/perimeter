# Changelog

All notable changes to perimeter are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed, the per-incident table's header and its body were two separate lists

- **A column in one and not the other shifts every later value under the wrong heading.**
  The header of the per-incident coverage table on `dins.html` was five hard-coded labels;
  the body was a separate tuple of five field names, filtered by `if name in by_name`. A
  field leaving `DINS_FIELDS` would have dropped its cell from every row and left all five
  headers standing, which does not blank a column. Every cell after the missing one moves
  left: the vent-screen share published under Eaves, correctly counted and wrongly
  labelled, on a page whose subject is not misreading a number. Nothing was wrong in the
  acquired file, and nothing is wrong on the page today; all five fields are in
  `DINS_FIELDS`, so this is a defect the code could produce rather than one it had
  produced. The header and the body now read one paired list,
  `render.INCIDENT_FIELD_COLUMNS`, and a column the report carries no coverage for is
  written as `not counted` rather than dropped, so the row keeps its width either way.
  The table this page already builds honestly, the per-decade acreage table, reads its
  header off the body for exactly this reason; this is the same discipline applied to the
  one table that had not had it.
- **Nothing could have caught it, so there is now something that can.**
  `html-validate` does not compare row widths and neither does axe, and a short row
  renders as an ordinary table. `tests/test_pages_html.py::row_width_problems` counts
  cells per row per table, `colspan` included, across all three pages, and reports a table
  with no rows rather than passing over one. Per ADR-0004 it is run against markup that
  must not pass it: a row missing a cell, a page with no table at all, and, in
  `test_the_per_incident_table_writes_a_cell_for_a_field_it_cannot_count`, a real
  `DinsReport` with a field removed from every incident. Against the previous renderer
  that last one reports rows nine cells wide under a ten-cell header; against this one it
  reports nothing.
- **`make site-check` earned its keep on its first day.** The paragraph under the table
  changed, `site/` went stale, and the target said so before the commit rather than after
  the deploy. `site/dins.html` is rebuilt; every cell in the table is byte-identical,
  which is the evidence that this change does not move a published number.

### Fixed, thirty fields published a zero for a comparison that never happened

- **A field with no published coded-value domain reported `outside_published_domain: 0`.**
  `FieldSpec.outside_domain` answers False for every cell of a field the layer publishes no
  domain for, and `field_coverage` summed that answer for every field alike, so thirty of
  the fifty-four measured fields published a zero meaning "nothing was counted" in the same
  key where `CAUSE` publishes a zero meaning "counted, none found". `FIRE_NAME`, `UNIT_ID`,
  `COUNTY` and twenty-seven others are free text; both publishers say which of their fields
  they constrain. The zero said the file and the domain agree, about a domain that does not
  exist. The four out-of-domain measures are now `null` together for such a field, the way
  `present_tenths_pct` is already `null` where there is no denominator, and zero keeps the
  narrow meaning it should always have had. See ADR-0010.
- **The fact was known one layer down and lost one layer up.**
  `tests/test_schema.py::test_free_text_fields_have_no_domain_to_be_outside_of` has always
  asserted that a free-text field has nothing to be outside of. Nothing carried that into
  the counting, and nothing tested what the count published, so the artifact contradicted
  the test in the same suite. `tests/test_measurements.py` now separates the two zeros at
  the count, `tests/test_artifacts_and_pages.py` checks both sides of the line in both
  published artifacts, and both new tests fail against the previous code.
- **Both pages say it in words rather than leaving the row silent.** A row with no note
  about the published domain read the same whether the domain held every value or did not
  exist. Every free-text row now carries "The layer publishes no coded-value domain for this
  field, so no value here is counted as outside one", and the paragraph under each field
  table names all three states a row can be in, so silence means exactly one of them.
- **The capped list of named out-of-domain values now says how many it names.**
  `outside_published_domain_values` stops at twelve so a field with a thousand spellings
  does not publish a thousand keys. Nothing said it stops. No field reaches the cap today,
  which is why nothing has been misread yet; a truncated list that does not declare itself
  reads as the whole set. `outside_published_domain_values_listed` is published beside
  `outside_published_domain_distinct`, and where they differ the list stopped.
- **`site/` was rebuilt from the acquired files, and `make site-check` is what keeps it
  honest.** `tests/test_published_site_is_current.py` compares the shape of the published
  artifacts, so the new key would have failed the build until `site/` was rebuilt; it
  compares pages only outside `<main>`, so the thirty new page notes would have passed
  unnoticed. `make site-check` builds from `data/raw/` into `build/site-current` and diffs
  it against `site/`, never writing into `site/`, and refuses outright when the acquired
  files are absent, because a check that could not run is not a check that passed. It
  cannot run in CI: those files are not in git and never will be. Verified to fail on both
  inputs it exists to catch, a drifted page and a missing source file.

### Fixed, the committed ruleset would have locked the owner out on first apply

- **`.github/rulesets/main.json` carried `"bypass_actors": []`.** No ruleset has ever
  been applied to this repository (`gh api repos/ChelseaKR/perimeter/rulesets` returned
  `[]` on 2026-08-15 and again on 2026-08-28), so nothing was broken yet; what was
  committed was a first application that would have broken it. The file now carries
  exactly the repository owner's standing bypass, `RepositoryRole` 5 with
  `bypass_mode: always`, deliberately and permanently: an agent once applied a ruleset
  with no bypass and locked the owner out of their own repository, and restoring access
  took a sweep across eighteen repositories. An empty list there is not a stricter gate,
  it is the lockout. `.github/rulesets/README.md` argued the other way, calling the empty
  list "the stricter reading" of CICD-15; that bullet is replaced with the reversal and
  the reason, the apply procedure gains a step that checks the bypass actually came
  through, and the "what is true today" section now says plainly that no ruleset is
  applied and that this file has therefore never been corrected by a live one.
  Re-measured 2026-08-29: still `[]`, still `"protected": false`, and the branch
  protection endpoint still 404s.
- **Nothing read that file, so correcting it once would not have held.** Measured before
  writing the check: no test and no module in this repository referenced `ruleset` or
  `bypass_actors` anywhere, so the value could regress to the empty list in a single edit
  with every gate still green. `tests/test_ruleset.py` makes the empty list a test
  failure. `lockout_risk` is a pure function of a parsed document, exercised against the
  five shapes that lose the bypass (empty list, absent key, wrong type, a different
  actor, and the owner downgraded to `bypass_mode: pull_request`) with a positive control
  so it is not passing by refusing everything, and `load_ruleset` fails on a missing or
  unparseable file rather than returning an empty document that the assertions would read
  as nothing wrong.
- **The apply order named two required contexts that did not exist. They exist.**
  `.github/rulesets/README.md` said "Two of the five contexts in `main.json` do not exist
  on `main` yet" and made landing them step 1. That was written 2026-08-15 and was false
  within the day: `zizmor` arrived with #16 (`839557e`) and `sast` had been in `ci.yml`
  since `ea06580`. Re-measured 2026-08-29 off the two most recent pull request head
  commits, `62c406e` (#30) and `ae0e2d6` (#31), all five contexts report. The completed
  steps are kept as numbered history rather than deleted and the rest are renumbered.
- **Still not applied.** Landing the corrected file changes nothing on the server.
  Applying the ruleset is a live repository setting and remains the owner's call.

### Added, a retrieval that goes stale now fails the build

- **A data card per source, under `docs/data/`.** DG-01 asks for one per ingest source
  with seven named rows. `PROVENANCE.md` carried five of them; the two it had never
  carried are the tier, L1 for both, and the refresh cadence with its staleness SLA.
  `tests/test_data_cards.py` enumerates the cards against the declared source list
  rather than against what is on disk, so adding a source without a card fails.
- **The staleness alarm DG-04 makes an AUTO-GATE.** Every figure on these pages is a
  count of a file downloaded on one day. The pages say the date, which is honest and is
  not the same as noticing. `tests/test_data_cards.py` now fails when a retrieval is
  older than the SLA its card states: 400 days for FRAP, one annual release cycle plus
  about five weeks, and 180 days for DINS, about one fire season, since that layer
  carries no version and is appended to as inspections complete. On the retrieval on
  record it fires 2027-02-03 for DINS and 2027-09-11 for FRAP. Firing is it working.
- **The clock is in the gate and not in the artifacts.** A page computing its own
  staleness would read the wall clock at build time and two builds a day apart would
  differ, which is in direct conflict with the byte-identical output `make determinism`
  exists to protect. The artifacts publish `retrieved` and `staleness_sla_days` and
  compute nothing; a consumer can do the subtraction against its own clock and get the
  same answer. See ADR-0009.
- **The SLA is this project's declaration, and every card says so.** Neither CAL FIRE
  nor FRAP promises a publication schedule and neither is asked to.

### Fixed, a caveat that was true when written, false a week later, and pinned by a test

- **The Standards Conformance table said the applicability manifest had no entry for
  this repository. It has had one since 2026-08-15.** The entry records the archetype as
  `civic-data-tool`, publication as cleared, the tier as `B+C`, and fourteen of the
  fifteen standards as applying with AI Evaluation N/A. The table now transcribes that,
  with the date it was read, and says plainly that the registry lives in another
  repository so nothing in CI can check the transcription against its source.
- **The test guarding that sentence could only ever pass.** It read
  `assert "applicability manifest has no entry" in section` and carried the instruction
  "Remove this test on the day the manifest entry exists, not before". It was green for
  twelve days over a claim that had become false, because the only thing reading the
  sentence was a test asserting the sentence was still there. It is replaced by tests
  that refuse the false claim, hold the transcription's shape and date, and check the
  one part that is mechanically checkable from inside this repository: that the table
  marks exactly the one standard the registry marks N/A.
- **Observability moves from Tier C to Tier B+C**, which is what the registry records and
  what OBS section 0 asks a repository with two surfaces to state. The B half is a real
  gap and is recorded as one: section 8 wants a Core Web Vitals RUM beacon, which means
  shipping a script that reports readers of a civic-data page back to somebody, and
  these pages ship no script and this project takes no telemetry. That refusal is a
  position rather than an oversight and the standard has no N/A for it. The
  Lighthouse-CI lab gate, which needs no beacon, is also not met and is the half that
  could be built.

### Fixed, the three pages could not say which of them a search result was for

- **One meta description was shared by all three pages, and none of them had a canonical.**
  `render.py` hardcoded a single sentence, "Coverage and completeness counts over
  California's public wildfire datasets. Unofficial.", into the head of the index, the
  perimeters page and the DINS page alike, so a search result for one was
  indistinguishable from a search result for another and none said what its own page
  counts. `page()` now takes a `description` per page, and each restates what that page
  already says of itself in its own standfirst.

  The descriptions state **no count**. The committed `site/` is built from `data/raw/`
  and the test build is built from the fixtures, so a figure hardcoded in `render.py`
  would be true of one and false of the other; CONTRIBUTING's rule is that a number is
  counted or it is not published, and these counts belong to CAL FIRE's files, which
  change underneath us.

- **A canonical URL and Open Graph tags on every page.** There were none. These pages are
  one of six project sites on the shared `chelseakr.github.io` origin, served from paths
  rather than domains of their own, so the canonical a single-domain habit produces (`/`)
  is not this site's root but a different address that 404s, and all six would claim it.
  `SITE_URL` and `CANONICAL_PATH` are keyed by `active`, the value each page already uses
  to mark its own nav entry, so a canonical and the highlighted tab cannot disagree about
  which page this is. No `og:image`: this repository ships no image, and `twitter:card` is
  `summary`, which promises none.

- **The page parser in `tests/test_pages_html.py` could not see any of this.** It recorded
  `name=` metas only, so every `property="og:..."` tag was invisible to it, and
  `<link rel="canonical">` is not a meta tag at all. It now records both, and the existing
  title-and-description checks were extended rather than joined by a parallel SEO suite.
  `tests/test_published_site.py` gains the same assertion over the committed bytes, beside
  the rooted-link check that holds the same subpath property for `href`.

  Observed failing four ways: the canonical line deleted; `SITE_URL` set to the bare
  origin; `CANONICAL_PATH` collapsed so all three pages share one canonical; and the
  original defect restored, one description for all three pages. A fifth, hand-editing the
  committed `site/index.html` canonical to the shared origin, fails the published-bytes
  check. `make site` reproduces `site/` from `data/raw/` with no change outside the head.

### Documented, the pages have been served since 2026-08-08 and the README never said so

- **The README named the two measurement pages only as build outputs.** `site/perimeters.html`
  and `site/dins.html` appear in the prose as paths, and nowhere in the file was there a URL
  of any kind. `.github/workflows/pages.yml` landed in #7 on 2026-08-08 and has deployed
  `site/` from `main` 16 times since; `https://chelseakr.github.io/perimeter/` answers 200.
  The very next merge, #8, added the `**Status:**` line at the top of the README and still
  described the pages as files. So a reader was told the project is Beta and told where the
  HTML is written on their own disk, and was not told the measurements were already readable
  without cloning anything or acquiring CAL FIRE's files.
- **No figure is added.** The counts on those pages belong to CAL FIRE and FRAP and move when
  the retrieval is refreshed, and CONTRIBUTING's rule is that a number is counted or it is not
  published. This entry adds three links and one clause about what publishes them.

### Added, the WCAG gate now runs in an engine that does layout, and it found something

- **The scroll containers holding the wide tables were not keyboard reachable.** Every
  wide table sits in a container with `overflow-x: auto`, which is the conforming answer
  to SC 1.4.10 Reflow, and a container that scrolls and cannot be focused is a SC 2.1.1
  Keyboard failure: it scrolls for a pointer and not for a keyboard, so a sighted
  keyboard user cannot read the columns past the right edge. axe rates it serious. Each
  is now a `<section>` with `tabindex="0"`, named from the table's own caption. This was
  invisible to the existing gate and to any amount of care in the markup, because
  whether a container scrolls is a fact about layout and jsdom does none.
- **`tools/a11y_browser` runs the same axe rule sets in Chromium, and declares nothing
  undecidable.** In jsdom four rules land in `incomplete` and are declared in
  `tools/a11y.mjs` with a reason. A real engine decides all four, so the browser run has
  no exceptions list: a violation fails it and so does an undecided rule.
- **WCAG 2.2 SC 1.4.10 Reflow is measured rather than eyeballed.** 320 by 256, which is
  1280 by 1024 at 400% zoom. The document must not scroll horizontally and no element may
  spill past the viewport, counting both a box that is too wide and a box that fits
  around content that does not. Content inside a scroll container is exempt, because that
  is the conforming pattern rather than the failure. Ported from `ledger`, which runs the
  same spec over a served app; here the pages are static files and are read as `file://`
  URLs, so nothing is served and no port is opened.
- **SC 2.5.8 Target size is decided too**, which closes the one rule `tools/a11y.mjs`
  declared undecidable and covered nowhere.
- **`tests/test_a11y_browser_gate.py` is the failure evidence.** Eleven cases: a page
  that scrolls sideways at 320px, text spilling out of a correctly sized block, an
  unfocusable scroll container, text below the contrast threshold, an 8px pointer target,
  an empty directory, a missing directory, and a conformant page that must pass both
  specs.
- **Nothing is suppressed anywhere after this, so there is no `waivers.yml`.** Reported
  as #14, which asked for one covering whatever remained; nothing does. `README.md`'s
  "what still needs a person" list loses reflow and target size and keeps print, focus
  appearance, a screen reader, and looking at the layout. See ADR-0008.

### Fixed, an access table whose denominators could quietly hold fewer records than the file

- **The two populations in the assessed-against-inaccessible table are counted from the
  damage field, and a record whose damage field says nothing was in neither.** Both
  denominators were built from the records that answer, so a record that answers neither
  question left the table without appearing anywhere in it. Measured against the
  pre-change code over four records, one assessed, one inaccessible, one with a blank
  damage field and one holding a marker: the denominators summed to 2. Nothing published
  said which two records were missing or that any were.
- **No record in the acquired file is in that state, which is why this was invisible.**
  `access_split` has always counted `damage_not_recorded` and `damage_explicit_unknown`,
  and both are 0 in the 2026-08-07 retrieval, so every denominator happened to be
  complete. The table could not have said so, and would not have said otherwise.
- **`AccessFieldCoverage` now counts three populations that partition the records by
  construction**, and publishes `undetermined_present`, `undetermined_total` and
  `undetermined_tenths_pct` per field. The page states what the two columns are counted
  over and what is in neither, in both cases, with the counts coming from the pipeline.
  See ADR-0007.

### Fixed, 12,148 structures recorded as built in year 0

- **`YEARBUILT` counted the literal `0` as a recorded construction year.** 12,148 of the
  132,522 DINS records hold it, 9.2% of the file, and every one was inside the field's
  77.0% recorded share. No structure standing in a California wildfire was built in year
  0. `0` is now a declared unknown marker on `Basis.INFERRED`, and the field publishes
  89,943 recorded values (67.9%) with 12,148 recorded-as-unknown. The 30,431 empty cells
  are unchanged. Reported as #24.
- **The evidence is in `docs/MARKERS.md` section 7, not in the commit message.** The
  zeros are in 186 incidents, 45 counties and eight fire years; 55 incident groups hold
  nothing else; 11,779 of the 12,148 carry an APN, so the parcel join found a parcel and
  the parcel had no year; and 45.5% of them also carry an assessed improved value of `0`
  against 0.4% of the records holding a real year.
- **The other five numeric fields with recorded zeros are written up too, including the
  two that were considered and left alone.** `NOOUTBUILDINGSDAMAGED`,
  `NOOUTBUILDINGSNOTDAMAGED` and `NOOFCARSONPROPERTY` are inspector counts where a zero
  is the measurement. `NUMBEROFUNITPERSTRUCTURE` (58,411 zeros) and
  `ASSESSEDIMPROVEDVALUE` (6,613) each have a reading in which the zero is real, so
  neither is declared and both carry the numbers a later reader would need to decide
  otherwise.
- **The audit gate was green over a set that excluded the field that needed reviewing.**
  `docs/MARKERS.md` covers fields that declare a vocabulary, and a numeric field
  deciding its zeros are values declares nothing, so it was outside the audit by
  construction. `tests/test_schema.py` now fails when a numeric field publishes recorded
  zeros the audit does not cover. See ADR-0006.
- **Twenty-eight of the fifty-four measured fields now declare a vocabulary**, twelve
  published and sixteen inferred. `README.md`, `docs/MARKERS.md`, `schema.py` and the
  published pages all say so.

### Fixed, a field note that described a measurement nobody made

- **`WHEREFIRESTARTEDONSTRUCTURE` told a reader its blank rate was "read against the
  affected subset rather than the whole file", and no such subset exists anywhere in
  this pipeline.** `field_coverage` derives a field's total from the records it is
  handed and `dins_report` hands it all 132,522, so the published `total` for that
  field is the whole file and always was. The false sentence shipped inside the same
  JSON object as the 2.8% it purported to describe. The note now quotes what D4
  actually says, "Only recorded for Affected 1-9% damage category", names it as CAL
  FIRE's restriction on collection rather than this project's on counting, and says
  plainly that the counts are over every record. Reported as #23.
- **`WHATDIDFIRESTARTFROM` carried the same claim in shorter form, with nothing behind
  it.** `docs/MARKERS.md` gives that field's source as D3 and D4 and records only that
  D4 adds "May not be reliably determined". The note now says that, and says the counts
  are over every record. It does not borrow the other field's restriction: D4's
  "Affected 1-9%" is a named damage band recorded for one field and not the other, and
  writing it as "where the structure was affected" would widen it to four damage bands
  under CAL FIRE's name.
- **Nothing in this repository read a field note until now.** Four gates in
  `tests/test_field_notes.py`, each also run against input it must reject: a note may
  not claim a population narrower than the file; every field's total is every record it
  was handed, in the code and in the published artifacts and per incident; a quotation
  in a note must be transcribed in `docs/MARKERS.md` on that field's own line; and the
  note in `schema.py` and the note in the published artifact are one sentence. See
  ADR-0005.

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
