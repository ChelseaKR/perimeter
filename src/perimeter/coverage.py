"""Coverage as the output, not as a footnote under one.

Every measurement in this module is a count of records in a named state. Nothing is
estimated, nothing is interpolated across a gap, and no rate is published over an empty
denominator. Where a share would have to be invented, the share is absent.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from perimeter.cells import CellState, present_tenths_of_percent
from perimeter.dins import (
    AccessSplit,
    IncidentKey,
    access_split,
    damage_distribution,
    group_by_incident,
    is_assessed,
    is_inaccessible,
)
from perimeter.perimeters import (
    DuplicateSignal,
    ThresholdCohort,
    YearCohort,
    duplicate_signals,
    placeholder_counterfactual,
    threshold_cohorts,
    year_cohorts,
)
from perimeter.records import Record
from perimeter.schema import DINS_FIELDS, FRAP_FIELDS, Basis, FieldSpec

OUTSIDE_DOMAIN_VALUE_CAP = 12
"""How many out-of-domain values to name per field.

The full count is always published, and so is how many of them this list holds:
``outside_domain_distinct`` is the number found and ``outside_domain_values_listed`` is
the number named. A reader comparing the two can see that the list stops short, rather
than reading a truncated list as the whole set.
"""


@dataclass(frozen=True)
class FieldCoverage:
    """One field's three states, plus what the values themselves look like.

    The four out-of-domain measures are ``None`` together, for one reason: the layer
    publishes no coded-value domain for that field, so there is nothing for a value to be
    outside of and nothing was counted. That is not the same fact as a field whose domain
    is published and whose every value is inside it, which counts zero. Thirty of the
    fifty-four fields measured here are free text, and reporting them as ``0`` said the
    file and the domain agree about a domain that does not exist.
    """

    name: str
    label: str
    note: str
    basis: Basis
    present: int
    explicit_unknown: int
    not_recorded: int
    markers: dict[str, int]
    outside_domain: int | None
    outside_domain_distinct: int | None
    outside_domain_values: dict[str, int] | None
    outside_domain_values_listed: int | None
    zero_values: int | None

    @property
    def total(self) -> int:
        return self.present + self.explicit_unknown + self.not_recorded

    @property
    def present_tenths_pct(self) -> int | None:
        return present_tenths_of_percent(self.present, self.total)


def field_coverage(records: Sequence[Record], spec: FieldSpec) -> FieldCoverage:
    """Count one field across a set of records."""
    states: Counter[str] = Counter()
    markers: Counter[str] = Counter()
    outside: Counter[str] = Counter()
    zeros = 0
    for record in records:
        cell = record.cell(spec.name)
        states[cell.state.value] += 1
        if cell.state is CellState.EXPLICIT_UNKNOWN:
            marker = cell.marker
            if marker is not None:
                markers[marker] += 1
            continue
        if cell.state is not CellState.PRESENT:
            continue
        value = cell.value()
        if spec.outside_domain(cell):
            outside[value] += 1
        if spec.numeric:
            try:
                if float(value) == 0:
                    zeros += 1
            except ValueError:  # pragma: no cover - numeric drift raises at read time
                pass
    named = sorted(outside.items(), key=lambda item: (-item[1], item[0]))
    listed = dict(named[:OUTSIDE_DOMAIN_VALUE_CAP])
    # A field the layer publishes no domain for was never compared against one. Its
    # out-of-domain measures are absent rather than zero: `spec.outside_domain` answers
    # False for every cell of such a field, so summing that answer produces a zero that
    # reads as a finding and is not one.
    has_domain = spec.domain_values is not None
    return FieldCoverage(
        name=spec.name,
        label=spec.label,
        note=spec.note,
        basis=spec.basis,
        present=states.get("present", 0),
        explicit_unknown=states.get("explicit_unknown", 0),
        not_recorded=states.get("not_recorded", 0),
        markers=dict(sorted(markers.items())),
        outside_domain=sum(outside.values()) if has_domain else None,
        outside_domain_distinct=len(outside) if has_domain else None,
        outside_domain_values=listed if has_domain else None,
        outside_domain_values_listed=len(listed) if has_domain else None,
        zero_values=zeros if spec.numeric else None,
    )


def field_coverages(
    records: Sequence[Record], specs: Sequence[FieldSpec]
) -> list[FieldCoverage]:
    return [field_coverage(records, spec) for spec in specs]


# --------------------------------------------------------------------------------------
# Page 1: FRAP historical fire perimeter completeness
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PerimeterReport:
    records: int
    fields: list[FieldCoverage]
    years: list[YearCohort]
    duplicates: list[DuplicateSignal]
    placeholder_counterfactual: DuplicateSignal
    thresholds: list[ThresholdCohort]

    @property
    def earliest_year(self) -> int | None:
        years = [cohort.year for cohort in self.years if cohort.year is not None]
        return min(years) if years else None

    @property
    def latest_year(self) -> int | None:
        years = [cohort.year for cohort in self.years if cohort.year is not None]
        return max(years) if years else None

    @property
    def records_without_year(self) -> int:
        return sum(cohort.records for cohort in self.years if cohort.year is None)

    @property
    def irwin_present(self) -> int:
        return sum(cohort.irwin_present for cohort in self.years)


def perimeter_report(records: Sequence[Record]) -> PerimeterReport:
    return PerimeterReport(
        records=len(records),
        fields=field_coverages(records, FRAP_FIELDS),
        years=year_cohorts(records),
        duplicates=duplicate_signals(records),
        placeholder_counterfactual=placeholder_counterfactual(records),
        thresholds=threshold_cohorts(records),
    )


# --------------------------------------------------------------------------------------
# Page 2: DINS damage inspection coverage
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AccessFieldCoverage:
    """One field counted three ways, so that every record is counted one of them.

    Two of the three are the measurement: a construction attribute missing on a
    structure the inspection could not reach is a different fact from the same attribute
    missing on a structure that was assessed, and that is the split this exists for.

    The third is the population neither of those describes. ``DAMAGE`` is what says
    whether a structure was reached, and a record whose ``DAMAGE`` is blank or holds a
    marker answers neither question. There is no such record in the acquired file today,
    and there was no such count either: the two denominators were built from the two
    populations that answer, so a record that answered nothing left the table without
    appearing anywhere in it, and a reader adding the columns up would have found fewer
    records than the file holds with nothing saying why. ``AccessSplit`` has always
    counted these records; this is the same discipline applied one level down, per field.
    """

    name: str
    label: str
    assessed_present: int
    assessed_total: int
    inaccessible_present: int
    inaccessible_total: int
    undetermined_present: int
    undetermined_total: int

    @property
    def assessed_tenths_pct(self) -> int | None:
        return present_tenths_of_percent(self.assessed_present, self.assessed_total)

    @property
    def inaccessible_tenths_pct(self) -> int | None:
        return present_tenths_of_percent(
            self.inaccessible_present, self.inaccessible_total
        )

    @property
    def undetermined_tenths_pct(self) -> int | None:
        return present_tenths_of_percent(
            self.undetermined_present, self.undetermined_total
        )

    @property
    def counted_records(self) -> int:
        """Every record the three populations account for between them."""
        return self.assessed_total + self.inaccessible_total + self.undetermined_total


@dataclass(frozen=True)
class IncidentCoverage:
    """One incident's records and how complete each measured field is inside it."""

    key: IncidentKey
    records: int
    access: AccessSplit
    damage: dict[str, int]
    fields: list[FieldCoverage]


@dataclass(frozen=True)
class DinsReport:
    records: int
    incidents: int
    unattributed_records: int
    fields: list[FieldCoverage]
    access: AccessSplit
    damage: dict[str, int]
    by_access: list[AccessFieldCoverage]
    incident_rows: list[IncidentCoverage]


def access_field_coverages(
    records: Sequence[Record], specs: Sequence[FieldSpec]
) -> list[AccessFieldCoverage]:
    assessed = [record for record in records if is_assessed(record)]
    blocked = [record for record in records if is_inaccessible(record)]
    # Everything the damage field does not place in either population. Derived by
    # subtraction from the records handed in rather than by a third predicate, so the
    # three populations partition the input by construction and a future damage state
    # cannot fall between them.
    undetermined = [
        record
        for record in records
        if not is_assessed(record) and not is_inaccessible(record)
    ]
    rows: list[AccessFieldCoverage] = []
    for spec in specs:
        rows.append(
            AccessFieldCoverage(
                name=spec.name,
                label=spec.label,
                assessed_present=sum(
                    1 for record in assessed if record.cell(spec.name).is_present
                ),
                assessed_total=len(assessed),
                inaccessible_present=sum(
                    1 for record in blocked if record.cell(spec.name).is_present
                ),
                inaccessible_total=len(blocked),
                undetermined_present=sum(
                    1 for record in undetermined if record.cell(spec.name).is_present
                ),
                undetermined_total=len(undetermined),
            )
        )
    return rows


def dins_report(records: Sequence[Record]) -> DinsReport:
    groups, unattributed = group_by_incident(records)
    return DinsReport(
        records=len(records),
        incidents=len(groups),
        unattributed_records=len(unattributed),
        fields=field_coverages(records, DINS_FIELDS),
        access=access_split(records),
        damage=damage_distribution(records),
        by_access=access_field_coverages(records, DINS_FIELDS),
        incident_rows=[
            IncidentCoverage(
                key=key,
                records=len(group),
                access=access_split(group),
                damage=damage_distribution(group),
                fields=field_coverages(group, DINS_FIELDS),
            )
            for key, group in groups
        ],
    )
