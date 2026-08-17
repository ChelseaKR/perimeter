# Provenance

Two sources, both published by the California Department of Forestry and Fire Protection,
both under a Creative Commons Attribution licence, both read from a GeoServices REST
endpoint that the dataset itself lists among its published resources.

The values in this file are mirrored from `src/perimeter/sources.py`, which is the single
reviewed record. `tests/test_provenance.py` fails if the two disagree, so this document
cannot drift away from the numbers the pages print.

## Acquisition

Acquisition is a separate step from the build, run by hand:

```sh
uv run python -m perimeter.acquire --out data/raw
```

`data/raw/` is not in git and is never used by CI. The build reads files already on disk,
so a build is reproducible without asking CAL FIRE's servers for anything. Re-running
acquisition on an unchanged layer produces a byte-identical file, because the writer sorts
keys and pins its separators; the SHA-256 below is what to compare against.

Before the walk starts, the layer is asked how many records match the predicate the walk
uses, and nothing is written unless the walk comes back with that many. A short download
is the one failure that does not look like one: it produces a complete-looking file with a
hash and a date, and every count taken from it describes a fraction of the layer in the
same words it would use for all of it. The record counts below are the layers' own totals.

Geometry is not requested. Every measurement here is over attributes, so `returnGeometry`
is false on every request. That keeps the download small and keeps this project honest
about what it can speak to: nothing on either page describes the shape, extent or accuracy
of any polygon.

### If an endpoint declines automated access

`perimeter.acquire` raises `AcquisitionBlocked` and stops. It does not retry under another
identity, does not present itself as a browser, and has no second path. If that happens,
download the file from the dataset's landing page by hand, record the manual acquisition
in the table below with the date and the file's size and hash, and note it in the
CHANGELOG. Both endpoints answered ordinary automated requests on the retrieval date.

## S1. California Historical Fire Perimeters

| | |
|---|---|
| Publisher | California Department of Forestry and Fire Protection, Fire and Resource Assessment Program |
| Landing page | https://data.cnra.ca.gov/dataset/california-historical-fire-perimeters |
| Endpoint | `https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/California_Historic_Fire_Perimeters/FeatureServer/0/query` |
| Layer read | California Fire Perimeters (all) |
| Licence | Creative Commons Attribution |
| Version | firep25_1 |
| Retrieved | 2026-08-07 |
| Records | 23,334 |
| Bytes on disk | 7,964,688 |
| SHA-256 | `9be7bcb9c08f6813ba13263eabebc96256f0ea8fb0e809ad8a4171046466a16a` |
| Local file | `data/raw/frap_perimeters.json` |

The service publishes three layers over the same records. Layer 0, "California Fire
Perimeters (all)", is the unfiltered one and is the only layer read. Layers 1 and 2 are
filtered views (recent large fires, and 1950 onward) and measuring them would be measuring
a filter.

FRAP's Wildland Fire Perimeters metadata document, linked from the dataset page, carries
the attribute table and the release notes. It is the source for the field definitions
quoted in `docs/MARKERS.md`, alongside the coded-value domains the layer itself returns.

| | |
|---|---|
| Metadata document | https://calfire-forestry.maps.arcgis.com/home/item.html?id=a31aa1efe1d6466f8530b501c30ab00a |
| Layer domains | `https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/California_Historic_Fire_Perimeters/FeatureServer/0?f=pjson` |

### What FRAP says about this dataset

> Although the dataset represents the most complete digital record of fire perimeters in
> California, it is still incomplete, and users should be cautious when drawing
> conclusions based on the data.

> This data should be used carefully for statistical analysis and reporting due to missing
> perimeters (see Use Limitation in metadata). Some fires are missing because historical
> records were lost or damaged, were too small for the minimum cutoffs, had inadequate
> documentation or have not yet been incorporated into the database. Other errors with the
> fire perimeter database include duplicate fires and over-generalization. Additionally,
> over-generalization, particularly with large old fires, may show unburned “islands”
> within the final perimeter as burned.

> CAL FIRE (including contract counties) submit perimeters ≥10 acres in timber, ≥50 acres
> in brush, or ≥300 acres in grass, and/or ≥3 impacted residential or commercial
> structures, and/or caused ≥1 fatality. All cooperating agencies submit perimeters ≥10
> acres.

> A new field, Global ID, was added to provide a unique ID to track all fire records in
> this dataset including those pre-dating IRWIN IDs.

> A count of 12,097 fires' collection methods were edited from Null values to Unknown.

## S2. CAL FIRE Damage Inspection (DINS) Data

| | |
|---|---|
| Publisher | California Department of Forestry and Fire Protection |
| Landing page | https://data.ca.gov/dataset/cal-fire-damage-inspection-dins-data |
| Endpoint | `https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/POSTFIRE_MASTER_DATA_SHARE/FeatureServer/0/query` |
| Layer read | POSTFIRE |
| Licence | Creative Commons Attribution |
| Version | POSTFIRE_MASTER_DATA_SHARE |
| Retrieved | 2026-08-07 |
| Records | 132,522 |
| Bytes on disk | 163,728,068 |
| SHA-256 | `7683850bec00c201ad05ae55ab3c70baf53acd298a1da2fe8fd3c5432a624761` |
| Local file | `data/raw/dins_postfire.json` |

The dataset also publishes a CSV export. It is not used. That export's header row carries
the field *aliases* rather than the field names, including one alias containing an HTML
entity, so a rename upstream could shift which column a measurement is about without the
build noticing. The GeoServices endpoint returns canonical field names and is listed among
the dataset's own resources.

CAL FIRE publishes a database dictionary for this dataset, linked from the dataset page.
It gives each field's definition, size and whether it carries a domain, and it is the
second source, after the layer's own coded-value domains, that `docs/MARKERS.md` checks
every DINS declaration against.

| | |
|---|---|
| Database dictionary | https://calfire-forestry.maps.arcgis.com/sharing/rest/content/items/db241103701846fa8c5b945cfeedda07/data |
| Layer domains | `https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/POSTFIRE_MASTER_DATA_SHARE/FeatureServer/0?f=pjson` |

### What CAL FIRE says about this dataset

> Information such as structure type, construction features, and defensive actions are
> determined as best as possible. Attributes with null values could not be determined.

> Fire damage and poor access are major limiting factors for damage inspectors. All
> inspections are conducted using a systematic inspection process, however not all
> structures impacted by the fire may be identified due to these factors. Therefore, a
> small margin of error is expected.

> Two address fields are included in the database. The street number, street name, and
> street type fields are “field determined.” The inspector inputs this information based
> on what they see in the field. The Address (parcel) and APN (parcel) fields are added
> through a spatial join after data collection is complete.

> This database is used to document all structures impacted by wildland fire within the
> Statewide Responsibility Area (SRA) that are inside or within 300 feet of the fire
> perimeter.

## Fixtures

`fixtures/frap_perimeters.sample.json` and `fixtures/dins_postfire.sample.json` are
hand-written, not sampled from the acquired files. DINS records carry real street
addresses, parcel numbers and assessed values for identifiable properties, and this repo
has no reason to republish those to exercise a parser. Every fixture value is invented to
put one classification case in front of the tests: a genuine zero, an empty cell, a
published unknown code, a marker word, a finding of absence such as `No Damage`, a value
outside the published domain, a structure that could not be reached, and a record with no
year at all.

A build from fixtures stamps `is_fixture: true` and publishes `null` for every acquisition
fact: version, retrieval date, record count, byte count and hash. Fixture output cannot
present itself as a measurement of CAL FIRE's real files.

## Exclusions

Nothing acquired has been excluded from the counts. Every record in both layers is
measured, including the seventeen perimeter records whose state is not California and the
DINS records whose hazard type is not fire. Filtering them out would make the published
totals disagree with the source, and the point of the totals is that they agree.

These are not measured, and are named here so their absence is deliberate rather than
implied:

- **Polygon geometry.** Not downloaded. Over-generalization, which FRAP lists among the
  known issues, is a property of the geometry, so this project cannot and does not speak
  to it. `GIS_ACRES` is the one geometry-derived attribute available without it.
- **Layers 1 and 2 of the perimeter service.** Filtered views of layer 0.
- **The `COMMENTS` field on perimeters and the DINS street number, suffix, zip, battalion,
  fire name and object identifiers.** Present in the source, not part of either
  measurement.
- **Anything joining these records to another dataset.** No linkage to NIFC, to parcel
  rolls, or to loss or insurance data. The IRWIN ID measurement counts whether the
  identifier is present; it does not follow it anywhere.
