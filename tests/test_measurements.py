"""The two measurements, over the committed fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from perimeter.cells import Cell, CellState
from perimeter.coverage import (
    DinsReport,
    PerimeterReport,
    dins_report,
    field_coverage,
    perimeter_report,
)
from perimeter.dins import (
    access_split,
    damage_distribution,
    group_by_incident,
    incident_key,
    is_assessed,
    is_inaccessible,
    load_inspections,
)
from perimeter.perimeters import (
    acres_of,
    decade_of,
    load_perimeters,
    year_of,
)
from perimeter.records import Record
from perimeter.schema import (
    DINS_FIELDS,
    DINS_FIELDS_BY_NAME,
    FRAP_FIELDS_BY_NAME,
    FieldSpec,
    SchemaDriftError,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture(scope="module")
def perimeters() -> list[Record]:
    return load_perimeters(FIXTURES / "frap_perimeters.sample.json")


@pytest.fixture(scope="module")
def inspections() -> list[Record]:
    return load_inspections(FIXTURES / "dins_postfire.sample.json")


@pytest.fixture(scope="module")
def frap(perimeters: list[Record]) -> PerimeterReport:
    return perimeter_report(perimeters)


@pytest.fixture(scope="module")
def dins(inspections: list[Record]) -> DinsReport:
    return dins_report(inspections)


# --- FRAP -----------------------------------------------------------------------------


def test_records_without_a_year_are_their_own_cohort(frap: PerimeterReport) -> None:
    """Never attached to a neighbouring year, never dropped."""
    assert frap.records == 10
    assert frap.records_without_year == 1
    no_year = [cohort for cohort in frap.years if cohort.year is None]
    assert len(no_year) == 1
    assert no_year[0].records == 1
    assert sum(cohort.records for cohort in frap.years) == frap.records


def test_year_cohorts_are_ordered_with_the_no_year_cohort_last(
    frap: PerimeterReport,
) -> None:
    years = [cohort.year for cohort in frap.years]
    assert years == [1878, 1955, 1995, 2021, None]
    assert frap.earliest_year == 1878
    assert frap.latest_year == 2025 or frap.latest_year == 2021


def test_an_empty_string_identifier_is_absent_not_present(
    perimeters: list[Record],
) -> None:
    """The fixture holds one record whose IRWIN ID is "" rather than null."""
    record = next(r for r in perimeters if r.identifier == "3")
    assert not record.cell("IRWINID").is_present
    assert frap_irwin_total(perimeters) == 4


def frap_irwin_total(records: list[Record]) -> int:
    return sum(1 for r in records if r.cell("IRWINID").is_present)


def test_a_field_with_no_blanks_can_still_be_far_from_complete(
    perimeters: list[Record],
) -> None:
    """Cause: nothing empty, and several records recorded as Unknown."""
    cause = field_coverage(perimeters, FRAP_FIELDS_BY_NAME["CAUSE"])
    assert cause.not_recorded == 0
    assert cause.explicit_unknown == 3
    assert cause.present == 7
    assert cause.present_tenths_pct == 700


def test_an_all_zeros_identifier_is_counted_apart_from_recorded_ones(
    perimeters: list[Record],
) -> None:
    incident = field_coverage(perimeters, FRAP_FIELDS_BY_NAME["INC_NUM"])
    assert incident.markers == {"00000000": 2}
    assert incident.explicit_unknown == 2


def test_duplicate_signals_only_key_records_carrying_the_whole_key(
    frap: PerimeterReport,
) -> None:
    signals = {signal.key: signal for signal in frap.duplicates}
    irwin = signals["irwin_id"]
    assert irwin.keyed_records == 4
    assert irwin.reused_keys == 1
    assert irwin.records_sharing_a_key == 2

    local = signals["year_unit_incident_number"]
    # Records whose incident number is the all-zeros marker are not keyed at all.
    assert local.keyed_records == 6
    assert local.records_sharing_a_key == 4


def test_acreage_cohorts_count_against_the_published_thresholds(
    frap: PerimeterReport,
) -> None:
    by_decade = {cohort.decade: cohort for cohort in frap.thresholds}
    assert by_decade[1950].below[10] == 1
    assert by_decade[1950].below[300] == 1
    assert by_decade[2020].below[10] == 1
    assert None in by_decade


def test_year_and_acres_read_back_as_numbers(perimeters: list[Record]) -> None:
    record = next(r for r in perimeters if r.identifier == "1")
    assert year_of(record) == 2021
    assert acres_of(record) == pytest.approx(1204.5)
    assert decade_of(record) == 2020


def test_a_record_without_a_year_has_no_decade(perimeters: list[Record]) -> None:
    record = next(r for r in perimeters if r.identifier == "3")
    assert year_of(record) is None
    assert decade_of(record) is None


def test_a_year_that_is_not_a_year_stops_the_build() -> None:
    spec = FieldSpec("YEAR_", "Year")
    record = Record(identifier="9", cells={"YEAR_": spec.classify("soon", where="r")})
    with pytest.raises(SchemaDriftError, match="not a year"):
        year_of(record)


# --- DINS -----------------------------------------------------------------------------


def test_no_damage_is_a_finding_and_not_a_blank(dins: DinsReport) -> None:
    assert dins.damage["No Damage"] == 2
    damage = next(f for f in dins.fields if f.name == "DAMAGE")
    assert damage.not_recorded == 0
    assert damage.present == dins.records


def test_inaccessible_is_a_recorded_value_kept_apart_from_assessed(
    dins: DinsReport,
) -> None:
    assert dins.access.assessed == 8
    assert dins.access.inaccessible == 2
    assert dins.access.damage_not_recorded == 0
    assert dins.access.total == dins.records


def test_completeness_is_reported_separately_for_the_two_populations(
    dins: DinsReport,
) -> None:
    """A blank on a structure nobody could reach is not the same fact."""
    roof = next(row for row in dins.by_access if row.name == "ROOFCONSTRUCTION")
    assert roof.assessed_total == 8
    assert roof.inaccessible_total == 2
    assert roof.inaccessible_present == 0
    assert roof.inaccessible_tenths_pct == 0
    assert roof.assessed_present == 5


def test_a_recorded_zero_is_counted_as_a_value_and_as_a_zero(
    inspections: list[Record],
) -> None:
    outbuildings = field_coverage(
        inspections, DINS_FIELDS_BY_NAME["NOOUTBUILDINGSDAMAGED"]
    )
    assert outbuildings.present == 3
    assert outbuildings.zero_values == 2
    assert outbuildings.not_recorded == 7
    assert outbuildings.present + outbuildings.not_recorded == 10


def test_out_of_domain_values_are_named_and_counted(
    inspections: list[Record],
) -> None:
    roof = field_coverage(inspections, DINS_FIELDS_BY_NAME["ROOFCONSTRUCTION"])
    assert roof.outside_domain == 1
    assert roof.outside_domain_values == {"Fire Resistant": 1}
    assert roof.outside_domain_distinct == 1


def test_incidents_differing_in_what_was_recorded_are_not_merged(
    dins: DinsReport,
) -> None:
    assert dins.incidents == 3
    assert dins.unattributed_records == 0
    keys = [
        (row.key.name, row.key.number, row.key.start_year) for row in dins.incident_rows
    ]
    assert ("ELM", None, 1995) in keys
    assert sum(row.records for row in dins.incident_rows) == dins.records


def test_per_incident_coverage_differs_between_incidents(dins: DinsReport) -> None:
    by_name = {row.key.name: row for row in dins.incident_rows}
    alder = {field.name: field for field in by_name["ALDER"].fields}
    elm = {field.name: field for field in by_name["ELM"].fields}
    assert alder["ROOFCONSTRUCTION"].present == 3
    assert elm["ROOFCONSTRUCTION"].present == 0
    assert elm["ROOFCONSTRUCTION"].not_recorded == 1


def test_a_record_with_no_incident_identity_at_all_is_set_aside() -> None:
    spec = FieldSpec("X", "X")
    blank = Record(
        identifier="1",
        cells={
            "INCIDENTNAME": spec.classify(None, where="r"),
            "INCIDENTNUM": spec.classify(None, where="r"),
            "INCIDENTSTARTDATE": spec.classify(None, where="r"),
            "DAMAGE": spec.classify("No Damage", where="r"),
        },
    )
    groups, unattributed = group_by_incident([blank])
    assert groups == []
    assert len(unattributed) == 1
    assert incident_key(blank).is_empty


def test_damage_helpers_agree_with_the_split(inspections: list[Record]) -> None:
    assert sum(1 for r in inspections if is_assessed(r)) == 8
    assert sum(1 for r in inspections if is_inaccessible(r)) == 2
    assert access_split(inspections).total == len(inspections)
    assert sum(damage_distribution(inspections).values()) == len(inspections)


def test_a_start_date_that_is_not_a_timestamp_stops_the_build() -> None:
    spec = FieldSpec("INCIDENTSTARTDATE", "Start")
    record = Record(
        identifier="1",
        cells={
            "INCIDENTNAME": spec.classify("Alder", where="r"),
            "INCIDENTNUM": spec.classify(None, where="r"),
            "INCIDENTSTARTDATE": spec.classify("last summer", where="r"),
        },
    )
    with pytest.raises(SchemaDriftError, match="not a timestamp"):
        incident_key(record)


def test_reports_over_nothing_publish_zeroes_rather_than_failing() -> None:
    empty_perimeters = perimeter_report([])
    assert empty_perimeters.records == 0
    assert empty_perimeters.earliest_year is None
    assert empty_perimeters.latest_year is None
    assert all(field.present_tenths_pct is None for field in empty_perimeters.fields)

    empty_dins = dins_report([])
    assert empty_dins.records == 0
    assert empty_dins.incidents == 0
    assert all(row.assessed_tenths_pct is None for row in empty_dins.by_access)


def _damage_record(cell: Cell) -> Record:
    spec = FieldSpec("X", "X")
    blank = spec.classify(None, where="r")
    cells = {field.name: blank for field in DINS_FIELDS}
    cells["DAMAGE"] = cell
    cells["INCIDENTNAME"] = spec.classify("Alder", where="r")
    return Record(identifier="1", cells=cells)


def test_a_blank_damage_field_is_neither_assessed_nor_inaccessible() -> None:
    """No DINS record carries this today. The count exists so that if one ever
    does, it is reported rather than silently folded into the assessed population."""
    record = _damage_record(Cell.not_recorded())
    split = access_split([record])
    assert split.damage_not_recorded == 1
    assert split.assessed == 0
    assert split.inaccessible == 0
    assert damage_distribution([record]) == {"not_recorded": 1}


def test_a_damage_field_holding_a_marker_is_counted_as_a_marker() -> None:
    record = _damage_record(Cell.explicit_unknown("unknown"))
    split = access_split([record])
    assert split.damage_explicit_unknown == 1
    assert split.assessed == 0
    assert damage_distribution([record]) == {"explicit_unknown": 1}


def test_a_field_whose_marker_was_lost_still_counts_in_its_state() -> None:
    """Guards the coverage counter against a marker-less explicit-unknown cell."""
    record = _damage_record(Cell(CellState.EXPLICIT_UNKNOWN, None))
    damage = field_coverage([record], DINS_FIELDS_BY_NAME["DAMAGE"])
    assert damage.explicit_unknown == 1
    assert damage.markers == {}
