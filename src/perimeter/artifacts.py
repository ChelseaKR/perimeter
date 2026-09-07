"""Write the two coverage measurements as JSON that is the same bytes every time.

Determinism is a requirement here rather than a nicety. These numbers are meant to be
cited, compared between releases, and checked by somebody who re-runs the build. So: keys
sorted, records in a defined order, integer arithmetic for every published share, and no
wall clock anywhere in the payload. The retrieval date comes from the reviewed constants
in :mod:`perimeter.sources`, not from the machine running the build.

A build from committed fixtures stamps ``is_fixture: true``. Fixture output must never be
able to pass itself off as a measurement of CAL FIRE's real files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from perimeter.cells import present_tenths_of_percent
from perimeter.coverage import (
    CohortCoverage,
    DinsReport,
    FieldCoverage,
    PerimeterReport,
    dins_report,
    perimeter_report,
)
from perimeter.dins import NOT_APPLICABLE_FIELD, AccessSplit, load_inspections
from perimeter.perimeters import (
    COLLECTION_ACRE_THRESHOLDS,
    DuplicateSignal,
    load_perimeters,
)
from perimeter.sources import DINS, FRAP, Source

FIELD_STATE_ORDER = ("present", "explicit_unknown", "not_recorded")
"""The order of the three counts in every compact per-incident field triple."""

ARTIFACT_SCHEMA_VERSION = 1
"""The version of the published artifact contract, carried in every artifact.

Bump it when a consumer validating against the previous schema in ``site/data/schema/``
would reject the new artifact, or would read an existing key as meaning something else:
a key removed, a key renamed, a type widened or narrowed, or the meaning of a value
changed. Adding an *optional* key does not require a bump; adding a required one does,
because ``additionalProperties: false`` in the previous schema rejects it either way.

``CHANGELOG.md`` states the same rule for a reader, and
``test_the_changelog_states_the_rule_for_bumping_the_schema_version`` holds the two
together so the rule cannot be edited in one place only.

It lives here rather than in :mod:`perimeter.schema_export` because the writer is what
declares the contract's version; the schema module reads it. Putting it there instead
would make :mod:`perimeter.artifacts` import the module that describes it.
"""


def _source_json(source: Source, *, is_fixture: bool) -> dict[str, Any]:
    """Provenance for one source. A fixture build publishes no acquisition facts.

    A fixture was never downloaded from CAL FIRE, so its record count, byte count, hash
    and retrieval date are all null rather than the real file's values. Absence is
    published as absence.
    """
    return {
        "key": source.key,
        "title": source.title,
        "publisher": source.publisher,
        "landing_page": source.landing_page,
        "endpoint": source.endpoint,
        "layer": source.layer,
        "licence": source.licence,
        "licence_url": source.licence_url,
        "version": None if is_fixture else source.version,
        "retrieved": None if is_fixture else source.retrieved,
        # Policy rather than acquisition, so a fixture build publishes it too. A consumer
        # holding the retrieval date and the SLA can decide for itself whether what it is
        # reading is current; nothing here computes that, because computing it needs a
        # clock and these artifacts have none.
        "data_tier": source.tier,
        "refresh_cadence": source.refresh_cadence,
        "staleness_sla_days": source.staleness_sla_days,
        "data_card": source.card,
        "acquired_record_count": None if is_fixture else source.record_count,
        "acquired_bytes": None if is_fixture else source.raw_bytes,
        "acquired_sha256": None if is_fixture else source.sha256,
        "caveats": [
            {
                "topic": caveat.topic,
                "quote": caveat.quote,
                "measured_as": caveat.measured_as,
            }
            for caveat in source.caveats
        ],
    }


def _field_json(field: FieldCoverage) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": field.name,
        "label": field.label,
        "present": field.present,
        "explicit_unknown": field.explicit_unknown,
        "not_recorded": field.not_recorded,
        "total": field.total,
        "present_tenths_pct": field.present_tenths_pct,
        "markers": field.markers,
        # Null, not zero, for a field the layer publishes no coded-value domain for.
        # Nothing was counted against a domain that does not exist, and a zero here would
        # say the file and the domain agree. `outside_published_domain_values_listed` is
        # how many of `_distinct` the values object actually names, so a list capped at
        # OUTSIDE_DOMAIN_VALUE_CAP cannot be read as the whole set.
        "outside_published_domain": field.outside_domain,
        "outside_published_domain_distinct": field.outside_domain_distinct,
        "outside_published_domain_values": field.outside_domain_values,
        "outside_published_domain_values_listed": field.outside_domain_values_listed,
        "marker_basis": field.basis.value,
    }
    if field.zero_values is not None:
        payload["recorded_zero_values"] = field.zero_values
    if field.note:
        payload["note"] = field.note
    return payload


def _signal_json(signal: DuplicateSignal) -> dict[str, Any]:
    return {
        "key": signal.key,
        "description": signal.description,
        "keyed_records": signal.keyed_records,
        "distinct_keys": signal.distinct_keys,
        "reused_keys": signal.reused_keys,
        "records_sharing_a_key": signal.records_sharing_a_key,
    }


def _access_json(access: AccessSplit) -> dict[str, Any]:
    return {
        "assessed": access.assessed,
        "inaccessible": access.inaccessible,
        "damage_not_recorded": access.damage_not_recorded,
        "damage_explicit_unknown": access.damage_explicit_unknown,
        "total": access.total,
    }


def _cohort_json(cohort: CohortCoverage) -> dict[str, Any]:
    """One cohort of one cut, in the compact per-field shape `incidents_detail` uses.

    ``value`` is the recorded value this cohort is, and it is ``null`` for the cohorts
    that are absences: a record whose county cell is empty, and a record whose county
    cell carries a marker, are two different cohorts and neither of them is a county.
    ``label`` is what a page prints. Reading ``value`` rather than ``label`` is how a
    consumer tells a measured cohort from an absence without parsing English.
    """
    return {
        "value": cohort.value,
        "label": cohort.label,
        "records": cohort.records,
        "access": _access_json(cohort.access),
        "fields": {
            field.name: [field.present, field.explicit_unknown, field.not_recorded]
            for field in cohort.fields
        },
        "fields_by_access": {
            row.name: {
                "assessed": [row.assessed_present, row.assessed_total],
                "inaccessible": [row.inaccessible_present, row.inaccessible_total],
                "undetermined": [row.undetermined_present, row.undetermined_total],
            }
            for row in cohort.by_access
        },
    }


def perimeters_payload(report: PerimeterReport, *, is_fixture: bool) -> dict[str, Any]:
    return {
        "is_fixture": is_fixture,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "measurement": "Completeness of the FRAP historical fire perimeter record",
        "source": _source_json(FRAP, is_fixture=is_fixture),
        "records": report.records,
        "earliest_year": report.earliest_year,
        "latest_year": report.latest_year,
        "records_without_year": report.records_without_year,
        "irwin_id_present": report.irwin_present,
        "fields": [_field_json(field) for field in report.fields],
        "irwin_id_present_tenths_pct": present_tenths_of_percent(
            report.irwin_present, report.records
        ),
        "years": [
            {
                "year": cohort.year,
                "records": cohort.records,
                "irwin_present": cohort.irwin_present,
                "irwin_explicit_unknown": cohort.irwin_explicit_unknown,
                "irwin_not_recorded": cohort.irwin_not_recorded,
                "irwin_present_tenths_pct": present_tenths_of_percent(
                    cohort.irwin_present, cohort.records
                ),
            }
            for cohort in report.years
        ],
        "duplicate_signals": [_signal_json(signal) for signal in report.duplicates],
        "marker_counterfactuals": [_signal_json(report.placeholder_counterfactual)],
        "acre_thresholds": {
            "thresholds": list(COLLECTION_ACRE_THRESHOLDS),
            "note": (
                "Counts of surviving records below each acreage named in FRAP's "
                "published current collection criteria. These are not the criteria that "
                "applied in every earlier era, and a record below a threshold is not an "
                "error; the count is here so a reader can see how close each decade's "
                "records sit to the cutoffs FRAP names."
            ),
            "by_decade": [
                {
                    "decade": cohort.decade,
                    "records": cohort.records,
                    "acres_recorded": cohort.acres_recorded,
                    "below": {str(k): v for k, v in sorted(cohort.below.items())},
                }
                for cohort in report.thresholds
            ],
        },
    }


def dins_payload(report: DinsReport, *, is_fixture: bool) -> dict[str, Any]:
    return {
        "is_fixture": is_fixture,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "measurement": "Coverage of the CAL FIRE DINS damage inspection record",
        "source": _source_json(DINS, is_fixture=is_fixture),
        "records": report.records,
        "incidents": report.incidents,
        "records_not_attributable_to_an_incident": report.unattributed_records,
        "access": _access_json(report.access),
        "damage_values": report.damage,
        "damage_values_tenths_pct": {
            value: present_tenths_of_percent(count, report.records)
            for value, count in report.damage.items()
        },
        "fields": [_field_json(field) for field in report.fields],
        "field_state_order": list(FIELD_STATE_ORDER),
        # Three cuts of the same records. Each is a partition of the file, so summing a
        # cut per field and per state returns the file totals; nothing is estimated and
        # no cohort is compared against another.
        "completeness_by_year": [_cohort_json(cohort) for cohort in report.by_year],
        "completeness_by_county": [_cohort_json(cohort) for cohort in report.by_county],
        "completeness_by_structure_category": [
            _cohort_json(cohort) for cohort in report.by_structure_category
        ],
        # The era claim docs/MARKERS.md rests a marker decision on, as counts rather
        # than as a sentence somebody measured once and typed in.
        "not_applicable_spellings_by_year": {
            "field": NOT_APPLICABLE_FIELD,
            "note": (
                "How often each declared spelling of this field's Not Applicable value "
                "was written, per incident-start year. Both spellings are counted as the "
                "publisher's finding rather than one being read as missing data; "
                "docs/MARKERS.md section 2 sets out the evidence and the confidence."
            ),
            "by_year": [
                {
                    "value": cohort.key.value,
                    "label": cohort.label,
                    "records": cohort.records,
                    "spellings": dict(cohort.spellings),
                }
                for cohort in report.not_applicable_spellings
            ],
        },
        "completeness_by_access": [
            {
                "name": row.name,
                "label": row.label,
                "assessed_present": row.assessed_present,
                "assessed_total": row.assessed_total,
                "assessed_tenths_pct": row.assessed_tenths_pct,
                "inaccessible_present": row.inaccessible_present,
                "inaccessible_total": row.inaccessible_total,
                "inaccessible_tenths_pct": row.inaccessible_tenths_pct,
                "undetermined_present": row.undetermined_present,
                "undetermined_total": row.undetermined_total,
                "undetermined_tenths_pct": row.undetermined_tenths_pct,
            }
            for row in report.by_access
        ],
        "incidents_detail": [
            {
                "incident_name": incident.key.name,
                "incident_number": incident.key.number,
                "start_year": incident.key.start_year,
                "records": incident.records,
                "access": _access_json(incident.access),
                "damage_values": incident.damage,
                "fields": {
                    field.name: [
                        field.present,
                        field.explicit_unknown,
                        field.not_recorded,
                    ]
                    for field in incident.fields
                },
            }
            for incident in report.incident_rows
        ],
    }


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    return path


def build(
    *,
    perimeters_source: Path,
    dins_source: Path,
    out_dir: Path,
    is_fixture: bool,
) -> tuple[PerimeterReport, DinsReport]:
    """Measure both sources and write both JSON artifacts."""
    perimeters = perimeter_report(load_perimeters(perimeters_source))
    inspections = dins_report(load_inspections(dins_source))
    write_json(
        out_dir / "perimeters-coverage.json",
        perimeters_payload(perimeters, is_fixture=is_fixture),
    )
    write_json(
        out_dir / "dins-coverage.json", dins_payload(inspections, is_fixture=is_fixture)
    )
    return perimeters, inspections
