"""Three states for one cell, kept apart everywhere: present, explicit-unknown, not-recorded.

CAL FIRE's own DINS documentation says it plainly: "Attributes with null values could
not be determined." A blank cell is therefore a statement about the inspection, not a
measurement of the structure. Its perimeter datasets also carry codes that mean the
opposite thing: ``CAUSE = 14`` is "Unknown / Unidentified", a value somebody wrote down
on purpose, and ``No Eaves`` is an eave observation, not a missing eave field.

Three facts, never collapsed:

    present            a value the agency recorded, including a genuine zero and
                       including recorded absences such as "No Damage" or "No Fence"
    explicit_unknown   the agency recorded a documented marker meaning it could not
                       determine the value: an observation that determination failed
    not_recorded       the cell is empty; nothing was written down either way

A :class:`Cell` makes collapsing them impossible at the type level, because the value of
a non-present cell cannot be read at all. Anything that looks like a missing-data marker
but is not one this project has reviewed stops the build instead of being guessed at.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

SUSPECTED_SENTINELS = frozenset(
    {
        "-",
        "--",
        "?",
        "n/a",
        "n.a.",
        "na",
        "nil",
        "no data",
        "nodata",
        "none",
        "not applicable",
        "not collected",
        "not determined",
        "not inspected",
        "not recorded",
        "null",
        "tbd",
        "unk",
        "unknown",
        "<null>",
    }
)
"""Text that would be a missing-data marker in most datasets.

Any cell whose value normalizes into this set, in a field that has not declared that
exact marker, stops the build. Guessing here would turn one agency's absence into
another project's value.
"""


class CellState(Enum):
    PRESENT = "present"
    EXPLICIT_UNKNOWN = "explicit_unknown"
    NOT_RECORDED = "not_recorded"


class MissingValueError(ValueError):
    """A caller tried to read a value out of a cell that holds no value."""


class SentinelDriftError(ValueError):
    """A cell held a missing-data marker this project has not reviewed for that field."""


@dataclass(frozen=True)
class Cell:
    """One source cell, classified. Only a present cell will hand over its value."""

    state: CellState
    _value: str | None = None

    @classmethod
    def present(cls, value: str) -> Cell:
        return cls(CellState.PRESENT, value)

    @classmethod
    def explicit_unknown(cls, marker: str) -> Cell:
        # The marker is kept so coverage output can report which marker was used, but it
        # is not reachable through value(); it is not a measurement of the thing.
        return cls(CellState.EXPLICIT_UNKNOWN, marker)

    @classmethod
    def not_recorded(cls) -> Cell:
        return cls(CellState.NOT_RECORDED)

    def value(self) -> str:
        """The recorded value. Raises unless the agency actually recorded one."""
        if self.state is not CellState.PRESENT or self._value is None:
            raise MissingValueError(
                f"no recorded value to read: cell is {self.state.value}"
            )
        return self._value

    @property
    def marker(self) -> str | None:
        """Which documented unknown-marker was used, for explicit-unknown cells only."""
        return self._value if self.state is CellState.EXPLICIT_UNKNOWN else None

    @property
    def is_present(self) -> bool:
        return self.state is CellState.PRESENT


def normalize_marker(text: str) -> str:
    """Fold a cell's text the way a missing-data marker would be written by anyone."""
    return " ".join(text.split()).strip().lower()


def coverage(cells: Iterable[Cell]) -> dict[str, int]:
    """Counts for all three states, every key always present.

    Coverage is a first-class output here, so a state with no cells is published as a
    zero count rather than dropped from the object. A consumer reading this must not
    have to infer that a missing key meant nothing landed there.
    """
    counts = Counter(cell.state.value for cell in cells)
    return {state.value: counts.get(state.value, 0) for state in CellState}


def present_tenths_of_percent(present: int, total: int) -> int | None:
    """Present share in tenths of a percent, by integer arithmetic, or ``None``.

    Returns ``None`` when there is nothing to divide by. A coverage rate over an empty
    cohort is not zero percent and is not a hundred percent; it does not exist, and this
    project publishes it as absent rather than inventing a number for a chart to draw.
    Integer arithmetic keeps re-runs byte-identical across machines.
    """
    if total <= 0:
        return None
    return (present * 2000 + total) // (total * 2)
