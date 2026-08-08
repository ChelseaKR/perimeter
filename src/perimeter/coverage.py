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
"""How many out-of-domain values to name per field. The full count is always published."""


@dataclass(frozen=True)
class FieldCoverage:
    """One field's three states, plus what the values themselves look like."""

    name: str
    label: str
    note: str
    basis: Basis
    present: int
    explicit_unknown: int
    not_recorded: int
    markers: dict[str, int]
    outside_domain: int
    outside_domain_distinct: int
    outside_domain_values: dict[str, int]
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
    return FieldCoverage(
        name=spec.name,
        label=spec.label,
        note=spec.note,
        basis=spec.basis,
        present=states.get("present", 0),
        explicit_unknown=states.get("explicit_unknown", 0),
        not_recorded=states.get("not_recorded", 0),
        markers=dict(sorted(markers.items())),
        outside_domain=sum(outside.values()),
        outside_domain_distinct=len(outside),
        outside_domain_values=dict(named[:OUTSIDE_DOMAIN_VALUE_CAP]),
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
    """One field counted twice: on assessed records, and on inaccessible ones.

    This is the measurement that separates "not inspected" from "inspected, field blank".
    A construction attribute missing on a structure the inspection could not reach is a
    different fact from the same attribute missing on a structure that was assessed.
    """

    name: str
    label: str
    assessed_present: int
    assessed_total: int
    inaccessible_present: int
    inaccessible_total: int

    @property
    def assessed_tenths_pct(self) -> int | None:
        return present_tenths_of_percent(self.assessed_present, self.assessed_total)

    @property
    def inaccessible_tenths_pct(self) -> int | None:
        return present_tenths_of_percent(
            self.inaccessible_present, self.inaccessible_total
        )


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
