"""Classification and the two fail-closed refusals."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from perimeter.cells import Cell, CellState, SentinelDriftError
from perimeter.schema import (
    DINS_FIELDS,
    DINS_FIELDS_BY_NAME,
    FRAP_FIELDS,
    FRAP_FIELDS_BY_NAME,
    Basis,
    FieldSpec,
    SchemaDriftError,
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
