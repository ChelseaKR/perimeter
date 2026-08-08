"""The three states, and the guarantees that keep them apart."""

from __future__ import annotations

import pytest

from perimeter.cells import (
    SUSPECTED_SENTINELS,
    Cell,
    CellState,
    MissingValueError,
    coverage,
    normalize_marker,
    present_tenths_of_percent,
)


def test_present_cell_hands_over_its_value() -> None:
    assert Cell.present("Wood").value() == "Wood"
    assert Cell.present("Wood").is_present


def test_a_recorded_zero_is_a_value() -> None:
    cell = Cell.present("0")
    assert cell.is_present
    assert cell.value() == "0"


@pytest.mark.parametrize(
    "cell", [Cell.not_recorded(), Cell.explicit_unknown("unknown")]
)
def test_a_cell_without_a_value_refuses_to_produce_one(cell: Cell) -> None:
    """The whole point: no caller can read a number out of an absence."""
    with pytest.raises(MissingValueError):
        cell.value()
    assert not cell.is_present


def test_explicit_unknown_keeps_its_marker_but_not_as_a_value() -> None:
    cell = Cell.explicit_unknown("n/a")
    assert cell.marker == "n/a"
    with pytest.raises(MissingValueError):
        cell.value()


def test_only_explicit_unknown_cells_report_a_marker() -> None:
    assert Cell.present("Wood").marker is None
    assert Cell.not_recorded().marker is None


def test_a_present_cell_built_without_a_value_still_refuses() -> None:
    """Defends the invariant even if a Cell is constructed directly."""
    with pytest.raises(MissingValueError):
        Cell(CellState.PRESENT, None).value()


def test_coverage_always_publishes_all_three_states() -> None:
    counts = coverage([Cell.present("x"), Cell.present("y")])
    assert counts == {"present": 2, "explicit_unknown": 0, "not_recorded": 0}


def test_coverage_of_nothing_is_three_zeroes_not_an_empty_object() -> None:
    assert coverage([]) == {
        "present": 0,
        "explicit_unknown": 0,
        "not_recorded": 0,
    }


def test_coverage_counts_each_state_separately() -> None:
    counts = coverage(
        [
            Cell.present("x"),
            Cell.explicit_unknown("unknown"),
            Cell.explicit_unknown("na"),
            Cell.not_recorded(),
        ]
    )
    assert counts == {"present": 1, "explicit_unknown": 2, "not_recorded": 1}


@pytest.mark.parametrize(
    ("present", "total", "expected"),
    [(1, 1, 1000), (0, 10, 0), (1, 3, 333), (2, 3, 667), (156, 1000, 156)],
)
def test_share_is_integer_arithmetic(present: int, total: int, expected: int) -> None:
    assert present_tenths_of_percent(present, total) == expected


def test_a_share_over_nothing_does_not_exist() -> None:
    """Not zero percent, not a hundred percent. Absent."""
    assert present_tenths_of_percent(0, 0) is None
    assert present_tenths_of_percent(5, -1) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("Unknown ", "unknown"), ("  N/A", "n/a"), ("N/a", "n/a"), ("NA", "na")],
)
def test_marker_normalization_folds_case_and_whitespace(
    raw: str, expected: str
) -> None:
    assert normalize_marker(raw) == expected


def test_the_suspected_set_is_normalized_itself() -> None:
    """Every entry must already be in normal form, or it could never match."""
    for marker in SUSPECTED_SENTINELS:
        assert normalize_marker(marker) == marker
