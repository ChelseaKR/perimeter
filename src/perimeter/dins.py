"""DINS damage inspections: read the records, then count what the inspections recorded.

CAL FIRE states the rule this module is built around in the dataset's own description:
"Attributes with null values could not be determined." A blank DINS cell is therefore a
fact about the inspection, not a fact about the structure, and the two must not be
reported as the same thing.

The schema draws one more line that matters more than any other for reading a null here.
A record exists because an inspection identified a structure. Within that, ``DAMAGE`` may
say ``Inaccessible``, which CAL FIRE publishes as its own damage value: the structure was
identified but could not be reached. A construction attribute left blank on an
inaccessible record means something different from the same blank on a record the
inspector walked up to. This module keeps those two populations apart so the coverage
pages can report them apart.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from perimeter.cells import Cell, CellState
from perimeter.records import Record, load_rows, parse_records
from perimeter.schema import (
    DINS_FIELDS,
    DINS_INACCESSIBLE,
    DINS_REQUIRED_COLUMNS,
    SchemaDriftError,
)

SOURCE = "CAL FIRE DINS (POSTFIRE)"


def parse_inspections(rows: Sequence[dict[str, object]]) -> list[Record]:
    return parse_records(
        rows,
        specs=DINS_FIELDS,
        required=DINS_REQUIRED_COLUMNS,
        id_field="OBJECTID",
        source=SOURCE,
    )


def load_inspections(path: Path) -> list[Record]:
    return parse_inspections(load_rows(path))


def _epoch_year(cell: Cell, *, where: str) -> int | None:
    """The calendar year of a published timestamp, or ``None`` if none was recorded.

    The layer publishes dates as milliseconds since the epoch in UTC, and the year is
    read in UTC. No local timezone is applied anywhere, so the same file yields the same
    year on every machine that builds these artifacts.
    """
    if not cell.is_present:
        return None
    text = cell.value()
    try:
        millis = int(float(text))
    except ValueError:
        raise SchemaDriftError(
            f"{where}.INCIDENTSTARTDATE: {text!r} is not a timestamp"
        ) from None
    return datetime.fromtimestamp(millis / 1000, tz=UTC).year


def _present(record: Record, field: str) -> str | None:
    cell = record.cell(field)
    return cell.value() if cell.is_present else None


@dataclass(frozen=True, order=True)
class IncidentKey:
    """What names an incident. Any part may be absent, and absence is part of the key.

    Two records are grouped only when every part they carry matches. Records naming the
    same fire but differing in whether an incident number was recorded stay apart, since
    merging them would require assuming they are the same incident.
    """

    name: str | None
    number: str | None
    start_year: int | None

    @property
    def is_empty(self) -> bool:
        return self.name is None and self.number is None and self.start_year is None


def incident_key(record: Record) -> IncidentKey:
    name = _present(record, "INCIDENTNAME")
    return IncidentKey(
        name=None if name is None else name.strip().upper(),
        number=_present(record, "INCIDENTNUM"),
        start_year=_epoch_year(
            record.cell("INCIDENTSTARTDATE"),
            where=f"{SOURCE}[OBJECTID={record.identifier}]",
        ),
    )


def is_inaccessible(record: Record) -> bool:
    """True when CAL FIRE recorded that this structure could not be reached."""
    cell = record.cell("DAMAGE")
    return cell.is_present and cell.value() == DINS_INACCESSIBLE


def is_assessed(record: Record) -> bool:
    """True when a damage value other than Inaccessible was recorded."""
    cell = record.cell("DAMAGE")
    return cell.is_present and cell.value() != DINS_INACCESSIBLE


@dataclass(frozen=True)
class AccessSplit:
    """The three populations a blank construction attribute can belong to."""

    assessed: int
    inaccessible: int
    damage_not_recorded: int
    damage_explicit_unknown: int

    @property
    def total(self) -> int:
        return (
            self.assessed
            + self.inaccessible
            + self.damage_not_recorded
            + self.damage_explicit_unknown
        )


def access_split(records: Sequence[Record]) -> AccessSplit:
    """Split records by what the damage field says about the inspection itself."""
    assessed = inaccessible = not_recorded = unknown = 0
    for record in records:
        cell = record.cell("DAMAGE")
        if cell.state is CellState.NOT_RECORDED:
            not_recorded += 1
        elif cell.state is CellState.EXPLICIT_UNKNOWN:
            unknown += 1
        elif cell.value() == DINS_INACCESSIBLE:
            inaccessible += 1
        else:
            assessed += 1
    return AccessSplit(
        assessed=assessed,
        inaccessible=inaccessible,
        damage_not_recorded=not_recorded,
        damage_explicit_unknown=unknown,
    )


def damage_distribution(records: Sequence[Record]) -> dict[str, int]:
    """Counts per recorded damage value, plus the two non-value states.

    "No Damage" appears here as its own recorded finding. It is not merged with the blank
    cells and it is not a zero: an inspector looked at the structure and wrote down that
    it was undamaged.
    """
    counts: Counter[str] = Counter()
    for record in records:
        cell = record.cell("DAMAGE")
        if cell.state is CellState.PRESENT:
            counts[cell.value()] += 1
        else:
            counts[cell.state.value] += 1
    return dict(sorted(counts.items()))


def group_by_incident(
    records: Sequence[Record],
) -> tuple[list[tuple[IncidentKey, list[Record]]], list[Record]]:
    """Group records by incident, returning the groups and the unattributable records.

    A record carrying no incident name, no incident number and no start date cannot be
    attributed to an incident. It is returned separately and counted, never dropped and
    never folded into an arbitrary group.
    """
    buckets: dict[IncidentKey, list[Record]] = defaultdict(list)
    unattributed: list[Record] = []
    for record in records:
        key = incident_key(record)
        if key.is_empty:
            unattributed.append(record)
        else:
            buckets[key].append(record)
    ordered = sorted(
        buckets.items(),
        key=lambda item: (
            item[0].start_year is None,
            item[0].start_year or 0,
            item[0].name or "",
            item[0].number or "",
        ),
    )
    return ordered, unattributed
