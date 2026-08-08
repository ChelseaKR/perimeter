"""FRAP historical fire perimeters: read the records, then count what is in them.

FRAP publishes its own limits in the dataset description, and this module measures
against exactly those sentences rather than against an outside expectation. Where FRAP
says records are missing because some "were too small for the minimum cutoffs", this
counts how many surviving records sit below each published cutoff, by decade. Where FRAP
says the known errors "include duplicate fires", this counts records that share an
identifier or an identifying combination. It does not decide that any pair of records is
in fact one fire: that is a judgment about geometry and history, and this project holds
no geometry and makes no such judgment.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from perimeter.records import Record, float_value, load_rows, parse_records
from perimeter.schema import (
    FRAP_FIELDS,
    FRAP_REQUIRED_COLUMNS,
    SchemaDriftError,
)

SOURCE = "FRAP California Fire Perimeters (all)"

COLLECTION_ACRE_THRESHOLDS: tuple[int, ...] = (10, 50, 300)
"""The acreages named in FRAP's published current collection criteria.

Ten acres is the floor all cooperating agencies submit against, and is also CAL FIRE's
timber threshold; fifty is CAL FIRE's brush threshold and three hundred its grass
threshold. FRAP states these as the *current* criteria and separately records that older
fires may be absent for having been "too small for the minimum cutoffs" of their own era.
This project therefore counts surviving records against the published numbers and does
not reconstruct what any earlier era's cutoff was.
"""


def parse_perimeters(rows: Sequence[dict[str, object]]) -> list[Record]:
    return parse_records(
        rows,
        specs=FRAP_FIELDS,
        required=FRAP_REQUIRED_COLUMNS,
        id_field="OBJECTID",
        source=SOURCE,
    )


def load_perimeters(path: Path) -> list[Record]:
    return parse_perimeters(load_rows(path))


def year_of(record: Record) -> int | None:
    """The fire year, or ``None`` when the record does not carry one."""
    cell = record.cell("YEAR_")
    if not cell.is_present:
        return None
    text = cell.value()
    try:
        return int(float(text))
    except ValueError:
        raise SchemaDriftError(
            f"{SOURCE}[OBJECTID={record.identifier}].YEAR_: {text!r} is not a year"
        ) from None


def acres_of(record: Record) -> float | None:
    return float_value(
        record.cell("GIS_ACRES"),
        field="GIS_ACRES",
        where=f"{SOURCE}[OBJECTID={record.identifier}]",
    )


def decade_of(record: Record) -> int | None:
    """The decade this project derives from the record's own year.

    FRAP also publishes a DECADES column, whose coverage is measured separately. Deriving
    the decade here keeps the decade grouping defined for every record that has a year,
    rather than silently dropping records whose DECADES cell is empty.
    """
    year = year_of(record)
    return None if year is None else (year // 10) * 10


@dataclass(frozen=True)
class YearCohort:
    """One fire year, or the cohort of records that carry no year at all."""

    year: int | None
    records: int
    irwin_present: int
    irwin_explicit_unknown: int
    irwin_not_recorded: int


def year_cohorts(records: Sequence[Record]) -> list[YearCohort]:
    """Records per year with IRWIN ID coverage inside each year.

    Records with no year are kept as their own cohort rather than being dropped or
    attached to a neighbouring year. A year that no record names is simply absent from
    this list; it is not published as a year with zero fires, because this dataset cannot
    tell the difference between a year with no fires and a year whose fires are missing.
    """
    buckets: dict[int | None, list[Record]] = defaultdict(list)
    for record in records:
        buckets[year_of(record)].append(record)
    cohorts: list[YearCohort] = []
    for year in sorted(buckets, key=lambda value: (value is None, value)):
        group = buckets[year]
        states = Counter(record.cell("IRWINID").state.value for record in group)
        cohorts.append(
            YearCohort(
                year=year,
                records=len(group),
                irwin_present=states.get("present", 0),
                irwin_explicit_unknown=states.get("explicit_unknown", 0),
                irwin_not_recorded=states.get("not_recorded", 0),
            )
        )
    return cohorts


@dataclass(frozen=True)
class DuplicateSignal:
    """How many records share a key that ought to name one fire."""

    key: str
    description: str
    keyed_records: int
    distinct_keys: int
    reused_keys: int
    records_sharing_a_key: int


def _signal(
    key: str, description: str, keys: Sequence[tuple[str, ...]]
) -> DuplicateSignal:
    counts = Counter(keys)
    return DuplicateSignal(
        key=key,
        description=description,
        keyed_records=len(keys),
        distinct_keys=len(counts),
        reused_keys=sum(1 for count in counts.values() if count > 1),
        records_sharing_a_key=sum(count for count in counts.values() if count > 1),
    )


def _present(record: Record, field: str) -> str | None:
    cell = record.cell(field)
    return cell.value() if cell.is_present else None


def duplicate_signals(records: Sequence[Record]) -> list[DuplicateSignal]:
    """Count records sharing an identifier or an identifying combination.

    Each signal only keys the records that carry every part of that key. A record missing
    one part is excluded from that signal's denominator and counted in ``keyed_records``,
    so a low duplicate count is never an artifact of missing values quietly padding the
    total.

    These are candidates. FRAP documents that duplicate fires exist in the database; what
    is counted here is how often the published identifiers repeat, which is a different
    and smaller statement than "these records are the same fire".
    """
    irwin = [
        (value,)
        for record in records
        if (value := _present(record, "IRWINID")) is not None
    ]
    local: list[tuple[str, ...]] = []
    named: list[tuple[str, ...]] = []
    for record in records:
        year = year_of(record)
        if year is None:
            continue
        unit = _present(record, "UNIT_ID")
        number = _present(record, "INC_NUM")
        if unit is not None and number is not None:
            local.append((str(year), unit, number))
        name = _present(record, "FIRE_NAME")
        acres = acres_of(record)
        if name is not None and acres is not None:
            named.append((str(year), name.upper(), f"{round(acres)}"))
    return [
        _signal(
            "irwin_id",
            "Records sharing one IRWIN ID. IRWIN is the federal incident identifier, "
            "so a repeat means two perimeter records point at one federal incident.",
            irwin,
        ),
        _signal(
            "year_unit_incident_number",
            "Records sharing a fire year, reporting unit and local incident number. "
            "Local incident numbers repeat between units by design, so the unit is part "
            "of the key; without it this count would be inflated by unrelated fires.",
            local,
        ),
        _signal(
            "year_name_acres",
            "Records sharing a fire year, fire name and GIS acreage rounded to the "
            "nearest acre.",
            named,
        ),
    ]


@dataclass(frozen=True)
class ThresholdCohort:
    """Surviving records in one decade, against FRAP's published acreage criteria."""

    decade: int | None
    records: int
    acres_recorded: int
    below: dict[int, int]


def threshold_cohorts(records: Sequence[Record]) -> list[ThresholdCohort]:
    """Per decade, how many records fall below each published collection threshold."""
    buckets: dict[int | None, list[Record]] = defaultdict(list)
    for record in records:
        buckets[decade_of(record)].append(record)
    cohorts: list[ThresholdCohort] = []
    for decade in sorted(buckets, key=lambda value: (value is None, value)):
        group = buckets[decade]
        acreages = [
            acres for record in group if (acres := acres_of(record)) is not None
        ]
        cohorts.append(
            ThresholdCohort(
                decade=decade,
                records=len(group),
                acres_recorded=len(acreages),
                below={
                    threshold: sum(1 for acres in acreages if acres < threshold)
                    for threshold in COLLECTION_ACRE_THRESHOLDS
                },
            )
        )
    return cohorts
