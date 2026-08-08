"""Classification and the two fail-closed refusals."""

from __future__ import annotations

import pytest

from perimeter.cells import Cell, CellState, SentinelDriftError
from perimeter.schema import (
    DINS_FIELDS,
    DINS_FIELDS_BY_NAME,
    FRAP_FIELDS,
    FRAP_FIELDS_BY_NAME,
    FieldSpec,
    SchemaDriftError,
    require_columns,
)

PLAIN = FieldSpec("PLAIN", "Plain")


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


def test_the_two_not_applicable_spellings_are_not_assumed_to_match() -> None:
    """The published domain spells it NA; N/A also appears and is not merged into it."""
    spec = DINS_FIELDS_BY_NAME["UTILITYMISCSTRUCTUREDISTANCE"]
    assert spec.classify("NA", where="r").is_present
    assert spec.classify("N/A", where="r").state is CellState.EXPLICIT_UNKNOWN


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
