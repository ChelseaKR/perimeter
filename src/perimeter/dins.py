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
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from perimeter.cells import Cell, CellState
from perimeter.records import Record, load_rows, parse_records
from perimeter.schema import (
    DINS_FIELDS,
    DINS_FIELDS_BY_NAME,
    DINS_INACCESSIBLE,
    DINS_REQUIRED_COLUMNS,
    SchemaDriftError,
)

SOURCE = "CAL FIRE DINS (POSTFIRE)"

OUTSIDE_PUBLISHED_DOMAIN = "outside_published_domain"
"""The one cohort a recorded value the publisher's domain does not describe lands in.

Named rather than spelled out per cut, because it is the same fact wherever it appears
and because a reader comparing it against `outside_published_domain` on the field row
should be reading one word, not two spellings of one word.
"""


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


@dataclass(frozen=True, order=True)
class CohortKey:
    """Which cohort a record belongs to in one cut of the file, and why.

    A cut groups records by a published column, and the column can say three things.
    ``value`` is the recorded one. The other two are the absences, kept apart from each
    other and from every recorded value, because "the inspection recorded no county" and
    "the inspection recorded a marker in place of a county" are different facts and
    neither is a county.

    ``sort`` puts recorded values first in their own order and both absences after them,
    so a table never opens on the rows that carry no value.
    """

    sort: tuple[int, float, str]
    label: str
    value: str | None

    @property
    def is_recorded(self) -> bool:
        return self.value is not None


def _recorded(value: str, *, numeric: float | None = None) -> CohortKey:
    return CohortKey(
        sort=(0, numeric if numeric is not None else 0.0, value),
        label=value,
        value=value,
    )


def _absent(label: str, *, last: bool) -> CohortKey:
    return CohortKey(sort=(2 if last else 1, 0.0, label), label=label, value=None)


def year_cohort_key(record: Record) -> CohortKey:
    """Which incident-start year a record belongs to.

    The layer publishes the date as milliseconds since the epoch and the year is read in
    UTC, exactly as :func:`_epoch_year` reads it, so a cut by year and a per-incident
    start year cannot disagree about the same record.
    """
    cell = record.cell("INCIDENTSTARTDATE")
    if cell.state is CellState.EXPLICIT_UNKNOWN:
        return _absent("Start date recorded as unknown", last=False)
    if not cell.is_present:
        return _absent("No incident start date recorded", last=True)
    year = _epoch_year(cell, where=f"{SOURCE}[OBJECTID={record.identifier}]")
    if year is None:  # pragma: no cover - unreachable: the cell was shown present above
        return _absent("No incident start date recorded", last=True)
    return _recorded(str(year), numeric=float(year))


def _text_cohort_key(
    record: Record, field: str, *, unknown_label: str, absent_label: str
) -> CohortKey:
    cell = record.cell(field)
    if cell.state is CellState.EXPLICIT_UNKNOWN:
        return _absent(unknown_label, last=False)
    if not cell.is_present:
        return _absent(absent_label, last=True)
    return _recorded(cell.value())


def county_cohort_key(record: Record) -> CohortKey:
    """Which published county a record belongs to.

    The layer publishes no coded-value domain for ``COUNTY``, so every recorded spelling
    is its own cohort and nothing here decides that two spellings name one county.
    """
    return _text_cohort_key(
        record,
        "COUNTY",
        unknown_label="County recorded as unknown",
        absent_label="No county recorded",
    )


def structure_category_cohort_key(record: Record) -> CohortKey:
    """Which published structure category a record belongs to.

    ``STRUCTURECATEGORY`` is one of the fields the layer does publish a coded-value
    domain for. A recorded value outside that domain is counted, never dropped and never
    given a row of its own: it goes to one ``outside_published_domain`` cohort, because
    giving it a row would publish a category CAL FIRE does not define as though this
    project had found one (ADR 0002).
    """
    cell = record.cell("STRUCTURECATEGORY")
    if cell.state is CellState.EXPLICIT_UNKNOWN:
        return _absent("Structure category recorded as unknown", last=False)
    if not cell.is_present:
        return _absent("No structure category recorded", last=True)
    spec = DINS_FIELDS_BY_NAME["STRUCTURECATEGORY"]
    if spec.outside_domain(cell):
        return CohortKey(
            sort=(1, 0.0, OUTSIDE_PUBLISHED_DOMAIN),
            label=OUTSIDE_PUBLISHED_DOMAIN,
            value=OUTSIDE_PUBLISHED_DOMAIN,
        )
    return _recorded(cell.value())


def group_by_cohort(
    records: Sequence[Record], key: Callable[[Record], CohortKey]
) -> list[tuple[CohortKey, list[Record]]]:
    """Partition records into cohorts, in cohort order.

    Every record lands in exactly one cohort, so the cuts sum back to the file. An empty
    cohort is not published: nothing was measured there, and a row of zeros would read as
    a finding about a county with no records rather than as a county the file never
    names.
    """
    buckets: dict[CohortKey, list[Record]] = defaultdict(list)
    for record in records:
        buckets[key(record)].append(record)
    return sorted(buckets.items(), key=lambda item: item[0].sort)


NOT_APPLICABLE_FIELD = "UTILITYMISCSTRUCTUREDISTANCE"
"""The field whose Not Applicable value the file spells two ways.

``docs/MARKERS.md`` section 2 records the call: CAL FIRE's published domain for this
field lists ``NA``, the file also carries ``N/A``, and both are counted as the published
finding rather than one being read as missing data. The evidence for that call is an era
claim, that the two spellings fall on opposite sides of one year, and until now it was a
sentence somebody had measured once and typed in. :func:`recorded_absence_spellings`
per year is that sentence as a published count.
"""


def recorded_absence_spellings(records: Sequence[Record], field: str) -> dict[str, int]:
    """How often each declared recorded-absence spelling of one field was written.

    Only the spellings the field registry declares, and only in cells that are present.
    A recorded absence is a finding rather than a blank, so it is counted here among
    values and never among the empty cells.
    """
    spec = DINS_FIELDS_BY_NAME[field]
    counts: Counter[str] = Counter()
    for record in records:
        cell = record.cell(field)
        if cell.is_present and cell.value() in spec.recorded_absences:
            counts[cell.value()] += 1
    return dict(sorted(counts.items()))
