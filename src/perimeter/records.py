"""Turn raw source rows into records whose every measured cell is already classified.

Parsing happens once, at the edge. After this module runs, nothing downstream sees a raw
string, so nothing downstream can decide for itself what an empty cell meant. A row that
cannot be classified stops here rather than reaching a page.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from perimeter.cells import Cell
from perimeter.schema import FieldSpec, SchemaDriftError, require_columns


@dataclass(frozen=True)
class Record:
    """One source row: its identifier and its measured cells, all pre-classified."""

    identifier: str
    cells: Mapping[str, Cell]

    def cell(self, name: str) -> Cell:
        try:
            return self.cells[name]
        except KeyError:  # pragma: no cover - guarded by require_columns at parse time
            raise SchemaDriftError(
                f"{self.identifier}: field {name!r} was never parsed for this record"
            ) from None


def load_rows(path: Path) -> list[dict[str, object]]:
    """Read a source file of attribute rows.

    The acquisition step writes a JSON array of attribute objects using the field names
    the layer publishes. Reading field names rather than the CSV export's column aliases
    means a renamed alias upstream cannot quietly shift which column a measurement is
    about.
    """
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise SchemaDriftError(
            f"{path.name}: expected a JSON array of attribute rows, got "
            f"{type(payload).__name__}"
        )
    rows: list[dict[str, object]] = []
    for index, row in enumerate(payload):
        if not isinstance(row, dict):
            raise SchemaDriftError(
                f"{path.name}: row {index} is {type(row).__name__}, not an object"
            )
        rows.append(row)
    return rows


def parse_records(
    rows: Sequence[Mapping[str, object]],
    *,
    specs: Sequence[FieldSpec],
    required: tuple[str, ...],
    id_field: str,
    source: str,
) -> list[Record]:
    """Classify every measured cell of every row, or refuse the file.

    An empty file is allowed through: zero records is a real state of a source and is
    reported as zero, not as an error and not as a silent success with invented numbers.
    """
    if not rows:
        return []
    columns = set(rows[0])
    # Every measured column is required, not only the identity columns. Without this a
    # column that vanished upstream would be classified as not-recorded for every record
    # and published as a field nobody filled in, which is a different claim entirely.
    require_columns(
        columns,
        (*required, *(spec.name for spec in specs)),
        source=source,
    )
    records: list[Record] = []
    for index, row in enumerate(rows):
        raw_id = row.get(id_field)
        identifier = "" if raw_id is None else str(raw_id).strip()
        if not identifier:
            raise SchemaDriftError(
                f"{source}: row {index} has no {id_field}; records are addressed by "
                "that identifier and an unidentified row cannot be counted honestly"
            )
        where = f"{source}[{id_field}={identifier}]"
        records.append(
            Record(
                identifier=identifier,
                cells={
                    spec.name: spec.classify(row.get(spec.name), where=where)
                    for spec in specs
                },
            )
        )
    return records


def integer_value(cell: Cell, *, field: str, where: str) -> int | None:
    """The recorded whole number, or ``None`` when nothing was recorded.

    ``None`` here means "no number to read", never zero. Callers that count must add
    nothing for a ``None``; callers that average must not treat it as a sample.
    """
    if not cell.is_present:
        return None
    text = cell.value()
    try:
        return int(float(text))
    except ValueError:
        raise SchemaDriftError(
            f"{where}.{field}: {text!r} is not a number; this field is measured as one"
        ) from None


def float_value(cell: Cell, *, field: str, where: str) -> float | None:
    """The recorded measure, or ``None`` when nothing was recorded."""
    if not cell.is_present:
        return None
    text = cell.value()
    try:
        return float(text)
    except ValueError:
        raise SchemaDriftError(
            f"{where}.{field}: {text!r} is not a number; this field is measured as one"
        ) from None
