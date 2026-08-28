# A field note is published output and is gated like a number

- Status: Accepted
- Date: 2026-08-27
- Deciders: Chelsea Kelly-Reif

## Context

`FieldSpec.note` reads like a comment and is not one. `artifacts.py` copies it
verbatim into `site/data/*-coverage.json` beside the counts it describes, so it
is the only prose a machine reader of these artifacts is handed with the
numbers.

Issue #23 found one that was false. `WHEREFIRESTARTEDONSTRUCTURE` told a reader
its blank rate was "read against the affected subset rather than the whole
file". `field_coverage` derives a field's total from the records it is handed
and `dins_report` hands it all 132,522, so the sentence described a measurement
that has never existed, and it shipped in the same JSON object as the 2.8%
it was describing. `WHATDIDFIRESTARTFROM` carried a weaker version of the same
claim, "Collected only where the structure was affected", with nothing in this
repository recording where that came from.

Nothing mechanical noticed for either, because nothing mechanical read the
notes. Every other published fact here has something reading it: the provenance
block has `tests/test_provenance.py`, the pin has
`tests/test_standards_conformance.py`, a number in page prose has
`tests/test_pages_html.py`. The notes had nothing.

PR #25 then showed the second half of the problem. It correctly removed the
false clause and replaced it with "Collected only where the structure was
affected per CAL FIRE's dictionary", for both fields. `docs/MARKERS.md` records
a collection restriction for one of the two, quoting D4 as "Only recorded for
Affected 1-9% damage category": a named damage band, not "affected" generally.
`WHATDIDFIRESTARTFROM` has no such record at all. The patch applied cleanly, the
basis stayed `inferred`, `schema.py` and the artifact stayed in sync, and 549
tests passed, so the repository's entire apparatus had no opinion about a
sentence that put words in CAL FIRE's mouth.

## Decision

A field note is published output. Four gates hold it to that, in
`tests/test_field_notes.py`, each written as a function that is separately run
against input it must reject:

1. **A note may not claim a population narrower than the file.** No measurement
   here narrows a denominator per field, so a note saying one does is false
   whatever else it says. This gate is a list of phrasings, and is named as one:
   it reads prose and can be evaded by wording it does not carry.
2. **Every field's total is every record it was handed.** Checked in the code
   over the fixtures and in the published artifacts, top level and per incident.
   This is the half of gate 1 that holds whatever the wording, because it reads
   the counts rather than the sentence.
3. **A quotation in a note must be transcribed in the audit, on that field's own
   line.** Double quotes in a note mean source text; single quotes mean a value.
   `docs/MARKERS.md` is where a transcription is tied to the document it came
   from and to a URL a reader can re-read, so a note may quote only what the
   audit already records for that field. This is the gate that rejects PR #25:
   the restriction it borrowed is recorded on one field's line and not the
   other's.
4. **The note in the registry and the note in the published artifact are one
   sentence.** Editing `schema.py` without rebuilding `site/` leaves the reader
   with the old claim, which is how a corrected note fails to reach anybody.

Where a published document restricts collection, the note says so as the
publisher's restriction and quotes it, and says separately what this project
counted. Those are two different facts and the note now keeps them apart.

## Consequences

Writing a note costs more. A sentence about what CAL FIRE collects now needs the
audit line to exist first, which means reading D3 or D4 and transcribing it
before the note can mention it. That is the same slowness ADR-0003 imposed on
adding a marker, for the same reason.

Gate 1 is the weakest of the four and should not be trusted alone. It caught the
sentence that was there; a differently worded false claim would pass it. Gate 2
is why that is survivable: a note asserting a narrower denominator is
contradicted by the totals published beside it, and those are checked.

What none of this decides is whether a note's *reasoning* is sound. A note can
quote the right document, count over the right population, match its artifact,
and still draw a conclusion a reader would argue with. `docs/MARKERS.md` and its
confidence column remain the place that argument happens.
