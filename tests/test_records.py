"""Parsing at the edge, and the file-level refusals."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from perimeter.cells import Cell
from perimeter.records import (
    Record,
    float_value,
    integer_value,
    load_rows,
    parse_records,
)
from perimeter.schema import FieldSpec, SchemaDriftError

SPECS = (FieldSpec("NAME", "Name"), FieldSpec("SIZE", "Size", numeric=True))
REQUIRED = ("ID",)


def parse(rows: list[dict[str, object]]) -> list[Record]:
    return parse_records(
        rows, specs=SPECS, required=REQUIRED, id_field="ID", source="S"
    )


def test_every_measured_cell_is_classified_at_parse_time() -> None:
    records = parse([{"ID": 1, "NAME": "Cedar", "SIZE": None}])
    assert records[0].identifier == "1"
    assert records[0].cell("NAME").value() == "Cedar"
    assert not records[0].cell("SIZE").is_present


def test_a_missing_identity_column_stops_the_build() -> None:
    with pytest.raises(SchemaDriftError, match="ID"):
        parse([{"NAME": "Cedar", "SIZE": 1}])


def test_a_missing_measured_column_stops_the_build() -> None:
    """Otherwise the field would be published as one nobody ever filled in."""
    with pytest.raises(SchemaDriftError, match="SIZE"):
        parse([{"ID": 1, "NAME": "Cedar"}])


def test_a_row_without_an_identifier_stops_the_build() -> None:
    with pytest.raises(SchemaDriftError, match="has no ID"):
        parse([{"ID": 1, "NAME": "a", "SIZE": 1}, {"ID": "  ", "NAME": "b", "SIZE": 2}])


def test_an_empty_source_is_zero_records_not_an_error() -> None:
    """Zero records is a real state of a source and is reported as zero."""
    assert parse([]) == []


def test_asking_a_record_for_an_unparsed_field_raises() -> None:
    record = Record(identifier="1", cells={"NAME": Cell.present("Cedar")})
    with pytest.raises(SchemaDriftError, match="never parsed"):
        record.cell("SIZE")


def test_reading_a_number_out_of_a_blank_gives_none_never_zero() -> None:
    assert integer_value(Cell.not_recorded(), field="SIZE", where="r") is None
    assert float_value(Cell.not_recorded(), field="SIZE", where="r") is None
    assert integer_value(Cell.explicit_unknown("na"), field="SIZE", where="r") is None


def test_a_recorded_zero_reads_back_as_zero() -> None:
    assert integer_value(Cell.present("0"), field="SIZE", where="r") == 0
    assert float_value(Cell.present("0.0"), field="SIZE", where="r") == 0.0


def test_numbers_parse() -> None:
    assert integer_value(Cell.present("42.0"), field="SIZE", where="r") == 42
    assert float_value(Cell.present("4.5"), field="SIZE", where="r") == 4.5


@pytest.mark.parametrize("reader", [integer_value, float_value])
def test_a_non_number_in_a_numeric_field_stops_the_build(reader: object) -> None:
    with pytest.raises(SchemaDriftError, match="not a number"):
        reader(Cell.present("many"), field="SIZE", where="r")  # type: ignore[operator]


def test_load_rows_reads_an_array_of_objects(tmp_path: Path) -> None:
    path = tmp_path / "rows.json"
    path.write_text(json.dumps([{"ID": 1}]), encoding="utf-8")
    assert load_rows(path) == [{"ID": 1}]


def test_load_rows_refuses_a_payload_that_is_not_an_array(tmp_path: Path) -> None:
    path = tmp_path / "rows.json"
    path.write_text(json.dumps({"ID": 1}), encoding="utf-8")
    with pytest.raises(SchemaDriftError, match="expected a JSON array"):
        load_rows(path)


def test_load_rows_refuses_a_row_that_is_not_an_object(tmp_path: Path) -> None:
    path = tmp_path / "rows.json"
    path.write_text(json.dumps([{"ID": 1}, 7]), encoding="utf-8")
    with pytest.raises(SchemaDriftError, match="row 1 is int"):
        load_rows(path)
