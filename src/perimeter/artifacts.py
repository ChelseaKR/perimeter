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

from perimeter.coverage import (
    DinsReport,
    FieldCoverage,
    PerimeterReport,
    dins_report,
    perimeter_report,
)
from perimeter.dins import AccessSplit, load_inspections
from perimeter.perimeters import COLLECTION_ACRE_THRESHOLDS, load_perimeters
from perimeter.sources import DINS, FRAP, Source

FIELD_STATE_ORDER = ("present", "explicit_unknown", "not_recorded")
"""The order of the three counts in every compact per-incident field triple."""


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
        "outside_published_domain": field.outside_domain,
        "outside_published_domain_distinct": field.outside_domain_distinct,
        "outside_published_domain_values": field.outside_domain_values,
    }
    if field.zero_values is not None:
        payload["recorded_zero_values"] = field.zero_values
    if field.note:
        payload["note"] = field.note
    return payload


def _access_json(access: AccessSplit) -> dict[str, Any]:
    return {
        "assessed": access.assessed,
        "inaccessible": access.inaccessible,
        "damage_not_recorded": access.damage_not_recorded,
        "damage_explicit_unknown": access.damage_explicit_unknown,
        "total": access.total,
    }


def perimeters_payload(report: PerimeterReport, *, is_fixture: bool) -> dict[str, Any]:
    return {
        "is_fixture": is_fixture,
        "measurement": "Completeness of the FRAP historical fire perimeter record",
        "source": _source_json(FRAP, is_fixture=is_fixture),
        "records": report.records,
        "earliest_year": report.earliest_year,
        "latest_year": report.latest_year,
        "records_without_year": report.records_without_year,
        "irwin_id_present": report.irwin_present,
        "fields": [_field_json(field) for field in report.fields],
        "years": [
            {
                "year": cohort.year,
                "records": cohort.records,
                "irwin_present": cohort.irwin_present,
                "irwin_explicit_unknown": cohort.irwin_explicit_unknown,
                "irwin_not_recorded": cohort.irwin_not_recorded,
            }
            for cohort in report.years
        ],
        "duplicate_signals": [
            {
                "key": signal.key,
                "description": signal.description,
                "keyed_records": signal.keyed_records,
                "distinct_keys": signal.distinct_keys,
                "reused_keys": signal.reused_keys,
                "records_sharing_a_key": signal.records_sharing_a_key,
            }
            for signal in report.duplicates
        ],
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
        "measurement": "Coverage of the CAL FIRE DINS damage inspection record",
        "source": _source_json(DINS, is_fixture=is_fixture),
        "records": report.records,
        "incidents": report.incidents,
        "records_not_attributable_to_an_incident": report.unattributed_records,
        "access": _access_json(report.access),
        "damage_values": report.damage,
        "fields": [_field_json(field) for field in report.fields],
        "field_state_order": list(FIELD_STATE_ORDER),
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
