"""A field note is published output, so it is held to what the pipeline actually did.

Every ``FieldSpec.note`` in :mod:`perimeter.schema` is copied verbatim into
``site/data/*-coverage.json`` beside the counts it describes, which makes it the one
piece of prose a machine reader of these artifacts gets handed with the numbers. Issue
#23 found one asserting a methodology the code does not implement:
``WHEREFIRESTARTEDONSTRUCTURE`` told a reader its blank rate was "read against the
affected subset rather than the whole file" while ``field_coverage`` counted every one
of the 132,522 records, and the false sentence shipped in the same JSON object as the
number it described. Nothing mechanical noticed, because nothing mechanical read the
notes at all.

Four gates, each a function that can be run against input it should reject, per ADR-0004:

1. :func:`notes_claiming_a_narrower_population` reads the prose. It is a list of
   phrasings that assert a population narrower than the file, not a semantic check, and
   it is named as one: a note can still be wrong in words this list does not carry.
   Gate 2 is the half that holds whatever the wording.
2. :func:`totals_that_are_not_the_record_count` reads the counts. Every field's total is
   every record it was handed, in the code and in the published artifacts, so a note
   claiming otherwise is contradicted by the bytes beside it.
3. :func:`untranscribed_quotations` reads the citations. A note may transcribe a
   published document only where ``docs/MARKERS.md`` already records that transcription
   on that field's own line. This is the gate that would have stopped PR #25, which
   attributed "Collected only where the structure was affected" to CAL FIRE's dictionary
   for a field whose audit line records no such restriction.
4. :func:`notes_that_drifted_from_the_artifact` reads both. The note in ``schema.py`` and
   the note in the published artifact are the same sentence or one of them is stale.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from perimeter.coverage import field_coverage
from perimeter.dins import load_inspections
from perimeter.perimeters import load_perimeters
from perimeter.records import Record
from perimeter.schema import DINS_FIELDS, FRAP_FIELDS, FieldSpec

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
MARKERS_DOC = (ROOT / "docs" / "MARKERS.md").read_text(encoding="utf-8")
ALL_FIELDS: tuple[FieldSpec, ...] = (*FRAP_FIELDS, *DINS_FIELDS)
ARTIFACTS = (
    ("perimeters-coverage.json", FRAP_FIELDS),
    ("dins-coverage.json", DINS_FIELDS),
)


def artifact(name: str) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(
        (ROOT / "site" / "data" / name).read_text(encoding="utf-8")
    )
    return payload


# --------------------------------------------------------------------------------------
# Gate 1. The prose may not claim a population the pipeline does not count over.
# --------------------------------------------------------------------------------------

NARROWED_POPULATION_CLAIMS: tuple[str, ...] = (
    "affected subset",
    "rather than the whole file",
    "read against the",
    "restricted to",
    "narrower population",
    "only the affected",
    "of the affected records",
)
"""Phrasings that assert this field was counted over less than the file.

None of them can be true. ``field_coverage`` derives a field's total from the records it
is handed and nothing hands it a filtered set, so a note saying otherwise is describing
a measurement that does not exist. Where a published document restricts *collection*,
say so as the publisher's restriction and quote it: that is a fact about the file, and
gate 3 checks the quote against the audit.
"""


def notes_claiming_a_narrower_population(
    specs: Sequence[FieldSpec],
) -> list[tuple[str, str]]:
    """Fields whose note asserts a denominator narrower than every record."""
    found: list[tuple[str, str]] = []
    for spec in specs:
        lowered = spec.note.lower()
        found.extend(
            (spec.name, claim)
            for claim in NARROWED_POPULATION_CLAIMS
            if claim in lowered
        )
    return found


def test_no_note_claims_a_population_narrower_than_the_file() -> None:
    claimed = notes_claiming_a_narrower_population(ALL_FIELDS)
    assert claimed == [], (
        "these notes describe a denominator the pipeline does not compute; "
        f"field_coverage counts every record it is handed: {claimed}"
    )


def test_the_prose_gate_rejects_the_sentence_it_exists_to_catch() -> None:
    """The wording issue #23 found, run back through the gate."""
    was_shipped = FieldSpec(
        "WHEREFIRESTARTEDONSTRUCTURE",
        "Where fire started on structure",
        note=(
            "Collected only where the structure was affected, so its blank rate is "
            "read against the affected subset rather than the whole file."
        ),
    )
    assert notes_claiming_a_narrower_population([was_shipped]) == [
        ("WHEREFIRESTARTEDONSTRUCTURE", "affected subset"),
        ("WHEREFIRESTARTEDONSTRUCTURE", "rather than the whole file"),
        ("WHEREFIRESTARTEDONSTRUCTURE", "read against the"),
    ]


# --------------------------------------------------------------------------------------
# Gate 2. The counts say the same thing, whatever the prose says.
# --------------------------------------------------------------------------------------


def totals_that_are_not_the_record_count(
    totals: Sequence[tuple[str, int]], records: int
) -> list[tuple[str, int]]:
    """Fields whose published total is not the number of records measured."""
    return [(name, total) for name, total in totals if total != records]


def test_the_total_gate_rejects_a_field_counted_over_less_than_the_file() -> None:
    """A per-field denominator, had one ever been introduced, looks like this."""
    assert totals_that_are_not_the_record_count(
        [("DAMAGE", 132522), ("WHEREFIRESTARTEDONSTRUCTURE", 8739)], 132522
    ) == [("WHEREFIRESTARTEDONSTRUCTURE", 8739)]


@pytest.mark.parametrize(
    ("loader", "path", "specs"),
    [
        (load_perimeters, "frap_perimeters.sample.json", FRAP_FIELDS),
        (load_inspections, "dins_postfire.sample.json", DINS_FIELDS),
    ],
    ids=["perimeters", "dins"],
)
def test_every_field_is_counted_over_every_record_it_was_handed(
    loader: Any, path: str, specs: tuple[FieldSpec, ...]
) -> None:
    records: list[Record] = loader(FIXTURES / path)
    totals = [(spec.name, field_coverage(records, spec).total) for spec in specs]
    assert totals_that_are_not_the_record_count(totals, len(records)) == []


@pytest.mark.parametrize(("name", "specs"), ARTIFACTS, ids=[n for n, _ in ARTIFACTS])
def test_every_published_field_total_is_the_published_record_count(
    name: str, specs: tuple[FieldSpec, ...]
) -> None:
    payload = artifact(name)
    totals = [(field["name"], field["total"]) for field in payload["fields"]]
    assert totals_that_are_not_the_record_count(totals, payload["records"]) == []


def test_every_published_per_incident_field_is_counted_over_that_incident() -> None:
    """The per-incident blocks are counted the same way, and are checked the same way."""
    payload = artifact("dins-coverage.json")
    for incident in payload["incidents_detail"]:
        totals = [(name, sum(states)) for name, states in incident["fields"].items()]
        assert (
            totals_that_are_not_the_record_count(totals, incident["records"]) == []
        ), incident["incident_name"]


# --------------------------------------------------------------------------------------
# Gate 3. A quotation in a note is a citation, and the audit is where citations live.
# --------------------------------------------------------------------------------------

QUOTED = re.compile(r'"([^"]+)"')
"""Double quotes in a note mean transcribed source text. Values use single quotes."""


def untranscribed_quotations(
    specs: Sequence[FieldSpec], doc: str
) -> list[tuple[str, str]]:
    """Quotations in a note that the audit does not record on that field's own line.

    The audit line is where a transcription is tied to the document it came from and to
    a URL a reader can re-read. A note quoting something the audit does not carry for
    that field is an attribution nothing in this repository can check.
    """
    lines = doc.splitlines()
    found: list[tuple[str, str]] = []
    for spec in specs:
        naming = [" ".join(line.split()) for line in lines if f"`{spec.name}`" in line]
        for quote in QUOTED.findall(spec.note):
            flat = " ".join(quote.split())
            if not any(flat in line for line in naming):
                found.append((spec.name, quote))
    return found


def test_every_quotation_in_a_note_is_transcribed_in_the_audit() -> None:
    assert untranscribed_quotations(ALL_FIELDS, MARKERS_DOC) == [], (
        "a note transcribes source text that docs/MARKERS.md does not record on that "
        "field's line; either the audit is missing the evidence or the note invented it"
    )


def test_the_quotation_gate_rejects_the_attribution_pr_25_proposed() -> None:
    """The rejected patch moved a restriction onto a field the audit does not record it for.

    ``docs/MARKERS.md`` records "Only recorded for Affected 1-9% damage category" on the
    ``WHEREFIRESTARTEDONSTRUCTURE`` line and on no other. Attributing it to
    ``WHATDIDFIRESTARTFROM`` is an attribution the audit cannot support, and quoting it
    there fails here.
    """
    borrowed = FieldSpec(
        "WHATDIDFIRESTARTFROM",
        "What the fire started from",
        note='D4: "Only recorded for Affected 1-9% damage category".',
    )
    assert untranscribed_quotations([borrowed], MARKERS_DOC) == [
        ("WHATDIDFIRESTARTFROM", "Only recorded for Affected 1-9% damage category")
    ]


def test_the_quotation_gate_rejects_a_quotation_nobody_transcribed() -> None:
    invented = FieldSpec(
        "EAVES",
        "Eaves",
        note='D4: "Recorded for every structure the inspector reached".',
    )
    assert untranscribed_quotations([invented], MARKERS_DOC) == [
        ("EAVES", "Recorded for every structure the inspector reached")
    ]


# --------------------------------------------------------------------------------------
# Gate 4. The note in the registry and the note in the published artifact are one note.
# --------------------------------------------------------------------------------------


def notes_that_drifted_from_the_artifact(
    specs: Sequence[FieldSpec], payload: dict[str, Any]
) -> list[tuple[str, str, str]]:
    """Fields whose published note is not the note the registry holds today."""
    published = {field["name"]: field.get("note", "") for field in payload["fields"]}
    return [
        (spec.name, spec.note, published.get(spec.name, ""))
        for spec in specs
        if spec.name in published and published[spec.name] != spec.note
    ]


@pytest.mark.parametrize(("name", "specs"), ARTIFACTS, ids=[n for n, _ in ARTIFACTS])
def test_the_published_note_is_the_note_the_registry_holds(
    name: str, specs: tuple[FieldSpec, ...]
) -> None:
    drifted = [
        row[0] for row in notes_that_drifted_from_the_artifact(specs, artifact(name))
    ]
    assert drifted == [], (
        f"{name} publishes a note schema.py no longer holds for {drifted}; "
        "rebuild site/ from the acquired files (make site) so the reader gets the "
        "sentence the registry actually stands behind"
    )


def test_the_drift_gate_rejects_an_artifact_left_behind_by_an_edit() -> None:
    """Editing the registry without rebuilding site/ is exactly what PR #25 could not do."""
    stale = {
        "records": 1,
        "fields": [{"name": "DAMAGE", "total": 1, "note": "an older sentence"}],
    }
    spec = FieldSpec("DAMAGE", "Damage", note="the sentence held today")
    assert notes_that_drifted_from_the_artifact([spec], stale) == [
        ("DAMAGE", "the sentence held today", "an older sentence")
    ]
