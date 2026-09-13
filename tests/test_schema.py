"""Classification and the two fail-closed refusals."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from perimeter.cells import Cell, CellState, SentinelDriftError
from perimeter.coverage import FieldCoverage, field_coverage, zero_review
from perimeter.records import Record
from perimeter.schema import (
    DINS_FIELDS,
    DINS_FIELDS_BY_NAME,
    FRAP_FIELDS,
    FRAP_FIELDS_BY_NAME,
    Basis,
    FieldSpec,
    SchemaDriftError,
    ZeroReading,
    require_columns,
)

PLAIN = FieldSpec("PLAIN", "Plain")
ALL_FIELDS = (*FRAP_FIELDS, *DINS_FIELDS)


@pytest.mark.parametrize("raw", [None, "", "   ", "\t"])
def test_nothing_in_the_cell_is_not_recorded(raw: str | None) -> None:
    assert PLAIN.classify(raw, where="row").state is CellState.NOT_RECORDED


def test_an_ordinary_value_is_present() -> None:
    cell = PLAIN.classify("  Cedar  ", where="row")
    assert cell.state is CellState.PRESENT
    assert cell.value() == "Cedar"


def test_a_published_code_for_unknown_is_explicit_not_blank() -> None:
    cause = FRAP_FIELDS_BY_NAME["CAUSE"]
    cell = cause.classify(14, where="row")
    assert cell.state is CellState.EXPLICIT_UNKNOWN
    assert cell.marker == "14"


def test_an_ordinary_code_is_present() -> None:
    cause = FRAP_FIELDS_BY_NAME["CAUSE"]
    assert cause.classify(1, where="row").value() == "1"


def test_a_reviewed_text_marker_folds_its_spelling_variants() -> None:
    city = DINS_FIELDS_BY_NAME["CITY"]
    for spelling in ("NA", "na", " NA ", "N/A", "N/a"):
        cell = city.classify(spelling, where="row")
        assert cell.state is CellState.EXPLICIT_UNKNOWN, spelling
    assert city.classify("NA", where="row").marker == "na"
    assert city.classify("N/A", where="row").marker == "n/a"


def test_a_published_finding_of_absence_is_a_value() -> None:
    """No Damage, No Eaves and Not Applicable are observations, not missing data."""
    assert DINS_FIELDS_BY_NAME["DAMAGE"].classify("No Damage", where="r").is_present
    assert DINS_FIELDS_BY_NAME["EAVES"].classify("No Eaves", where="r").is_present
    assert (
        DINS_FIELDS_BY_NAME["PROPANETANKDISTANCE"].classify("N/A", where="r").is_present
    )


# --------------------------------------------------------------------------------------
# A field measured as a number, holding something that is not one. Issue #51.
# --------------------------------------------------------------------------------------

NUMERIC_FIELDS = tuple(spec for spec in ALL_FIELDS if spec.numeric)


def test_the_project_measures_nine_fields_as_numbers() -> None:
    """Pins the population the refusal below covers, so a tenth cannot arrive unnoticed."""
    assert sorted(spec.name for spec in NUMERIC_FIELDS) == [
        "ASSESSEDIMPROVEDVALUE",
        "GIS_ACRES",
        "LATITUDE",
        "LONGITUDE",
        "NOOFCARSONPROPERTY",
        "NOOUTBUILDINGSDAMAGED",
        "NOOUTBUILDINGSNOTDAMAGED",
        "NUMBEROFUNITPERSTRUCTURE",
        "YEARBUILT",
    ]


@pytest.mark.parametrize("spec", NUMERIC_FIELDS, ids=lambda s: s.name)
@pytest.mark.parametrize("text", ["1,250,000", "two", "38.5N", "$4,000", "12 acres"])
def test_a_measured_as_a_number_field_refuses_a_value_that_is_not_one(
    spec: FieldSpec, text: str
) -> None:
    """All nine, not the one that happened to be parsed downstream.

    Before this, ``GIS_ACRES`` raised here because ``perimeters.acres_of`` parses it and
    the other eight did not, because nothing parses them. A reformatted column was
    published as a full set of recorded measurements on eight fields out of nine.
    """
    with pytest.raises(SchemaDriftError, match="is not a number") as caught:
        spec.classify(text, where="FRAP[OBJECTID=1]")
    assert repr(text) in str(caught.value)
    assert spec.name in str(caught.value)


@pytest.mark.parametrize("spec", NUMERIC_FIELDS, ids=lambda s: s.name)
@pytest.mark.parametrize("text", ["0", "0.0", "-1", "1250000", "38.5", "6613"])
def test_a_number_in_a_numeric_field_is_still_an_ordinary_recorded_value(
    spec: FieldSpec, text: str
) -> None:
    """The refusal must not be a refusal of the values these fields are full of."""
    cell = spec.classify(text, where="r")
    if cell.state is CellState.EXPLICIT_UNKNOWN:
        assert spec.name == "YEARBUILT" and text == "0"
        return
    assert cell.state is CellState.PRESENT
    assert cell.value() == text


def test_a_field_not_measured_as_a_number_is_untouched_by_the_check() -> None:
    """`CITY` holds text. Nothing here should start reading it as a measurement."""
    assert DINS_FIELDS_BY_NAME["CITY"].classify("Paradise", where="r").is_present
    assert FRAP_FIELDS_BY_NAME["FIRE_NAME"].classify("Camp", where="r").is_present


def test_a_blank_or_marker_cell_in_a_numeric_field_is_not_asked_to_be_a_number() -> (
    None
):
    """The refusal is about recorded values, and a blank is not one.

    ``YEARBUILT``'s ``0`` is the case that matters: it is a declared marker, so it is
    classified before this check and stays explicit-unknown rather than being read as
    the number zero.
    """
    year = DINS_FIELDS_BY_NAME["YEARBUILT"]
    assert year.classify(None, where="r").state is CellState.NOT_RECORDED
    assert year.classify("   ", where="r").state is CellState.NOT_RECORDED
    assert year.classify("0", where="r").state is CellState.EXPLICIT_UNKNOWN


def test_the_same_word_is_read_differently_in_different_fields() -> None:
    """None is a published street-type finding, and a marker in a parcel APN."""
    assert DINS_FIELDS_BY_NAME["STREETTYPE"].classify("None", where="r").is_present
    apn = DINS_FIELDS_BY_NAME["APN"].classify("None", where="r")
    assert apn.state is CellState.EXPLICIT_UNKNOWN


def test_both_not_applicable_spellings_are_the_published_finding() -> None:
    """NA is the published code. N/A is the same finding under the pre-2020 spelling.

    See docs/MARKERS.md: the two spellings never share an incident, they fall on
    opposite sides of the 2020 incidents, and both sit beside a propane Not Applicable
    at the same rate. Counting N/A as missing data would publish 6,544 inspector
    findings as undetermined cells.
    """
    spec = DINS_FIELDS_BY_NAME["UTILITYMISCSTRUCTUREDISTANCE"]
    assert spec.classify("NA", where="r").is_present
    assert spec.classify("N/A", where="r").is_present
    assert not spec.unknown_markers


def test_the_undocumented_spelling_is_still_reported_as_outside_the_domain() -> None:
    """Present, and outside the domain published today. Both facts reach the reader."""
    spec = DINS_FIELDS_BY_NAME["UTILITYMISCSTRUCTUREDISTANCE"]
    assert not spec.outside_domain(spec.classify("NA", where="r"))
    assert spec.outside_domain(spec.classify("N/A", where="r"))


def test_a_whole_placeholder_address_is_not_a_recorded_address() -> None:
    """Two DINS site addresses are placeholder strings rather than marker words."""
    spec = DINS_FIELDS_BY_NAME["SITEADDRESS"]
    for text in ("No Address Available", "NULL  NULL    UNKNOWN CA 00000"):
        assert spec.classify(text, where="r").state is CellState.EXPLICIT_UNKNOWN, text
    assert spec.classify("580 LOMMEL RD CALISTOGA CA 94515", where="r").is_present


def test_the_all_zeros_incident_number_is_not_an_identifier() -> None:
    """FRAP publishes no domain for INC_NUM; see docs/MARKERS.md for the evidence."""
    spec = FRAP_FIELDS_BY_NAME["INC_NUM"]
    assert spec.classify("00000000", where="r").state is CellState.EXPLICIT_UNKNOWN
    assert spec.classify("00012345", where="r").is_present
    assert spec.basis is Basis.INFERRED


def test_an_unreviewed_marker_stops_the_build() -> None:
    with pytest.raises(SentinelDriftError, match="missing-data marker"):
        PLAIN.classify("N/A", where="row 7")


@pytest.mark.parametrize(
    "marker", ["NULL", "<Null>", "unknown", "not determined", "--"]
)
def test_every_shape_of_unreviewed_marker_stops_the_build(marker: str) -> None:
    with pytest.raises(SentinelDriftError):
        PLAIN.classify(marker, where="row")


def test_the_refusal_names_the_field_and_the_row() -> None:
    with pytest.raises(SentinelDriftError) as caught:
        PLAIN.classify("tbd", where="SOURCE[OBJECTID=42]")
    message = str(caught.value)
    assert "SOURCE[OBJECTID=42]" in message
    assert "PLAIN" in message


def test_a_marker_reviewed_for_one_field_does_not_leak_to_another() -> None:
    """CITY may hold NA. A field that has not declared it must still refuse."""
    assert DINS_FIELDS_BY_NAME["CITY"].classify("NA", where="r").marker == "na"
    with pytest.raises(SentinelDriftError):
        DINS_FIELDS_BY_NAME["COUNTY"].classify("NA", where="r")


def test_out_of_domain_values_are_counted_rather_than_refused() -> None:
    """An ordinary value the domain does not list is a finding, not a crash."""
    roof = DINS_FIELDS_BY_NAME["ROOFCONSTRUCTION"]
    cell = roof.classify("Fire Resistant", where="r")
    assert cell.is_present
    assert roof.outside_domain(cell)
    assert not roof.outside_domain(roof.classify("Wood", where="r"))


def test_free_text_fields_have_no_domain_to_be_outside_of() -> None:
    assert not PLAIN.outside_domain(Cell.present("anything"))


def test_a_non_present_cell_is_never_reported_as_out_of_domain() -> None:
    roof = DINS_FIELDS_BY_NAME["ROOFCONSTRUCTION"]
    assert not roof.outside_domain(Cell.not_recorded())
    assert not roof.outside_domain(Cell.explicit_unknown("unknown"))


def test_a_missing_column_stops_the_build() -> None:
    with pytest.raises(SchemaDriftError, match="missing required columns"):
        require_columns({"A", "B"}, ("A", "B", "C"), source="S")


def test_require_columns_passes_when_everything_is_there() -> None:
    require_columns({"A", "B", "C"}, ("A", "B"), source="S")


@pytest.mark.parametrize("specs", [FRAP_FIELDS, DINS_FIELDS])
def test_field_names_are_unique(specs: tuple[FieldSpec, ...]) -> None:
    names = [spec.name for spec in specs]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("specs", [FRAP_FIELDS, DINS_FIELDS])
def test_a_marker_and_a_finding_are_never_the_same_string(
    specs: tuple[FieldSpec, ...],
) -> None:
    """A field cannot call one value both an absence-of-data and an observation."""
    for spec in specs:
        normalized = {value.strip().lower() for value in spec.recorded_absences}
        assert not (normalized & spec.unknown_markers), spec.name
        assert not (spec.recorded_absences & spec.unknown_codes), spec.name


@pytest.mark.parametrize("specs", [FRAP_FIELDS, DINS_FIELDS])
def test_every_published_finding_of_absence_survives_classification(
    specs: tuple[FieldSpec, ...],
) -> None:
    """Declaring a finding is only useful if classify actually keeps it present."""
    for spec in specs:
        for value in spec.recorded_absences:
            assert spec.classify(value, where="r").is_present, f"{spec.name}={value}"


# --------------------------------------------------------------------------------------
# The marker audit: every judgment call carries the ground it stands on.
# docs/MARKERS.md is the audit itself; these are the invariants it must keep holding.
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("spec", ALL_FIELDS, ids=lambda s: s.name)
def test_a_field_that_declares_a_judgment_call_declares_its_basis(
    spec: FieldSpec,
) -> None:
    """No unlabelled judgment calls. A declared marker is either documented or inferred."""
    if spec.declares_vocabulary:
        assert spec.basis is not Basis.NONE, (
            f"{spec.name} declares a vocabulary but no basis; see docs/MARKERS.md"
        )
    else:
        assert spec.basis is Basis.NONE, (
            f"{spec.name} declares a basis but no vocabulary to justify"
        )


@pytest.mark.parametrize("spec", ALL_FIELDS, ids=lambda s: s.name)
def test_a_published_basis_means_every_declared_value_is_in_the_domain(
    spec: FieldSpec,
) -> None:
    """The claim "published" is checkable: the values must be in the published domain.

    Field-level codes and findings must all appear in ``domain_values``. A field with no
    published domain cannot honestly claim a published basis at all.
    """
    if spec.basis is not Basis.PUBLISHED:
        return
    assert spec.domain_values is not None, (
        f"{spec.name} claims published with no domain"
    )
    lowered = {value.lower() for value in spec.domain_values}
    for value in spec.unknown_codes | spec.recorded_absences:
        assert value in spec.domain_values, f"{spec.name}: {value!r} is not published"
    for marker in spec.unknown_markers:
        assert marker in lowered, f"{spec.name}: marker {marker!r} is not published"


def test_the_count_of_inferred_fields_is_the_one_the_pages_state() -> None:
    """The pages and the module docstring print these two numbers. Keep them true."""
    inferred = [s for s in ALL_FIELDS if s.basis is Basis.INFERRED]
    published = [s for s in ALL_FIELDS if s.basis is Basis.PUBLISHED]
    assert (len(inferred), len(published)) == (16, 12)


@pytest.mark.parametrize("spec", ALL_FIELDS, ids=lambda s: s.name)
def test_an_inferred_field_says_in_its_own_note_that_it_is_inferred(
    spec: FieldSpec,
) -> None:
    """A reader of schema.py must not have to cross-reference to learn this."""
    if spec.basis is not Basis.INFERRED:
        return
    assert "infer" in spec.note.lower() or "read off the file" in spec.note.lower(), (
        f"{spec.name}: an inferred field must say so in its note"
    )


# --------------------------------------------------------------------------------------
# docs/MARKERS.md is the audit. It must not drift away from what it audits.
# --------------------------------------------------------------------------------------

MARKERS_DOC = (Path(__file__).resolve().parents[1] / "docs" / "MARKERS.md").read_text(
    encoding="utf-8"
)


@pytest.mark.parametrize("spec", ALL_FIELDS, ids=lambda s: s.name)
def test_every_judgment_call_is_written_up_in_the_audit(spec: FieldSpec) -> None:
    """A declaration nobody wrote up is a judgment call nobody can inspect."""
    if spec.basis is Basis.NONE:
        return
    assert f"`{spec.name}`" in MARKERS_DOC, (
        f"{spec.name} declares a vocabulary but docs/MARKERS.md does not cover it"
    )


def test_the_audit_states_the_split_it_actually_found() -> None:
    inferred = sum(1 for spec in ALL_FIELDS if spec.basis is Basis.INFERRED)
    published = sum(1 for spec in ALL_FIELDS if spec.basis is Basis.PUBLISHED)
    assert "**Twelve are published. Sixteen rest on inference.**" in MARKERS_DOC
    assert (published, inferred) == (12, 16)
    assert "fifty-four measured fields" in MARKERS_DOC
    assert len(ALL_FIELDS) == 54


def test_the_audit_carries_no_em_dashes() -> None:
    assert "—" not in MARKERS_DOC


def test_the_audit_names_the_documents_it_was_checked_against() -> None:
    """An evidence basis with no URL beside it cannot be checked by a reader."""
    for url in (
        "California_Historic_Fire_Perimeters/FeatureServer/0",
        "POSTFIRE_MASTER_DATA_SHARE/FeatureServer/0",
        "db241103701846fa8c5b945cfeedda07",
        "a31aa1efe1d6466f8530b501c30ab00a",
    ):
        assert url in MARKERS_DOC, url


# --------------------------------------------------------------------------------------
# A zero in a numeric field is a judgment call too, and the audit is where those live.
# --------------------------------------------------------------------------------------

SITE_DATA = Path(__file__).resolve().parents[1] / "site" / "data"
NUMERIC_ARTIFACTS = ("perimeters-coverage.json", "dins-coverage.json")


def _published(name: str) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads((SITE_DATA / name).read_text(encoding="utf-8"))
    return payload


def numeric_zeros_missing_from_the_audit(
    payload: dict[str, Any], doc: str
) -> list[tuple[str, int]]:
    """Numeric fields publishing recorded zeros that ``docs/MARKERS.md`` never covers.

    ``recorded_zero_values`` is published for every numeric field precisely because
    whether a zero is a measurement or a placeholder is a decision somebody made. For
    ``NOOFCARSONPROPERTY`` a zero is an inspector counting no cars. For ``YEARBUILT`` no
    reading makes a zero a construction year, and 12,148 of them were counted toward
    that field's recorded share until this was written.

    The existing audit gate only reaches a field that declares a vocabulary, so a
    numeric field deciding its zeros are values decided that silently. This is the
    reader for the other half.
    """
    missing: list[tuple[str, int]] = []
    for field in payload["fields"]:
        zeros = field.get("recorded_zero_values")
        if not zeros:
            continue
        if f"`{field['name']}`" not in doc:
            missing.append((field["name"], zeros))
    return missing


@pytest.mark.parametrize("name", NUMERIC_ARTIFACTS)
def test_every_published_zero_in_a_numeric_field_is_written_up(name: str) -> None:
    unreviewed = numeric_zeros_missing_from_the_audit(_published(name), MARKERS_DOC)
    assert unreviewed == [], (
        f"{name}: these numeric fields publish recorded zeros that docs/MARKERS.md "
        f"does not cover, so nothing says whether a zero there is a measurement or a "
        f"placeholder: {unreviewed}"
    )


def test_the_zero_gate_rejects_a_numeric_field_nobody_reviewed() -> None:
    """The shape issue #24 found, run back through the gate."""
    payload = {
        "fields": [
            {"name": "YEARBUILT", "recorded_zero_values": 12148},
            {"name": "NOOFCARSONPROPERTY", "recorded_zero_values": 55831},
        ]
    }
    assert numeric_zeros_missing_from_the_audit(payload, "audit covering nothing") == [
        ("YEARBUILT", 12148),
        ("NOOFCARSONPROPERTY", 55831),
    ]


def test_the_zero_gate_says_nothing_about_a_field_with_no_zeros_to_explain() -> None:
    """A numeric field publishing no zeros has made no call, so there is nothing to write up."""
    payload = {"fields": [{"name": "LATITUDE", "recorded_zero_values": 0}]}
    assert numeric_zeros_missing_from_the_audit(payload, "audit covering nothing") == []


# --------------------------------------------------------------------------------------
# Naming a field is not the same as saying the right thing about it. Issue #52.
# --------------------------------------------------------------------------------------
#
# `numeric_zeros_missing_from_the_audit` above asks whether section 7 mentions a field.
# It cannot see a wrong number in the table it is checking, and it skips a field whose
# zeros have gone to zero, which is exactly the field whose row went stale: `YEARBUILT`
# declared `0` a marker, dropped to `recorded_zero_values: 0`, and left both the opening
# sentence's count and its own row saying what had been true the week before. The reader
# invited by README to open `dins-coverage.json` and check the one number in this
# document that names an artifact key verbatim found it wrong.
#
# So this reads the section back against the artifacts instead: the stated count, the set
# of rows, and every figure in the Recorded zeros column.

ZERO_TABLE_HEADER = "| Field | Recorded zeros | Reading | Declared? |"

_ZERO_TABLE_ROW = re.compile(
    r"^\|\s*`(?P<name>[A-Z0-9_]+)`\s*\|\s*(?P<zeros>[\d,]+)\s*\|"
)

# The sentence is wrapped in the document, so every gap in the pattern is a whitespace
# run rather than a literal space. A gate that only matches its sentence on one line is a
# gate that goes quiet the first time somebody reflows a paragraph.
_ZERO_COUNT_SENTENCE = re.compile(
    r"(?P<word>[A-Za-z]+)\s+fields?\s+publish(?:es)?\s+a\s+`recorded_zero_values`"
    r"\s+count\s+above\s+zero"
)

NUMBER_WORDS = {
    "No": 0,
    "One": 1,
    "Two": 2,
    "Three": 3,
    "Four": 4,
    "Five": 5,
    "Six": 6,
    "Seven": 7,
    "Eight": 8,
    "Nine": 9,
    "Ten": 10,
    "Eleven": 11,
    "Twelve": 12,
}


def _zero_section(doc: str) -> str:
    """Section 7 alone, so the other tables in the file are not read as its table."""
    start = doc.index("## 7. Zeros in numeric fields")
    rest = doc[start:]
    end = rest.find("\n## ", 1)
    return rest if end == -1 else rest[:end]


def _zero_table(section: str) -> dict[str, int] | None:
    """The Recorded zeros column, or ``None`` when the table is not where it was.

    ``None`` rather than an empty dict on purpose. A renamed heading or a reshaped table
    would otherwise read as a table with nothing wrong in it, which is the failure this
    whole section is about.
    """
    if ZERO_TABLE_HEADER not in section:
        return None
    body = section.split(ZERO_TABLE_HEADER, 1)[1]
    rows: dict[str, int] = {}
    for line in body.splitlines():
        if not line.startswith("|"):
            if rows:
                break
            continue
        match = _ZERO_TABLE_ROW.match(line)
        if match is not None:
            rows[match["name"]] = int(match["zeros"].replace(",", ""))
    return rows


def _stated_count_problems(section: str, actual: int) -> list[str]:
    """What the opening sentence claims, against what the artifacts publish."""
    stated = _ZERO_COUNT_SENTENCE.search(section)
    if stated is None:
        return [
            "section 7 no longer says how many fields publish recorded zeros, so the "
            "count cannot be checked"
        ]
    written = NUMBER_WORDS.get(stated["word"])
    if written is None:
        return [
            f"section 7 says {stated['word']!r} fields publish recorded zeros; this "
            f"gate reads {sorted(NUMBER_WORDS)}"
        ]
    if written != actual:
        return [
            f"section 7 says {stated['word']} fields publish recorded zeros; "
            f"{actual} do"
        ]
    return []


def zero_audit_disagreements(payloads: Sequence[dict[str, Any]], doc: str) -> list[str]:
    """Every way section 7 can disagree with the artifacts it describes."""
    section = _zero_section(doc)
    published = {
        field["name"]: field["recorded_zero_values"]
        for payload in payloads
        for field in payload["fields"]
        if field.get("recorded_zero_values")
    }
    rows = _zero_table(section)
    if rows is None:
        return [f"section 7 has no table headed {ZERO_TABLE_HEADER!r} to check"]
    problems: list[str] = []
    if not rows:
        problems.append("section 7's table has no field rows, so it checks nothing")
    for name, count in sorted(published.items()):
        if name not in rows:
            problems.append(
                f"{name} publishes {count} recorded zeros and section 7's table has no "
                f"row for it"
            )
        elif rows[name] != count:
            problems.append(
                f"{name}: section 7's table says {rows[name]} recorded zeros, the "
                f"artifacts publish {count}"
            )
    for name, count in sorted(rows.items()):
        if name not in published:
            problems.append(
                f"{name}: section 7's table gives it {count} recorded zeros, the "
                f"artifacts publish none"
            )
    problems.extend(_stated_count_problems(section, len(published)))
    return problems


def test_the_zero_audit_agrees_with_the_artifacts_it_describes() -> None:
    disagreements = zero_audit_disagreements(
        [_published(name) for name in NUMERIC_ARTIFACTS], MARKERS_DOC
    )
    assert disagreements == [], (
        "docs/MARKERS.md section 7 contradicts site/data/*-coverage.json: "
        f"{disagreements}"
    )


# Every field named here is named somewhere in the text, which is all the older gate
# looks for. `ASSESSEDIMPROVEDVALUE` is discussed in prose and has no row; the
# `NOOFCARSONPROPERTY` row is one short; `YEARBUILT` keeps a row it stopped earning; and
# the opening count still says six. `numeric_zeros_missing_from_the_audit` reports none
# of it.
STALE_SECTION = """## 7. Zeros in numeric fields

Six fields publish a `recorded_zero_values` count above zero.

| Field | Recorded zeros | Reading | Declared? |
|---|---|---|---|
| `NOOFCARSONPROPERTY` | 55,830 | a count of no cars | no |
| `YEARBUILT` | 12,148 | a parcel record with no year | yes |

### `ASSESSEDIMPROVEDVALUE`: considered, and not declared

A parcel assessed at zero improved value is a thing that exists.

## 8. Something else
"""


def test_the_gate_catches_the_shape_issue_52_found() -> None:
    """A stale row, a stale count, a figure that drifted, and a row that is missing."""
    payloads = [
        {
            "fields": [
                {"name": "NOOFCARSONPROPERTY", "recorded_zero_values": 55831},
                {"name": "ASSESSEDIMPROVEDVALUE", "recorded_zero_values": 6613},
                {"name": "YEARBUILT", "recorded_zero_values": 0},
            ]
        }
    ]
    assert zero_audit_disagreements(payloads, STALE_SECTION) == [
        "ASSESSEDIMPROVEDVALUE publishes 6613 recorded zeros and section 7's table has "
        "no row for it",
        "NOOFCARSONPROPERTY: section 7's table says 55830 recorded zeros, the artifacts "
        "publish 55831",
        "YEARBUILT: section 7's table gives it 12148 recorded zeros, the artifacts "
        "publish none",
        "section 7 says Six fields publish recorded zeros; 2 do",
    ]


def test_the_older_gate_is_blind_to_all_four_of_them() -> None:
    """Why a second gate had to exist rather than the first one being tightened.

    `numeric_zeros_missing_from_the_audit` asks whether a field is named in the file. All
    three of these are, and the field whose row went stale publishes no zeros at all, so
    it is skipped before the question is even asked.
    """
    payload = {
        "fields": [
            {"name": "NOOFCARSONPROPERTY", "recorded_zero_values": 55831},
            {"name": "ASSESSEDIMPROVEDVALUE", "recorded_zero_values": 6613},
            {"name": "YEARBUILT", "recorded_zero_values": 0},
        ]
    }
    assert numeric_zeros_missing_from_the_audit(payload, STALE_SECTION) == []


def test_the_gate_refuses_a_section_whose_table_moved() -> None:
    """A renamed heading must not read as a table with nothing wrong in it."""
    moved = "## 7. Zeros in numeric fields\n\nNo table here.\n\n## 8. Next\n"
    assert zero_audit_disagreements([{"fields": []}], moved) == [
        f"section 7 has no table headed {ZERO_TABLE_HEADER!r} to check"
    ]


def test_the_gate_refuses_a_table_with_no_rows() -> None:
    empty = (
        "## 7. Zeros in numeric fields\n\n"
        "No fields publish a `recorded_zero_values` count above zero.\n\n"
        f"{ZERO_TABLE_HEADER}\n|---|---|---|---|\n\n## 8. Next\n"
    )
    assert zero_audit_disagreements([{"fields": []}], empty) == [
        "section 7's table has no field rows, so it checks nothing"
    ]


def test_the_gate_refuses_a_section_that_stopped_stating_the_count() -> None:
    """Deleting the sentence must not be a way to stop it being checked."""
    silent = (
        "## 7. Zeros in numeric fields\n\nSome fields have zeros in them.\n\n"
        f"{ZERO_TABLE_HEADER}\n|---|---|---|---|\n"
        "| `NOOFCARSONPROPERTY` | 55,831 | a count of no cars | no |\n\n## 8. Next\n"
    )
    payloads = [
        {"fields": [{"name": "NOOFCARSONPROPERTY", "recorded_zero_values": 55831}]}
    ]
    assert zero_audit_disagreements(payloads, silent) == [
        "section 7 no longer says how many fields publish recorded zeros, so the count "
        "cannot be checked"
    ]


def test_the_gate_refuses_a_count_it_cannot_read() -> None:
    """A word this gate cannot turn into a number is a count nobody is checking."""
    vague = (
        "## 7. Zeros in numeric fields\n\n"
        "Several fields publish a `recorded_zero_values` count above zero.\n\n"
        f"{ZERO_TABLE_HEADER}\n|---|---|---|---|\n"
        "| `NOOFCARSONPROPERTY` | 55,831 | a count of no cars | no |\n\n## 8. Next\n"
    )
    payloads = [
        {"fields": [{"name": "NOOFCARSONPROPERTY", "recorded_zero_values": 55831}]}
    ]
    problems = zero_audit_disagreements(payloads, vague)
    assert len(problems) == 1
    assert problems[0].startswith(
        "section 7 says 'Several' fields publish recorded zeros"
    )


# --------------------------------------------------------------------------------------
# A zero nobody ruled on is not a measurement (ADR-0006, issue #83)
# --------------------------------------------------------------------------------------

#: The last column of section 7's table, where the registry's declared reading is repeated
#: for a human. Matched as a backticked token so "reviewed" in prose cannot satisfy it.
_ZERO_READING_IN_ROW = re.compile(
    r"^\|\s*`(?P<name>[A-Z0-9_]+)`\s*\|[^|]*\|[^|]*\|(?P<declared>[^|]*)\|"
)


def _section_seven_readings(doc: str) -> dict[str, str]:
    """Field name to the reading word section 7's table states for it."""
    section = _zero_section(doc)
    found: dict[str, str] = {}
    for line in section.splitlines():
        match = _ZERO_READING_IN_ROW.match(line)
        if match is None:
            continue
        words = [
            reading.value
            for reading in ZeroReading
            if f"`{reading.value}`" in match["declared"]
        ]
        if len(words) == 1:
            found[match["name"]] = words[0]
    return found


@pytest.mark.parametrize("spec", ALL_FIELDS, ids=lambda s: s.name)
def test_only_a_field_measured_as_a_number_rules_on_its_zeros(spec: FieldSpec) -> None:
    """A field with no zeros to rule on has not ruled on any.

    Without this, a free-text field could be marked `measurement` and would enter the
    reviewed numerator of a question that does not apply to it -- a coverage figure made
    to look better by widening it with rows nobody had to examine.
    """
    if spec.numeric:
        return
    assert spec.zero_reading is ZeroReading.UNREVIEWED, (
        f"{spec.name} is not measured as a number, so it has no zeros to rule on, but it "
        f"declares zero_reading={spec.zero_reading.value!r}"
    )


@pytest.mark.parametrize("spec", ALL_FIELDS, ids=lambda s: s.name)
def test_a_marker_reading_and_a_declared_zero_marker_are_the_same_fact(
    spec: FieldSpec,
) -> None:
    """`marker` in the registry and `0` in the marker set must travel together.

    Either half alone is a lie in one direction: the word without the declaration says the
    zeros are counted as unknown when they are still counted as values, and the
    declaration without the word leaves the audit unable to see why the field publishes
    none.
    """
    declared = "0" in spec.unknown_markers or "0" in spec.unknown_codes
    says_marker = spec.zero_reading is ZeroReading.MARKER
    assert declared == says_marker, (
        f"{spec.name}: zero_reading is {spec.zero_reading.value!r} but `0` is "
        f"{'' if declared else 'not '}declared as a marker for it"
    )


def unruled_published_zeros(payload: dict[str, Any]) -> list[tuple[str, int]]:
    """Fields publishing a recorded zero while saying nobody has ruled on what one means.

    THE gate for issue #83. `numeric_zeros_missing_from_the_audit` asks whether the field
    is NAMED in docs/MARKERS.md, which a field can be while the document says nothing
    about its zeros; and until `zero_reading` existed nothing could ask the stronger
    question at all, because a reviewed decision and an unexamined field both published
    `marker_basis: "none"`.
    """
    return [
        (field["name"], field["recorded_zero_values"])
        for field in payload["fields"]
        if field.get("recorded_zero_values")
        and field.get("recorded_zero_reading") == ZeroReading.UNREVIEWED.value
    ]


@pytest.mark.parametrize("name", NUMERIC_ARTIFACTS)
def test_no_published_zero_is_one_nobody_ruled_on(name: str) -> None:
    unruled = unruled_published_zeros(_published(name))
    assert unruled == [], (
        f"{name}: these fields publish a recorded zero while declaring that nobody has "
        f"ruled on what a zero there means, so an absence may be being published as a "
        f"measurement: {unruled}. Read the field's form and set `zero_reading` on it in "
        f"src/perimeter/schema.py, then write the reading up in docs/MARKERS.md §7."
    )


def test_the_unruled_zero_gate_catches_the_shape_issue_83_found() -> None:
    """The five fields as they stood when #83 was filed, run back through the gate.

    A positive control: the gate above passes on the committed artifacts, and a passing
    gate is worth nothing until it has been shown to fail on the thing it is for.
    """
    before = {
        "fields": [
            {
                "name": "NOOFCARSONPROPERTY",
                "recorded_zero_values": 55831,
                "recorded_zero_reading": "unreviewed",
            },
            {
                "name": "NUMBEROFUNITPERSTRUCTURE",
                "recorded_zero_values": 58411,
                "recorded_zero_reading": "unreviewed",
            },
            {
                "name": "YEARBUILT",
                "recorded_zero_values": 0,
                "recorded_zero_reading": "marker",
            },
            {"name": "CITY", "markers": {"NA": 1}},
        ]
    }
    assert unruled_published_zeros(before) == [
        ("NOOFCARSONPROPERTY", 55831),
        ("NUMBEROFUNITPERSTRUCTURE", 58411),
    ]


@pytest.mark.parametrize("spec", ALL_FIELDS, ids=lambda s: s.name)
def test_every_ruling_on_a_zero_is_written_up_in_the_audit(spec: FieldSpec) -> None:
    """A reading nobody wrote up is a judgment call nobody can inspect.

    The sibling of `test_every_judgment_call_is_written_up_in_the_audit`, on the other
    axis. `Basis.NONE` and `ZeroReading.UNREVIEWED` are different absences and a field can
    be in one without being in the other -- which is the whole point of the second axis.
    """
    if spec.zero_reading is ZeroReading.UNREVIEWED:
        return
    assert f"`{spec.name}`" in MARKERS_DOC, (
        f"{spec.name} declares zero_reading={spec.zero_reading.value!r} and "
        f"docs/MARKERS.md never names it"
    )


def test_section_seven_states_the_reading_the_registry_carries() -> None:
    """The document and the registry, held to each other by an exact token.

    Both directions. A row whose word drifts from the registry is caught, and so is a row
    that stops carrying a word at all -- because a row with no word parses as absent here
    and the field it names is in the registry with one.
    """
    stated = _section_seven_readings(MARKERS_DOC)
    published = {
        field["name"]: field.get("recorded_zero_reading")
        for name in NUMERIC_ARTIFACTS
        for field in _published(name)["fields"]
        if field.get("recorded_zero_values")
    }
    assert stated, (
        "section 7's table no longer states a reading word for any field, so this gate "
        "checks nothing"
    )
    assert stated == published, (
        f"docs/MARKERS.md section 7 and the artifacts disagree about which reading each "
        f"field's zeros carry: doc={stated}, artifacts={published}"
    )


def _coverage_of(spec: FieldSpec, values: Sequence[object]) -> FieldCoverage:
    """One field's coverage over a handful of made-up cells."""
    records = [
        Record(identifier=str(index), cells={spec.name: spec.classify(raw, where="t")})
        for index, raw in enumerate(values)
    ]
    return field_coverage(records, spec)


def test_the_two_numbers_are_counted_separately() -> None:
    """`reviewed` counts rulings; `examinable` counts questions. Never the same walk.

    A control, not a restatement of :func:`zero_review`. Every other gate on this block
    reads the committed artifact, where the two numbers happen to be 6 and 8 because six
    fields have been ruled on -- so a build that counted every examinable field as
    reviewed would publish `8 of 8` and every one of those gates would still pass, because
    each of them recomputes the block from the same payload the block was written into.
    Measured 2026-09-13: `reviewed=len(numeric)` in `zero_review` left all 1,158 tests
    green. This is the one that reads the function's own answer over a field set whose two
    numbers are known to differ.
    """
    ruled = FieldSpec(
        "RULED", "Ruled", numeric=True, zero_reading=ZeroReading.MEASUREMENT
    )
    unruled = FieldSpec("UNRULED", "Unruled", numeric=True)
    text = FieldSpec("TEXT", "Not a number")
    review = zero_review(
        [
            _coverage_of(ruled, ["0", "1"]),
            _coverage_of(unruled, ["0", "2"]),
            _coverage_of(text, ["a", "b"]),
        ]
    )
    assert review.examinable == 2, "the free-text field is not a zero question"
    assert review.reviewed == 1
    assert review.unreviewed_fields == ("UNRULED",)
    assert review.unreviewed == 1
    assert review.publishing_zeros == 2
    assert review.publishing_zeros_reviewed == 1


def test_a_field_with_no_zeros_still_counts_as_a_question() -> None:
    """The reason `examinable` is not "fields publishing a zero".

    `LATITUDE` and `LONGITUDE` hold no zeros in this retrieval and nobody has ruled on
    them. A denominator of "fields publishing a zero today" would report 5 of 5 and be
    true, and the first zero to arrive in either would be published as a measurement
    nobody had ruled on -- the exact shape issue #83 reported.
    """
    unruled = FieldSpec("NOZEROS", "No zeros here", numeric=True)
    review = zero_review([_coverage_of(unruled, ["1", "2"])])
    assert review.examinable == 1
    assert review.reviewed == 0
    assert review.publishing_zeros == 0
    assert review.publishing_zeros_reviewed == 0


@pytest.mark.parametrize("name", NUMERIC_ARTIFACTS)
def test_the_published_zero_review_re_derives_from_the_fields_beside_it(
    name: str,
) -> None:
    """The two numbers, recomputed from the rows they describe.

    A summary block is exactly the shape that goes stale silently: it is small, it reads
    as a headline, and nothing else in the artifact contradicts it. Recomputing it here
    from the same document means the published figure cannot be one the fields do not
    support.
    """
    payload = _published(name)
    numeric = [field for field in payload["fields"] if "recorded_zero_reading" in field]
    review = payload["recorded_zero_review"]
    assert review["fields_measured_as_numbers"] == len(numeric)
    assert review["fields_with_a_reviewed_zero_reading"] == sum(
        1
        for field in numeric
        if field["recorded_zero_reading"] != ZeroReading.UNREVIEWED.value
    )
    assert review["fields_without_one"] == [
        field["name"]
        for field in numeric
        if field["recorded_zero_reading"] == ZeroReading.UNREVIEWED.value
    ]
    with_zeros = [field for field in numeric if field["recorded_zero_values"]]
    assert review["fields_publishing_a_recorded_zero"] == len(with_zeros)
    assert review["fields_publishing_a_recorded_zero_with_a_reviewed_reading"] == sum(
        1
        for field in with_zeros
        if field["recorded_zero_reading"] != ZeroReading.UNREVIEWED.value
    )
    # The denominator and the numerator are not the same number, and a build where they
    # are would make the gap this issue is about invisible again.
    assert (
        review["fields_with_a_reviewed_zero_reading"]
        <= review["fields_measured_as_numbers"]
    )
