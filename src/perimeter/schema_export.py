"""A published contract for the two artifacts, and a descriptor that carries their terms.

``site/data/*.json`` are the product. The pages are one rendering of them, and a
downstream reader — the sibling project, a researcher, a reporter — has had no contract
for their shape except this repository's source. The three-state model is the whole point
of the measurement and it is invisible in the JSON: ``"EAVES": [222, 0, 0]`` means
nothing at all without :data:`perimeter.artifacts.FIELD_STATE_ORDER`, and nothing in the
artifact said so.

Two documents fix that, and both are built by the same run that builds the pages:

* **JSON Schema** (draft 2020-12) per artifact, under ``site/data/schema/``. Every object
  closes with ``additionalProperties: false`` and lists every key it publishes as
  ``required``, which is what makes the schema a gate in both directions rather than a
  description. A key the writer starts emitting fails validation as an unexpected
  property; a key the schema starts demanding that the writer does not emit fails as a
  missing one. :mod:`tests.test_artifact_schemas` runs both directions against a fixture
  build and against the committed real artifacts.
* **A Frictionless Data Package** at ``site/data/datapackage.json``, describing both
  resources with the licence, the endpoint, the retrieval date and the SHA-256 of the
  file each was measured from. Those facts come from :mod:`perimeter.sources`, the single
  reviewed provenance record, so the descriptor cannot state a hash the artifacts do not.

Why the schemas are declared here rather than derived from the dataclasses: the payloads
are not dataclasses. :func:`perimeter.artifacts.perimeters_payload` and
:func:`~perimeter.artifacts.dins_payload` assemble dictionaries by hand, adding derived
keys (``total``, ``present_tenths_pct``), renaming others (``outside_domain`` becomes
``outside_published_domain``) and dropping some conditionally. A generator over
``FieldCoverage`` would describe the dataclass and not the artifact, which is the wrong
document. So the shape is written out, and held to the writer by validation in both
directions rather than by being computed from it. What that leaves uncovered is exactly
one case — a key the schema marks *optional* that the writer never emits — and
``test_every_optional_key_is_one_the_writer_can_omit`` names those two keys explicitly.

A fixture build writes a fixture descriptor: ``is_fixture`` true, and the acquisition
facts null rather than the real file's. Fixture output must never pass itself off as a
measurement of CAL FIRE's files, and a descriptor is the most quotable place that could
happen.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from perimeter.artifacts import ARTIFACT_SCHEMA_VERSION, FIELD_STATE_ORDER
from perimeter.sources import DINS, FRAP, Source

SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

SCHEMA_BASE_URL = "https://chelseakr.github.io/perimeter/data/schema"
"""Where the published schemas are served. The ``$id`` a consumer resolves against."""

_STATE_MEANING = (
    "The three counts are in the order published as `field_state_order`: "
    f"{FIELD_STATE_ORDER[0]} is a recorded value, {FIELD_STATE_ORDER[1]} is a value the "
    f"publisher records to mean it could not be determined, and {FIELD_STATE_ORDER[2]} "
    "is an empty cell. A recorded unknown is neither present nor missing, and folding it "
    "into either one is the error this project exists to refuse."
)


def _integer(description: str, *, nullable: bool = False) -> dict[str, Any]:
    return {
        "type": ["integer", "null"] if nullable else "integer",
        "description": description,
    }


def _string(description: str, *, nullable: bool = False) -> dict[str, Any]:
    return {
        "type": ["string", "null"] if nullable else "string",
        "description": description,
    }


def _counts(description: str) -> dict[str, Any]:
    """An object of name to count. Keys are values found in the data, so they are open."""
    return {
        "type": "object",
        "description": description,
        "additionalProperties": {"type": "integer"},
    }


def _object(description: str, properties: dict[str, Any]) -> dict[str, Any]:
    """A closed object requiring every property it declares.

    Closed and fully required is what makes the schema fail in both directions. Every
    optional key in these artifacts is declared by name in :func:`_field_schema`.
    """
    return {
        "type": "object",
        "description": description,
        "properties": properties,
        "required": sorted(properties),
        "additionalProperties": False,
    }


def _tenths_pct(what: str) -> dict[str, Any]:
    return _integer(
        f"{what}, in tenths of a percent, as an integer. Null where the denominator is "
        "zero: no share is published over an empty population.",
        nullable=True,
    )


def _source_schema() -> dict[str, Any]:
    return _object(
        "Provenance for the file this artifact measures, from the reviewed record in "
        "`perimeter.sources`. In a fixture build every acquisition fact is null.",
        {
            "key": _string("Stable identifier for the source."),
            "title": _string("The publisher's title for the dataset."),
            "publisher": _string("The agency that publishes it."),
            "landing_page": _string("The dataset's landing page."),
            "endpoint": _string("The service endpoint the rows were queried from."),
            "layer": _string("The layer within that service."),
            "licence": _string("The licence the publisher states."),
            "licence_url": _string("URL for that licence."),
            "version": _string(
                "The publisher's version string, or null in a fixture build.",
                nullable=True,
            ),
            "retrieved": _string(
                "ISO date the file was downloaded, or null in a fixture build.",
                nullable=True,
            ),
            "data_tier": _string("This project's governance tier for the source."),
            "refresh_cadence": _string(
                "When this project re-pulls the source, in words."
            ),
            "staleness_sla_days": _integer(
                "How long a retrieval is taken to describe the published file. This "
                "project's declaration, not a commitment by the publisher. Nothing here "
                "computes staleness: the artifacts carry no clock, so a consumer "
                "subtracts `retrieved` from its own."
            ),
            "data_card": _string(
                "Path to the data card for this source in the repository."
            ),
            "acquired_record_count": _integer(
                "Rows in the downloaded file, or null in a fixture build.",
                nullable=True,
            ),
            "acquired_bytes": _integer(
                "Size of the downloaded file, or null in a fixture build.",
                nullable=True,
            ),
            "acquired_sha256": _string(
                "SHA-256 of the downloaded file, or null in a fixture build.",
                nullable=True,
            ),
            "caveats": {
                "type": "array",
                "description": (
                    "The publisher's own statements about where the data is incomplete, "
                    "quoted, each with the measurement built from it."
                ),
                "items": _object(
                    "One published limitation and the measurement that answers it.",
                    {
                        "topic": _string("Short topic label."),
                        "quote": _string("The publisher's words, verbatim."),
                        "measured_as": _string("What this project counts in response."),
                    },
                ),
            },
        },
    )


def _field_schema() -> dict[str, Any]:
    """One measured field. The only object here with optional keys.

    ``recorded_zero_values`` is written only for a field declared numeric, and ``note``
    only for a field whose registry entry carries one. Both are therefore absent from
    ``required``, and both are named in the test that holds the optional set closed.
    """
    schema = _object(
        f"Completeness of one measured field. {_STATE_MEANING}",
        {
            "name": _string("Column name as the publisher spells it."),
            "label": _string("Human-readable label from the field registry."),
            "present": _integer(
                f"Cells carrying a recorded value ({FIELD_STATE_ORDER[0]})."
            ),
            "explicit_unknown": _integer(
                f"Cells carrying a published marker meaning the value could not be "
                f"determined ({FIELD_STATE_ORDER[1]})."
            ),
            "not_recorded": _integer(f"Empty cells ({FIELD_STATE_ORDER[2]})."),
            "total": _integer(
                "The three counts summed. The denominator for this field."
            ),
            "present_tenths_pct": _tenths_pct(
                "Share of cells carrying a recorded value"
            ),
            "markers": _counts(
                "Which recorded-unknown marker was found, and how often. Keys are the "
                "publisher's spellings, which differ between eras of the same file."
            ),
            "outside_published_domain": _integer(
                "Recorded values that are not in the publisher's coded-value domain for "
                "this field. Null, never zero, where the layer publishes no domain: "
                "nothing was counted against a domain that does not exist, and a zero "
                "would say the file and the domain agree.",
                nullable=True,
            ),
            "outside_published_domain_distinct": _integer(
                "How many distinct such values were found. Null with no published domain.",
                nullable=True,
            ),
            "outside_published_domain_values": {
                "type": ["object", "null"],
                "description": (
                    "Up to `OUTSIDE_DOMAIN_VALUE_CAP` of those values with their counts. "
                    "Compare `outside_published_domain_values_listed` against "
                    "`outside_published_domain_distinct` before reading this as the whole "
                    "set. Null with no published domain."
                ),
                "additionalProperties": {"type": "integer"},
            },
            "outside_published_domain_values_listed": _integer(
                "How many of the distinct values the object above actually names.",
                nullable=True,
            ),
            "marker_basis": {
                "type": "string",
                "description": (
                    "Whether the recorded-unknown markers for this field are the "
                    "publisher's own (`published`) or this project's reading of the data "
                    "(`inferred`). See docs/MARKERS.md."
                ),
            },
            "recorded_zero_values": _integer(
                "Cells recording a literal zero, for a field measured as a number. A "
                "zero is a judgment call (ADR 0006) and is published separately rather "
                "than folded into either presence or absence. Absent for a field that is "
                "not numeric."
            ),
            "note": _string(
                "The field registry's note on this field. Absent where the registry "
                "carries none."
            ),
        },
    )
    optional = {"recorded_zero_values", "note"}
    schema["required"] = sorted(set(schema["required"]) - optional)
    return schema


def _signal_schema() -> dict[str, Any]:
    return _object(
        "One duplicate-candidate signal: records sharing an identifier or an identifying "
        "combination. Candidates, not findings; this project does not decide that two "
        "records are the same fire.",
        {
            "key": _string("Identifier for the signal."),
            "description": _string("What was keyed on, in words."),
            "keyed_records": _integer("Records carrying a value for that key."),
            "distinct_keys": _integer("Distinct key values among them."),
            "reused_keys": _integer("Key values carried by more than one record."),
            "records_sharing_a_key": _integer("Records carrying a reused key value."),
        },
    )


def _access_schema() -> dict[str, Any]:
    return _object(
        "The assessed / inaccessible split, and the population in neither (ADR 0007).",
        {
            "assessed": _integer(
                "Records the damage field places in the assessed population."
            ),
            "inaccessible": _integer(
                "Records the damage field records as inaccessible."
            ),
            "damage_not_recorded": _integer("Records with an empty damage cell."),
            "damage_explicit_unknown": _integer(
                "Records whose damage cell carries a recorded-unknown marker."
            ),
            "total": _integer("All records in this population."),
        },
    )


def _envelope(properties: dict[str, Any], *, measurement: str) -> dict[str, Any]:
    """The keys both artifacts share, plus this artifact's own."""
    shared = {
        "is_fixture": {
            "type": "boolean",
            "description": (
                "True when this artifact was built from the committed sample fixtures "
                "rather than the publisher's file. A fixture build publishes no "
                "acquisition facts and its counts describe ten records."
            ),
        },
        "artifact_schema_version": {
            "type": "integer",
            "const": ARTIFACT_SCHEMA_VERSION,
            "description": (
                "The version of this contract. Bumped when a consumer validating against "
                "the previous schema would reject the new artifact or would read an "
                "existing key as meaning something else."
            ),
        },
        "measurement": _string("What this artifact measures, in one sentence."),
        "source": _source_schema(),
        "records": _integer("Records measured."),
    }
    return {**shared, **properties}


def perimeters_schema() -> dict[str, Any]:
    """The contract for ``perimeters-coverage.json``."""
    schema = _object(
        "Completeness of the FRAP historical fire perimeter record, measured as counts "
        "of cells in three named states. Nothing is estimated, nothing is interpolated "
        "across a gap, and no share is published over an empty denominator.",
        _envelope(
            {
                "earliest_year": _integer(
                    "Earliest fire year carried by any record, or null if none carries one.",
                    nullable=True,
                ),
                "latest_year": _integer(
                    "Latest fire year carried by any record, or null if none carries one.",
                    nullable=True,
                ),
                "records_without_year": _integer(
                    "Records carrying no fire year at all."
                ),
                "irwin_id_present": _integer("Records carrying an IRWIN identifier."),
                "irwin_id_present_tenths_pct": _tenths_pct(
                    "Share carrying an IRWIN identifier"
                ),
                "fields": {
                    "type": "array",
                    "description": "Every measured field, in registry order.",
                    "items": _field_schema(),
                },
                "years": {
                    "type": "array",
                    "description": (
                        "One row per fire year, plus one row for the records carrying no "
                        "year. Years are not interpolated and no year is invented for a "
                        "record that carries none."
                    ),
                    "items": _object(
                        "One fire year, or the cohort of records carrying no year.",
                        {
                            "year": _integer(
                                "The fire year, or null for the no-year cohort.",
                                nullable=True,
                            ),
                            "records": _integer("Records in this cohort."),
                            "irwin_present": _integer(
                                "Of those, carrying an IRWIN identifier."
                            ),
                            "irwin_explicit_unknown": _integer(
                                "Carrying a recorded-unknown marker in that field."
                            ),
                            "irwin_not_recorded": _integer("With that cell empty."),
                            "irwin_present_tenths_pct": _tenths_pct(
                                "Share of this cohort carrying an IRWIN identifier"
                            ),
                        },
                    ),
                },
                "duplicate_signals": {
                    "type": "array",
                    "description": "Duplicate candidates, keyed several ways.",
                    "items": _signal_schema(),
                },
                "marker_counterfactuals": {
                    "type": "array",
                    "description": (
                        "The same keying run against a value this project does not treat "
                        "as a marker, so a reader can see what the marker choice bought."
                    ),
                    "items": _signal_schema(),
                },
                "acre_thresholds": _object(
                    "Records per decade counted against the acreages FRAP's published "
                    "current collection criteria name. Not the criteria of every earlier "
                    "era, and a record below a threshold is not an error.",
                    {
                        "thresholds": {
                            "type": "array",
                            "description": "The acreages counted against.",
                            "items": {"type": "integer"},
                        },
                        "note": _string("What these counts are and are not."),
                        "by_decade": {
                            "type": "array",
                            "description": "One row per decade, plus the no-year cohort.",
                            "items": _object(
                                "One decade of surviving records.",
                                {
                                    "decade": _integer(
                                        "First year of the decade, or null for records "
                                        "carrying no year.",
                                        nullable=True,
                                    ),
                                    "records": _integer("Records in this decade."),
                                    "acres_recorded": _integer(
                                        "Of those, carrying a recorded acreage. The "
                                        "denominator for the counts below."
                                    ),
                                    "below": _counts(
                                        "Threshold acreage to the count of records below "
                                        "it. Keys are the thresholds as strings."
                                    ),
                                },
                            ),
                        },
                    },
                ),
            },
            measurement="perimeters",
        ),
    )
    schema["$schema"] = SCHEMA_DIALECT
    schema["$id"] = f"{SCHEMA_BASE_URL}/perimeters-coverage.schema.json"
    schema["title"] = "Perimeter: FRAP fire perimeter completeness"
    schema["field_state_order"] = list(FIELD_STATE_ORDER)
    return schema


def dins_schema() -> dict[str, Any]:
    """The contract for ``dins-coverage.json``."""
    incident_fields = {
        "type": "object",
        "description": (
            "Field name to a three-element array of counts within this incident, in "
            f"`field_state_order`. {_STATE_MEANING}"
        ),
        "additionalProperties": {
            "type": "array",
            "items": {"type": "integer"},
            "minItems": len(FIELD_STATE_ORDER),
            "maxItems": len(FIELD_STATE_ORDER),
        },
    }
    schema = _object(
        "Coverage of the CAL FIRE DINS damage inspection record, measured as counts of "
        "cells in three named states, for the whole file, per access population, and per "
        "incident.",
        _envelope(
            {
                "incidents": _integer("Distinct incidents the records group into."),
                "records_not_attributable_to_an_incident": _integer(
                    "Records carrying no part of an incident key, so nothing places them "
                    "in an incident. Published rather than dropped."
                ),
                "access": _access_schema(),
                "damage_values": _counts(
                    "The damage field's recorded values and their counts, as the "
                    "publisher spells them."
                ),
                "damage_values_tenths_pct": {
                    "type": "object",
                    "description": (
                        "The same values as a share of all records, in tenths of a "
                        "percent. Null where the denominator is zero."
                    ),
                    "additionalProperties": {"type": ["integer", "null"]},
                },
                "fields": {
                    "type": "array",
                    "description": "Every measured field, in registry order.",
                    "items": _field_schema(),
                },
                "field_state_order": {
                    "type": "array",
                    "description": (
                        "What the three counts in every compact triple mean, in order. "
                        f"{_STATE_MEANING}"
                    ),
                    "items": {"type": "string"},
                },
                "completeness_by_access": {
                    "type": "array",
                    "description": (
                        "Each field's completeness split by access population, each "
                        "column over its own denominator. The third population is "
                        "published rather than left out (ADR 0007)."
                    ),
                    "items": _object(
                        "One field, split three ways by access.",
                        {
                            "name": _string("Column name as the publisher spells it."),
                            "label": _string("Human-readable label."),
                            "assessed_present": _integer(
                                "Recorded, among assessed records."
                            ),
                            "assessed_total": _integer(
                                "Assessed records. Its own denominator."
                            ),
                            "assessed_tenths_pct": _tenths_pct(
                                "Share recorded among assessed"
                            ),
                            "inaccessible_present": _integer(
                                "Recorded, among records the publisher marks inaccessible."
                            ),
                            "inaccessible_total": _integer("Inaccessible records."),
                            "inaccessible_tenths_pct": _tenths_pct(
                                "Share recorded among inaccessible"
                            ),
                            "undetermined_present": _integer(
                                "Recorded, among the records neither population holds."
                            ),
                            "undetermined_total": _integer(
                                "Records in neither population."
                            ),
                            "undetermined_tenths_pct": _tenths_pct(
                                "Share recorded among the records in neither population"
                            ),
                        },
                    ),
                },
                "incidents_detail": {
                    "type": "array",
                    "description": (
                        "One row per incident. Any part of an incident key may be absent, "
                        "and absence is part of the key: records naming the same fire but "
                        "differing in whether a number was recorded stay apart, because "
                        "merging them would assume they are the same incident."
                    ),
                    "items": _object(
                        "One incident's records and per-field completeness.",
                        {
                            "incident_name": _string(
                                "Incident name, or null where none was recorded.",
                                nullable=True,
                            ),
                            "incident_number": _string(
                                "Incident number, or null where none was recorded.",
                                nullable=True,
                            ),
                            "start_year": _integer(
                                "Incident start year, or null where none was recorded.",
                                nullable=True,
                            ),
                            "records": _integer("Records in this incident."),
                            "access": _access_schema(),
                            "damage_values": _counts(
                                "The damage field's recorded values within this incident."
                            ),
                            "fields": incident_fields,
                        },
                    ),
                },
            },
            measurement="dins",
        ),
    )
    schema["$schema"] = SCHEMA_DIALECT
    schema["$id"] = f"{SCHEMA_BASE_URL}/dins-coverage.schema.json"
    schema["title"] = "Perimeter: CAL FIRE DINS damage inspection coverage"
    schema["field_state_order"] = list(FIELD_STATE_ORDER)
    return schema


SCHEMAS = {
    "perimeters-coverage.schema.json": perimeters_schema,
    "dins-coverage.schema.json": dins_schema,
}


def _resource(
    source: Source,
    *,
    artifact: str,
    schema_file: str,
    title: str,
    description: str,
    is_fixture: bool,
) -> dict[str, Any]:
    """One Frictionless resource: the artifact, its schema, and what it measured.

    ``sources``, ``licenses`` and ``hash`` describe the *input* the artifact measures,
    which is the fact a consumer needs and the one this repository reviews. A fixture
    build states no hash, no version and no retrieval date, because a fixture was never
    downloaded from anywhere.
    """
    return {
        "name": source.key,
        "path": artifact,
        "type": "table",
        "format": "json",
        "mediatype": "application/json",
        "title": title,
        "description": description,
        "profile": "data-resource",
        "jsonSchema": f"schema/{schema_file}",
        "licenses": [
            {
                "name": "CC-BY-4.0",
                "title": source.licence,
                "path": source.licence_url,
            }
        ],
        "sources": [
            {
                "title": source.title,
                "path": source.landing_page,
                "endpoint": source.endpoint,
                "layer": source.layer,
                "publisher": source.publisher,
                "version": None if is_fixture else source.version,
                "retrieved": None if is_fixture else source.retrieved,
                "hash": None if is_fixture else f"sha256:{source.sha256}",
                "bytes": None if is_fixture else source.raw_bytes,
                "recordCount": None if is_fixture else source.record_count,
                "dataTier": source.tier,
                "refreshCadence": source.refresh_cadence,
                "stalenessSlaDays": source.staleness_sla_days,
            }
        ],
    }


def datapackage(*, is_fixture: bool) -> dict[str, Any]:
    """The Frictionless descriptor for both artifacts."""
    return {
        "profile": "data-package",
        "name": "perimeter-coverage",
        "title": "Perimeter: coverage of two California wildfire datasets",
        "description": (
            "Counts of cells in three named states across CAL FIRE's historical fire "
            "perimeter record and its damage inspection record. Unofficial. Both "
            "publishers state in their own words that these files are incomplete; this "
            "measures how, in counts, with no estimation and no share over an empty "
            "denominator."
        ),
        "homepage": "https://chelseakr.github.io/perimeter/",
        "isFixture": is_fixture,
        "artifactSchemaVersion": ARTIFACT_SCHEMA_VERSION,
        "fieldStateOrder": list(FIELD_STATE_ORDER),
        "fieldStateMeaning": _STATE_MEANING,
        "licenses": [
            {
                "name": "CC-BY-4.0",
                "title": "Creative Commons Attribution",
                "path": "http://www.opendefinition.org/licenses/cc-by",
            }
        ],
        "resources": [
            _resource(
                FRAP,
                artifact="perimeters-coverage.json",
                schema_file="perimeters-coverage.schema.json",
                title="FRAP fire perimeter completeness",
                description=(
                    "Per-field, per-year and per-decade counts over the FRAP historical "
                    "fire perimeter record."
                ),
                is_fixture=is_fixture,
            ),
            _resource(
                DINS,
                artifact="dins-coverage.json",
                schema_file="dins-coverage.schema.json",
                title="CAL FIRE DINS damage inspection coverage",
                description=(
                    "Per-field, per-access-population and per-incident counts over the "
                    "CAL FIRE damage inspection record."
                ),
                is_fixture=is_fixture,
            ),
        ],
    }


def write(out_dir: Path, *, is_fixture: bool) -> list[Path]:
    """Write both schemas and the data package beside the artifacts.

    Same bytes for the same inputs, like everything else this build writes: keys sorted,
    two-space indent, trailing newline, and no wall clock anywhere.
    """
    written: list[Path] = []
    schema_dir = out_dir / "schema"
    schema_dir.mkdir(parents=True, exist_ok=True)
    for name, build_schema in sorted(SCHEMAS.items()):
        path = schema_dir / name
        path.write_text(
            json.dumps(build_schema(), indent=2, sort_keys=True, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        written.append(path)
    descriptor = out_dir / "datapackage.json"
    descriptor.write_text(
        json.dumps(
            datapackage(is_fixture=is_fixture),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    written.append(descriptor)
    return written
