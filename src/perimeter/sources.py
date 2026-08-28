"""What was downloaded, from where, under what licence, and what its publisher says about it.

This module is the single reviewed record of provenance. PROVENANCE.md restates it for
a reader and a test asserts the two agree, so the document cannot drift away from the
numbers the pages print.

The quotes below are CAL FIRE's and FRAP's own words, copied from the dataset
descriptions published on data.cnra.ca.gov and data.ca.gov on the retrieval date. They
are the reason this project exists: both agencies already state where their data is
incomplete, and nobody has published the per-year and per-incident counts that turn those
sentences into something a downstream user can plan against. Every measurement on the two
pages is tied back to one of these quotes.
"""

from __future__ import annotations

from dataclasses import dataclass

RETRIEVED = "2026-08-07"
"""The date both sources were downloaded. Mirrored in PROVENANCE.md and tested for sync."""


@dataclass(frozen=True)
class Caveat:
    """One published limitation, quoted, and the measurement built from it."""

    topic: str
    quote: str
    measured_as: str


@dataclass(frozen=True)
class Source:
    key: str
    title: str
    publisher: str
    landing_page: str
    endpoint: str
    layer: str
    licence: str
    licence_url: str
    version: str
    retrieved: str
    record_count: int
    raw_bytes: int
    sha256: str
    raw_file: str
    caveats: tuple[Caveat, ...]
    card: str
    """The data card for this source, under docs/data/."""

    tier: str
    """Data-governance tier. Both sources are L1: openly licensed public reference data."""

    refresh_cadence: str
    """When this project re-pulls the source, in words."""

    staleness_sla_days: int
    """How long a retrieval describes the published file, in days.

    This is this project's declaration, not a commitment by CAL FIRE or FRAP. Neither
    publisher promises a schedule, and neither is asked to: the number exists so that a
    retrieval going stale is a build failure here rather than a page quietly describing a
    file that has moved on. `tests/test_data_cards.py` is where it fires. It is not in
    the pages, because a page computing staleness would need a clock and the artifacts
    have none; what the artifacts publish is the retrieval date and this number, so any
    consumer can do the subtraction with their own clock and get the same answer.
    """


FRAP = Source(
    key="frap_perimeters",
    title="California Historical Fire Perimeters",
    publisher="California Department of Forestry and Fire Protection, Fire and Resource Assessment Program",
    landing_page="https://data.cnra.ca.gov/dataset/california-historical-fire-perimeters",
    endpoint=(
        "https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/"
        "California_Historic_Fire_Perimeters/FeatureServer/0/query"
    ),
    layer="California Fire Perimeters (all)",
    licence="Creative Commons Attribution",
    licence_url="http://www.opendefinition.org/licenses/cc-by",
    version="firep25_1",
    retrieved=RETRIEVED,
    record_count=23334,
    raw_bytes=7964688,
    sha256="9be7bcb9c08f6813ba13263eabebc96256f0ea8fb0e809ad8a4171046466a16a",
    raw_file="frap_perimeters.json",
    card="docs/data/frap-perimeters.md",
    tier="L1",
    refresh_cadence="On each published FRAP version. The layer is released as a "
    "versioned annual product and the acquired file is firep25_1.",
    # One annual cycle plus about five weeks, so a retrieval does not go stale on the eve
    # of the version that would replace it.
    staleness_sla_days=400,
    caveats=(
        Caveat(
            topic="Completeness",
            quote=(
                "Although the dataset represents the most complete digital record of "
                "fire perimeters in California, it is still incomplete, and users "
                "should be cautious when drawing conclusions based on the data."
            ),
            measured_as="Records per fire year, published as counts of what is present, "
            "with no year interpolated and no year invented for a record that carries none.",
        ),
        Caveat(
            topic="Missing perimeters",
            quote=(
                "This data should be used carefully for statistical analysis and "
                "reporting due to missing perimeters (see Use Limitation in metadata). "
                "Some fires are missing because historical records were lost or damaged, "
                "were too small for the minimum cutoffs, had inadequate documentation or "
                "have not yet been incorporated into the database."
            ),
            measured_as="Records per decade counted against each acreage named in the "
            "published collection criteria, so a reader can see how much of each decade "
            "sits near the cutoffs.",
        ),
        Caveat(
            topic="Collection criteria",
            quote=(
                "CAL FIRE (including contract counties) submit perimeters ≥10 acres "
                "in timber, ≥50 acres in brush, or ≥300 acres in grass, and/or "
                "≥3 impacted residential or commercial structures, and/or caused "
                "≥1 fatality. All cooperating agencies submit perimeters ≥10 acres."
            ),
            measured_as="The 10, 50 and 300 acre thresholds are the ones counted against, "
            "and they are labelled as the current criteria rather than applied backwards "
            "to eras whose cutoffs this project has not established.",
        ),
        Caveat(
            topic="Duplicates and generalization",
            quote=(
                "Other errors with the fire perimeter database include duplicate fires "
                "and over-generalization. Additionally, over-generalization, particularly "
                "with large old fires, may show unburned “islands” within the "
                "final perimeter as burned."
            ),
            measured_as="Counts of records sharing an identifier or an identifying "
            "combination, published as candidates. Over-generalization is a property of "
            "the polygons, which this project does not download and does not assess.",
        ),
        Caveat(
            topic="IRWIN linkage",
            quote=(
                "A new field, Global ID, was added to provide a unique ID to track all "
                "fire records in this dataset including those pre-dating IRWIN IDs."
            ),
            measured_as="IRWIN ID coverage per year, which shows where the federal "
            "identifier begins to appear and how much of each recent year carries one.",
        ),
        Caveat(
            topic="Null to Unknown",
            quote=(
                "A count of 12,097 fires' collection methods were edited from Null values "
                "to Unknown."
            ),
            measured_as="Collection method counted in three states rather than two, so "
            "the cells this edit moved are visible as recorded unknowns instead of "
            "disappearing into an apparently complete field.",
        ),
    ),
)

DINS = Source(
    key="dins_postfire",
    title="CAL FIRE Damage Inspection (DINS) Data",
    publisher="California Department of Forestry and Fire Protection",
    landing_page="https://data.ca.gov/dataset/cal-fire-damage-inspection-dins-data",
    endpoint=(
        "https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/"
        "POSTFIRE_MASTER_DATA_SHARE/FeatureServer/0/query"
    ),
    layer="POSTFIRE",
    licence="Creative Commons Attribution",
    licence_url="http://www.opendefinition.org/licenses/cc-by",
    version="POSTFIRE_MASTER_DATA_SHARE",
    retrieved=RETRIEVED,
    record_count=132522,
    raw_bytes=163728068,
    sha256="7683850bec00c201ad05ae55ab3c70baf53acd298a1da2fe8fd3c5432a624761",
    raw_file="dins_postfire.json",
    card="docs/data/dins.md",
    tier="L1",
    refresh_cadence="After each fire season. The layer carries no version string and is "
    "appended to as inspections complete, so there is no release to wait for.",
    # About one fire season. After that the file has grown by incidents this measurement
    # does not describe, and the record count on the page is a count of an older file.
    staleness_sla_days=180,
    caveats=(
        Caveat(
            topic="Nulls",
            quote=(
                "Information such as structure type, construction features, and "
                "defensive actions are determined as best as possible. Attributes with "
                "null values could not be determined."
            ),
            measured_as="Every measured field counted in three states: a recorded value, "
            "a recorded marker meaning it could not be determined, and an empty cell. "
            "A null is never rendered as a value and never as a zero.",
        ),
        Caveat(
            topic="Inspection limits",
            quote=(
                "Fire damage and poor access are major limiting factors for damage "
                "inspectors. All inspections are conducted using a systematic inspection "
                "process, however not all structures impacted by the fire may be "
                "identified due to these factors. Therefore, a small margin of error is "
                "expected."
            ),
            measured_as="Field completeness reported separately for records assessed on "
            "site and records CAL FIRE recorded as Inaccessible, so a blank on a "
            "structure that could not be reached is not counted as the same fact as a "
            "blank on one that was.",
        ),
        Caveat(
            topic="Two address sources",
            quote=(
                "Two address fields are included in the database. The street number, "
                "street name, and street type fields are “field determined.” The "
                "inspector inputs this information based on what they see in the field. "
                "The Address (parcel) and APN (parcel) fields are added through a spatial "
                "join after data collection is complete."
            ),
            measured_as="The field-determined address columns and the parcel-join columns "
            "are counted separately, because their blanks are produced by two different "
            "processes and mean two different things.",
        ),
        Caveat(
            topic="Scope",
            quote=(
                "This database is used to document all structures impacted by wildland "
                "fire within the Statewide Responsibility Area (SRA) that are inside or "
                "within 300 feet of the fire perimeter."
            ),
            measured_as="Records and incidents counted as published, with no inference "
            "about structures outside that scope. A structure absent from this file is "
            "not published here as an undamaged structure.",
        ),
    ),
)

SOURCES: tuple[Source, ...] = (FRAP, DINS)
