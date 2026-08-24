"""The reviewed field registry: what each column may hold, and what stops the build.

Every declaration here carries the basis it rests on, because some of them rest on
different ground and a reader cannot tell which from the value alone.

* :attr:`Basis.PUBLISHED` means the marker or finding is a code in the layer's own
  coded-value domain (the ``domain`` block the ArcGIS GeoService returns for that field)
  or is stated in the publisher's prose. ``CAUSE = 14`` and DINS ``No Damage`` are of
  this kind, and the domain can be re-read at the endpoint in ``PROVENANCE.md``.
* :attr:`Basis.INFERRED` means no published domain or sentence documents the value, and
  the declaration was read off the distribution of the acquired file itself. FRAP's
  ``INC_NUM`` is free text with no domain at all, so treating its all-zeros value as a
  placeholder is an inference, however well the counts support it.

Fifteen of the twenty-seven fields that declare any vocabulary are inferred. That is not
a defect in either dataset: both publishers document their domains for the fields they
constrain and say plainly which fields are free text. It is a fact about this project's
judgment calls, and it is published rather than hidden, on the pages and in
``docs/MARKERS.md``, which records the evidence, the source URL and the effect on the
published figures for every entry below.

Two rules, both fail-closed:

* A column this project reads going missing is upstream drift, not a reason to skip a
  measurement. :class:`SchemaDriftError`.
* A cell holding something that reads like a missing-data marker, in a field that has
  not declared that exact marker, is drift too. :class:`~perimeter.cells.SentinelDriftError`.

A third case is deliberately *not* an error: an ordinary value outside the published
domain. That is a real thing to count and publish, so coverage reports it as
``outside_published_domain`` rather than crashing on it or silently accepting it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from perimeter.cells import (
    SUSPECTED_SENTINELS,
    Cell,
    SentinelDriftError,
    normalize_marker,
)


class SchemaDriftError(ValueError):
    """The source no longer carries a column this project measures."""


class Basis(Enum):
    """Where a field's declared vocabulary came from.

    This is the difference between "the publisher says so" and "the file looks like it".
    Both are legitimate grounds for a measurement; publishing them as the same thing is
    not, because a reader deciding whether to rely on a count needs to know which one
    they are being handed.
    """

    NONE = "none"
    """The field declares no marker, code or finding of absence, so nothing to justify."""

    PUBLISHED = "published"
    """Every declared value is in the layer's coded-value domain or the publisher's prose."""

    INFERRED = "inferred"
    """At least one declared value was read off the acquired file's own distribution."""


@dataclass(frozen=True)
class FieldSpec:
    """One measured column and the vocabulary this project has reviewed for it."""

    name: str
    label: str
    unknown_codes: frozenset[str] = frozenset()
    """Exact published domain codes meaning "could not be determined".

    FRAP's ``CAUSE = 14`` is "Unknown / Unidentified" and ``C_METHOD = 8`` is "Unknown".
    Those are values somebody entered, so they are explicit-unknown rather than blank.
    """

    unknown_markers: frozenset[str] = frozenset()
    """Reviewed text markers, matched on their normalized form.

    Several fields carry a marker word where a value would go: ``CITY`` holds the literal
    text ``NA`` in a large share of DINS records, and FRAP holds fires named ``N/A``.
    Each marker is listed here per field after being read in that field's context,
    because the same word means different things in different columns: ``None`` is a
    published street-type value and is a real finding, while ``None`` in a parcel APN is
    a marker standing in for an absent parcel match. Matching on the normalized form
    folds casing and stray whitespace (``Unknown``, ``unknown``, ``Unknown ``) together
    so one reviewed entry covers the spelling variants of one marker.
    """

    recorded_absences: frozenset[str] = frozenset()
    """Exact published values recording that the feature is absent or does not apply.

    "No Eaves" is an eaves observation. "Not Applicable" for propane-tank distance is an
    inspector's finding. These are present values and are never folded into nulls.
    """

    domain_values: frozenset[str] | None = None
    """The published coded-value domain, or ``None`` where the field is free text."""

    numeric: bool = False
    """Counts and measures, where a recorded zero is a value and a blank is not."""

    basis: Basis = Basis.NONE
    """Where this field's declared vocabulary came from. See :class:`Basis`.

    A field declaring nothing is :attr:`Basis.NONE`. A field whose every declared value
    appears in the published domain is :attr:`Basis.PUBLISHED`. One carrying even a
    single value the publisher does not document is :attr:`Basis.INFERRED`, and says so
    on the page, because the weakest declaration sets what a reader can rely on.
    """

    note: str = ""

    @property
    def declares_vocabulary(self) -> bool:
        """True when this field makes any judgment call that needs a basis."""
        return bool(
            self.unknown_codes or self.unknown_markers or self.recorded_absences
        )

    def classify(self, raw: object, *, where: str) -> Cell:
        """Sort one cell into present, explicit-unknown, or not-recorded.

        Order matters. A published domain value is checked before the marker net, so a
        field that legitimately publishes ``None`` or ``N/A`` as a finding keeps it as a
        finding. Anything left that still reads as a missing-data marker stops the build.
        """
        if raw is None:
            return Cell.not_recorded()
        text = str(raw).strip()
        if text == "":
            return Cell.not_recorded()
        if text in self.unknown_codes:
            return Cell.explicit_unknown(text)
        if text in self.recorded_absences:
            return Cell.present(text)
        marker = normalize_marker(text)
        if marker in self.unknown_markers:
            return Cell.explicit_unknown(marker)
        if marker in SUSPECTED_SENTINELS:
            raise SentinelDriftError(
                f"{where}.{self.name}: cell {text!r} reads as a missing-data marker but "
                f"is not one this project has reviewed for this field "
                f"(reviewed markers: {sorted(self.unknown_markers | self.unknown_codes)}; "
                f"published absences: {sorted(self.recorded_absences)}); "
                "guessing here would publish an absence as a value"
            )
        return Cell.present(text)

    def outside_domain(self, cell: Cell) -> bool:
        """True when a present value is not in the reviewed published domain."""
        if self.domain_values is None or not cell.is_present:
            return False
        return cell.value() not in self.domain_values


def require_columns(
    present: set[str], required: tuple[str, ...], *, source: str
) -> None:
    """Refuse to measure a source that has lost a column this project reads."""
    missing = [name for name in required if name not in present]
    if missing:
        raise SchemaDriftError(
            f"{source} is missing required columns {missing}; the upstream layout "
            "changed and must be re-verified before any coverage number is published"
        )


# --------------------------------------------------------------------------------------
# FRAP California Historical Fire Perimeters, layer "California Fire Perimeters (all)"
# --------------------------------------------------------------------------------------

FRAP_CAUSE_CODES: dict[str, str] = {
    "1": "Lightning",
    "2": "Equipment Use",
    "3": "Smoking",
    "4": "Campfire",
    "5": "Debris",
    "6": "Railroad",
    "7": "Arson",
    "8": "Playing with Fire",
    "9": "Miscellaneous",
    "10": "Vehicle",
    "11": "Electrical Power",
    "12": "Firefighter Training",
    "13": "Non-Firefighter Training",
    "14": "Unknown / Unidentified",
    "15": "Structure",
    "16": "Aircraft",
    "17": "Volcanic",
    "18": "Escaped Prescribed Burn",
    "19": "Illegal Alien Campfire",
}
"""CAUSE domain as published by the layer. Code 14 is the documented unknown."""

FRAP_COLLECTION_METHOD_CODES: dict[str, str] = {
    "1": "GPS Ground",
    "2": "GPS Air",
    "3": "Infrared",
    "4": "Other Imagery",
    "5": "Photo Interpretation",
    "6": "Hand Drawn",
    "7": "Mixed Collection Methods",
    "8": "Unknown",
}
"""C_METHOD domain as published by the layer. Code 8 is the documented unknown."""

FRAP_OBJECTIVE_CODES: dict[str, str] = {
    "1": "Suppression (Wildfire)",
    "2": "Resource Benefit (WFU)",
}

FRAP_AGENCY_CODES: dict[str, str] = {
    "BIA": "USDI Bureau of Indian Affairs",
    "BLM": "Bureau of Land Management",
    "CCO": "Contract County",
    "CDF": "California Department of Forestry and Fire Protection",
    "DOD": "Department of Defense",
    "FWS": "USDI Fish and Wildlife Service",
    "LRA": "Local Response Area",
    "NOP": "No Protection",
    "NPS": "National Park Service",
    "OTH": "Other",
    "PVT": "Private",
    "USF": "USDA Forest Service",
}

FRAP_REQUIRED_COLUMNS: tuple[str, ...] = (
    "OBJECTID",
    "YEAR_",
    "STATE",
    "AGENCY",
    "UNIT_ID",
    "FIRE_NAME",
    "INC_NUM",
    "IRWINID",
    "ALARM_DATE",
    "CONT_DATE",
    "CAUSE",
    "C_METHOD",
    "OBJECTIVE",
    "GIS_ACRES",
    "COMPLEX_NAME",
    "COMPLEX_ID",
    "FIRE_NUM",
    "DECADES",
)

FRAP_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "YEAR_",
        "Year",
        note="Fire year. Records with no year are counted in their own cohort and are "
        "never folded into a year that would then appear larger than it is.",
    ),
    FieldSpec(
        "IRWINID",
        "IRWIN ID",
        note="Linkage to the federal IRWIN incident record. FRAP's own release notes "
        "describe the new Global ID field as covering records 'pre-dating IRWIN IDs', "
        "so an absent IRWIN ID on an older record is expected rather than anomalous.",
    ),
    FieldSpec("ALARM_DATE", "Alarm date"),
    FieldSpec("CONT_DATE", "Containment date"),
    FieldSpec(
        "FIRE_NAME",
        "Fire name",
        unknown_markers=frozenset({"unknown", "none", "n/a"}),
        basis=Basis.INFERRED,
        note="A small number of records carry a marker word where the name goes. "
        "Counting those as names would put a fire called N/A on a map. FIRE_NAME is "
        "published as free text with no coded-value domain, so these three markers are "
        "read off the file rather than off a documented vocabulary.",
    ),
    FieldSpec(
        "INC_NUM",
        "Local incident number",
        unknown_markers=frozenset({"00000000"}),
        basis=Basis.INFERRED,
        note="An all-zeros incident number stands in a large share of records. INC_NUM "
        "is published as free text with no coded-value domain, so nothing documents "
        "00000000 as a placeholder and this reading is inferred from the file. The "
        "inference is what the distribution supports: the all-zeros value is shared by "
        "records spanning 64 reporting units, 115 distinct fire years and nine "
        "agencies, and it thins out as recorded numbers appear, from every record "
        "before 1940 to a single record in the 2020s. A local incident number names one "
        "incident within one unit, so reading it as an identifier would put dozens of "
        "unrelated fires in one unit and one year on a single incident.",
    ),
    FieldSpec(
        "FIRE_NUM",
        "Fire number (historical use)",
        unknown_markers=frozenset({"<null>", "00000000"}),
        basis=Basis.INFERRED,
        note="Carries the literal text <Null> in a few records, and an all-zeros "
        "placeholder in several thousand more. Both are markers written into the cell "
        "rather than empty cells, and both are counted apart from recorded numbers. "
        "FIRE_NUM has no published domain, so both readings are inferred. One record "
        "carries a bare 0 rather than the padded form and is counted as a recorded "
        "number; see docs/MARKERS.md, which leaves that single record alone rather "
        "than extending the inference to a shape the file uses once.",
    ),
    FieldSpec(
        "CAUSE",
        "Cause",
        unknown_codes=frozenset({"14"}),
        domain_values=frozenset(FRAP_CAUSE_CODES),
        basis=Basis.PUBLISHED,
        note="Code 14 is the published 'Unknown / Unidentified' value. It is a recorded "
        "determination that the cause is unknown, not an empty cell.",
    ),
    FieldSpec(
        "C_METHOD",
        "Collection method",
        unknown_codes=frozenset({"8"}),
        domain_values=frozenset(FRAP_COLLECTION_METHOD_CODES),
        basis=Basis.PUBLISHED,
        note="Code 8 is the published 'Unknown' value. FRAP's firep25_1 release notes "
        "record that 12,097 fires' collection methods were edited from null to Unknown, "
        "which moves cells between two of the three states this project counts.",
    ),
    FieldSpec(
        "OBJECTIVE",
        "Management objective",
        domain_values=frozenset(FRAP_OBJECTIVE_CODES),
    ),
    FieldSpec("AGENCY", "Reporting agency", domain_values=frozenset(FRAP_AGENCY_CODES)),
    FieldSpec("UNIT_ID", "Unit"),
    FieldSpec("STATE", "State", domain_values=frozenset({"CA", "NV", "OR", "AZ"})),
    FieldSpec(
        "GIS_ACRES",
        "GIS calculated acres",
        numeric=True,
        note="Derived from the stored polygon, so it is the one geometry-dependent "
        "field available without downloading geometry.",
    ),
    FieldSpec("COMPLEX_NAME", "Complex name"),
    FieldSpec(
        "COMPLEX_ID",
        "Complex ID",
        unknown_markers=frozenset({"00000000"}),
        basis=Basis.INFERRED,
        note="One record carries the all-zeros form. The field has no published domain "
        "and mixes short alphanumeric codes, braced GUIDs and zero-padded numbers, so "
        "this reading is inferred by analogy with the same shape in INC_NUM and "
        "FIRE_NUM rather than from anything documented.",
    ),
    FieldSpec("DECADES", "Decade"),
)

FRAP_FIELDS_BY_NAME: dict[str, FieldSpec] = {spec.name: spec for spec in FRAP_FIELDS}


# --------------------------------------------------------------------------------------
# CAL FIRE Damage Inspection (DINS), layer "POSTFIRE"
# --------------------------------------------------------------------------------------

_UNKNOWN = frozenset({"unknown"})
"""The normalized form of the ``Unknown`` value published in many DINS domains."""

DINS_REQUIRED_COLUMNS: tuple[str, ...] = (
    "OBJECTID",
    "GLOBALID",
    "DAMAGE",
    "STRUCTURETYPE",
    "STRUCTURECATEGORY",
    "INCIDENTNAME",
    "INCIDENTNUM",
    "INCIDENTSTARTDATE",
    "HAZARDTYPE",
    "COUNTY",
    "CALFIREUNIT",
    "ROOFCONSTRUCTION",
    "EAVES",
    "VENTSCREEN",
    "EXTERIORSIDING",
    "WINDOWPANE",
    "DECKPORCHONGRADE",
    "DECKPORCHELEVATED",
    "PATIOCOVERCARPORT",
    "FENCEATTACHEDTOSTRUCTURE",
    "PROPANETANKDISTANCE",
    "UTILITYMISCSTRUCTUREDISTANCE",
    "WHEREFIRESTARTEDONSTRUCTURE",
    "WHATDIDFIRESTARTFROM",
    "DEFENSIVEACTIONS",
    "APN",
    "SITEADDRESS",
    "YEARBUILT",
    "ASSESSEDIMPROVEDVALUE",
    "LATITUDE",
    "LONGITUDE",
)

DINS_DAMAGE_VALUES = frozenset(
    {
        "Destroyed (>50%)",
        "Major (25-50%)",
        "Minor (10-25%)",
        "Affected (>0-10%)",
        "Inaccessible",
        "No Damage",
    }
)

DINS_INACCESSIBLE = "Inaccessible"
"""The published damage value for a structure the inspection could not reach.

This is the dataset's own distinction between a structure that was not assessed and a
structure that was assessed as undamaged. It is a recorded value, so it is present.
"""

DINS_NO_DAMAGE = "No Damage"
"""Inspected and found undamaged. A finding, never a null and never a zero."""

DINS_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "DAMAGE",
        "Damage",
        recorded_absences=frozenset({DINS_NO_DAMAGE}),
        domain_values=DINS_DAMAGE_VALUES,
        basis=Basis.PUBLISHED,
        note="'No Damage' is an inspection finding and 'Inaccessible' records that the "
        "structure could not be reached. Neither is an empty cell, and an empty cell is "
        "neither of them.",
    ),
    FieldSpec(
        "STRUCTURETYPE",
        "Structure type",
        domain_values=frozenset(
            {
                "Single Family Residence Single Story",
                "Single Family Residence Multi Story",
                "Mobile Home Single Wide",
                "Mobile Home Double Wide",
                "Mobile Home Triple Wide",
                "Motor Home",
                "Multi Family Residence Single Story",
                "Multi Family Residence Multi Story",
                "Mixed Commercial/Residential",
                "Commercial Building Single Story",
                "Commercial Building Multi Story",
                "Church",
                "Hospital",
                "School",
                "Infrastructure",
                "Utility Misc Structure",
            }
        ),
    ),
    FieldSpec(
        "STRUCTURECATEGORY",
        "Structure category",
        domain_values=frozenset(
            {
                "Single Residence",
                "Multiple Residence",
                "Mixed Commercial/Residential",
                "Nonresidential Commercial",
                "Infrastructure",
                "Other Minor Structure",
            }
        ),
    ),
    FieldSpec("INCIDENTNAME", "Incident name"),
    FieldSpec("INCIDENTNUM", "Incident number"),
    FieldSpec("INCIDENTSTARTDATE", "Incident start date"),
    FieldSpec(
        "HAZARDTYPE",
        "Hazard type",
        domain_values=frozenset(
            {"Fire", "Earthquake", "Flood", "Civil Disturbance", "Hazardous Material"}
        ),
    ),
    FieldSpec("COUNTY", "County"),
    FieldSpec("CALFIREUNIT", "CAL FIRE unit"),
    FieldSpec(
        "COMMUNITY",
        "Community",
        unknown_markers=frozenset({"unknown", "n/a", "na", "none", "-"}),
        basis=Basis.INFERRED,
        note="Free text with no published domain, so every marker here is read off the "
        "file. The field also carries the same place under several spellings, which "
        "this project does not merge; it counts whether a cell holds a community, not "
        "how many communities there are.",
    ),
    FieldSpec(
        "CITY",
        "City",
        unknown_markers=frozenset({"na", "n/a", "unknown", "none"}),
        basis=Basis.INFERRED,
        note="A large share of records carry a marker word in this field rather than a "
        "city. Read as text it would become a place name, so it is counted apart from "
        "both a recorded city and an empty cell. CITY has no published domain, so this "
        "is inferred. One thing the file shows is worth a reader's attention: every "
        "record holding NA belongs to an incident that started in 2020, and no record "
        "in that cohort holds the value Unincorporated that neighbouring years use. "
        "That pattern reads as a value applied to a load rather than determined per "
        "structure, which is why NA is not counted as a recorded city. Whether those "
        "cells are better read as a recorded marker or as an empty cell cannot be told "
        "from the file, and the distinction does not move any published present count, "
        "because neither state counts as a value.",
    ),
    FieldSpec(
        "ROOFCONSTRUCTION",
        "Roof construction",
        unknown_markers=_UNKNOWN,
        domain_values=frozenset(
            {"Wood", "Asphalt", "Concrete", "Tile", "Metal", "Other", "Unknown"}
        ),
        basis=Basis.PUBLISHED,
    ),
    FieldSpec(
        "EAVES",
        "Eaves",
        unknown_markers=_UNKNOWN | frozenset({"not applicable"}),
        recorded_absences=frozenset({"No Eaves"}),
        domain_values=frozenset({"Enclosed", "Unenclosed", "No Eaves", "Unknown"}),
        basis=Basis.INFERRED,
        note="'Unknown' and 'No Eaves' are both published domain values. 'Not "
        "Applicable' is not, and appears in the file anyway; it is counted as a marker "
        "rather than as a value, which is the reading that does not turn an "
        "undetermined eave into an observed one. That single addition is what makes "
        "this field inferred rather than published.",
    ),
    FieldSpec(
        "VENTSCREEN",
        "Vent screen",
        unknown_markers=_UNKNOWN,
        basis=Basis.PUBLISHED,
        recorded_absences=frozenset({"No Vents"}),
        domain_values=frozenset(
            {
                'Mesh Screen <= 1/8"',
                'Mesh Screen > 1/8"',
                "Unscreened",
                "No Vents",
                "Unknown",
            }
        ),
    ),
    FieldSpec(
        "EXTERIORSIDING",
        "Exterior siding",
        unknown_markers=_UNKNOWN,
        basis=Basis.PUBLISHED,
        domain_values=frozenset(
            {"Metal", "Stucco Brick Cement", "Vinyl", "Wood", "Other", "Unknown"}
        ),
    ),
    FieldSpec(
        "WINDOWPANE",
        "Window pane",
        unknown_markers=_UNKNOWN,
        recorded_absences=frozenset({"No Windows"}),
        basis=Basis.PUBLISHED,
        domain_values=frozenset({"Single Pane", "Multi Pane", "No Windows", "Unknown"}),
    ),
    FieldSpec(
        "DECKPORCHONGRADE",
        "Deck or porch on grade",
        unknown_markers=_UNKNOWN,
        recorded_absences=frozenset({"No Deck/Porch"}),
        basis=Basis.PUBLISHED,
        domain_values=frozenset(
            {"Composite", "Wood", "Masonry/Concrete", "No Deck/Porch", "Unknown"}
        ),
    ),
    FieldSpec(
        "DECKPORCHELEVATED",
        "Deck or porch elevated",
        unknown_markers=_UNKNOWN,
        recorded_absences=frozenset({"No Deck/Porch"}),
        basis=Basis.PUBLISHED,
        domain_values=frozenset(
            {"Composite", "Wood", "Masonry/Concrete", "No Deck/Porch", "Unknown"}
        ),
    ),
    FieldSpec(
        "PATIOCOVERCARPORT",
        "Patio cover or carport",
        unknown_markers=_UNKNOWN,
        recorded_absences=frozenset({"No Patio Cover/Carport"}),
        basis=Basis.PUBLISHED,
        domain_values=frozenset(
            {
                "Combustible",
                "Non Combustible",
                "No Patio Cover/Carport",
                "Unknown",
            }
        ),
    ),
    FieldSpec(
        "FENCEATTACHEDTOSTRUCTURE",
        "Fence attached to structure",
        unknown_markers=_UNKNOWN,
        recorded_absences=frozenset({"No Fence"}),
        basis=Basis.PUBLISHED,
        domain_values=frozenset(
            {"Combustible", "Non Combustible", "No Fence", "Unknown"}
        ),
    ),
    FieldSpec(
        "PROPANETANKDISTANCE",
        "Propane tank distance",
        unknown_markers=_UNKNOWN,
        recorded_absences=frozenset({"N/A"}),
        domain_values=frozenset({"0-10", "11-20", "21-30", ">30", "N/A"}),
        basis=Basis.INFERRED,
        note="'N/A' is published in the domain as 'Not Applicable', an inspector "
        "finding that the question does not apply, so it is present rather than "
        "missing. 'Unknown' is not in this field's published domain but appears in the "
        "file, and is counted as a marker; that addition is inferred, and it is what "
        "makes this field inferred rather than published.",
    ),
    FieldSpec(
        "UTILITYMISCSTRUCTUREDISTANCE",
        "Utility or misc structure distance",
        recorded_absences=frozenset({"NA", "N/A"}),
        domain_values=frozenset({"<30'", "30-50'", ">50'", "NA"}),
        basis=Basis.INFERRED,
        note="The published domain spells Not Applicable as 'NA'. The file carries "
        "'N/A' as well, and this project reads the two as one finding under two "
        "spellings rather than as two facts. Four things in the file support that. The "
        "spellings never occur together: no incident uses both, and every 'N/A' belongs "
        "to an incident that started in 2018 or 2019 while every 'NA' belongs to one "
        "that started in 2020 or later. Recorded distances appear on both sides of that "
        "line, so the change is a change of spelling and not of whether the question "
        "was asked. The sibling field PROPANETANKDISTANCE publishes 'N/A' as its own "
        "Not Applicable code and keeps that spelling across the same boundary, which is "
        "what a per-field domain revision looks like. And both spellings sit beside a "
        "propane Not Applicable at almost the same rate, 82 percent against 85 percent, "
        "which a marker for undetermined data would not do. Both are therefore counted "
        "as the published finding. 'N/A' is additionally reported under "
        "outside_published_domain, because the domain published today does not carry "
        "that spelling, so both facts reach the reader. CAL FIRE publishes no domain "
        "history, so the reading of 'N/A' as the earlier spelling is inferred.",
    ),
    FieldSpec(
        "WHEREFIRESTARTEDONSTRUCTURE",
        "Where fire started on structure",
        unknown_markers=_UNKNOWN | frozenset({"not applicable"}),
        basis=Basis.INFERRED,
        domain_values=frozenset(
            {
                "Roof",
                "Eaves",
                "Vent",
                "Siding",
                "Window",
                "Deck on Grade",
                "Deck Elevated",
                "Attached Patio Cover/Carport",
                "Attached Fence",
                "Unknown",
            }
        ),
        note="Collected only where the structure was affected per CAL FIRE's dictionary. "
        "'Unknown' is a published domain value; 'Not Applicable' is not, and the 23 "
        "records carrying it are counted as markers on an inference.",
    ),
    FieldSpec(
        "WHATDIDFIRESTARTFROM",
        "What the fire started from",
        unknown_markers=_UNKNOWN | frozenset({"not applicable"}),
        basis=Basis.INFERRED,
        domain_values=frozenset(
            {"Direct flame impingement", "Embers", "Radiant Heat", "Unknown"}
        ),
        note="Collected only where the structure was affected per CAL FIRE's dictionary. "
        "As with the field beside it, 'Unknown' is published and 'Not Applicable', on "
        "18 records, is not, so that marker is inferred.",
    ),
    FieldSpec(
        "DEFENSIVEACTIONS",
        "Defensive actions taken",
        unknown_markers=_UNKNOWN,
        basis=Basis.PUBLISHED,
        domain_values=frozenset(
            {
                "Combination of Actions",
                "Dozer Fuel Break",
                "Engine Company Actions",
                "Fire Retardant Drop",
                "Hand Crew Fuel Break",
                "Other",
                "Unknown",
            }
        ),
    ),
    FieldSpec("NUMBEROFUNITPERSTRUCTURE", "Units in structure", numeric=True),
    FieldSpec("NOOUTBUILDINGSDAMAGED", "Damaged outbuildings", numeric=True),
    FieldSpec("NOOUTBUILDINGSNOTDAMAGED", "Undamaged outbuildings", numeric=True),
    FieldSpec("NOOFCARSONPROPERTY", "Damaged or destroyed cars", numeric=True),
    FieldSpec(
        "APN",
        "APN (parcel)",
        unknown_markers=frozenset({"none", "unknown"}),
        basis=Basis.INFERRED,
        note="Added by a spatial join after collection, per CAL FIRE's description, so "
        "its coverage measures the join rather than the field inspection. No domain is "
        "published for it, so both markers are read off the file.",
    ),
    FieldSpec(
        "SITEADDRESS",
        "Site address (parcel)",
        unknown_markers=frozenset(
            {"none", "-", "no address available", "null null unknown ca 00000"}
        ),
        basis=Basis.INFERRED,
        note="Added by the same post-collection spatial join as APN, and free text with "
        "no published domain, so every marker here is inferred. Two of them are whole "
        "placeholder addresses rather than single words: the literal text 'No Address "
        "Available', and a composed placeholder reading 'NULL NULL UNKNOWN CA 00000'. "
        "Neither trips the single-token marker net, and this audit found them by "
        "reading the field's value distribution. Counting them as recorded addresses "
        "would publish a join that failed as a join that succeeded.",
    ),
    FieldSpec("YEARBUILT", "Year built (parcel)", numeric=True),
    FieldSpec(
        "ASSESSEDIMPROVEDVALUE", "Assessed improved value (parcel)", numeric=True
    ),
    FieldSpec(
        "STREETNAME",
        "Street name (field determined)",
        unknown_markers=frozenset({"unknown", "na", "none", "n/a"}),
        basis=Basis.INFERRED,
        note="Free text with no published domain, so every marker is read off the file.",
    ),
    FieldSpec(
        "STREETTYPE",
        "Street type (field determined)",
        unknown_markers=frozenset({"-", "unk", "n/a"}),
        recorded_absences=frozenset({"None"}),
        basis=Basis.INFERRED,
        domain_values=frozenset(
            {
                "Alley",
                "Avenue",
                "Boulevard",
                "Circle",
                "Court",
                "Drive",
                "Lane",
                "Loop",
                "Parkway",
                "Place",
                "Road",
                "Route",
                "Street",
                "Terrace",
                "Trail",
                "Way",
                "None",
                "Other",
            }
        ),
        note="'None' is a published domain value meaning the road carries no street "
        "type, so it is a present value rather than a blank. The three markers are not "
        "published anywhere and are read off the file; they cover nine records between "
        "them. Two further records read 'not given' and one reads 'not noted'. Those "
        "are left as recorded values outside the published domain, where they are "
        "counted and named, rather than folded into markers on a reading of three "
        "cells.",
    ),
    FieldSpec("LATITUDE", "Latitude", numeric=True),
    FieldSpec("LONGITUDE", "Longitude", numeric=True),
)

DINS_FIELDS_BY_NAME: dict[str, FieldSpec] = {spec.name: spec for spec in DINS_FIELDS}
