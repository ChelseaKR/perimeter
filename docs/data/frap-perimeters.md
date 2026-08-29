# Data card: California Historical Fire Perimeters

Required by DATA-GOVERNANCE-STANDARD section 1 (DG-01). The reviewed record this card
restates is `src/perimeter/sources.py`; `tests/test_data_cards.py` fails if the two
disagree, the same way `tests/test_provenance.py` holds `PROVENANCE.md` to it.

| Field | |
|---|---|
| Source | California Historical Fire Perimeters, published by California Department of Forestry and Fire Protection, Fire and Resource Assessment Program. Landing page: https://data.cnra.ca.gov/dataset/california-historical-fire-perimeters. Read from the GeoServices endpoint `https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/California_Historic_Fire_Perimeters/FeatureServer/0/query`, layer "California Fire Perimeters (all)" |
| Licence | Creative Commons Attribution (http://www.opendefinition.org/licenses/cc-by). No SPDX identifier is published by the source; this is the licence string the dataset itself carries |
| Fetch and refresh cadence | On each published FRAP version. The layer is released as a versioned annual product and the acquired file is firep25_1. Staleness SLA: **400 days** after the retrieval date, after which `tests/test_data_cards.py` fails |
| Fetch timestamp | `2026-08-07`, machine-readable in `src/perimeter/sources.py` as `retrieved`, in `data/raw/acquisition.json` per run, and in every published artifact under `source.retrieved` |
| Tier | L1: openly licensed public reference data, republished here only as counts |
| Known limitations | The publisher's own, quoted in `PROVENANCE.md` and in `src/perimeter/sources.py`, and measured rather than paraphrased. In short: FRAP states the record is incomplete, and this project publishes records per fire year rather than interpolating one. |
| Retention | DG-06, L1: indefinite, because the acquired file is what the measurement describes, unless the publisher revokes or relicenses it, in which case it is removed within 30 days of notice. `data/raw/` is gitignored and never in CI, so retention here is one working copy on one machine |

## What was acquired

| | |
|---|---|
| Version | `firep25_1` |
| Retrieved | 2026-08-07 |
| Records | 23,334 |
| Bytes | 7,964,688 |
| SHA-256 | `9be7bcb9c08f6813ba13263eabebc96256f0ea8fb0e809ad8a4171046466a16a` |
| File | `frap_perimeters.json` |

## The staleness SLA is this project's declaration

Neither CAL FIRE nor FRAP promises a publication schedule, and neither is asked to. The
number exists so that a retrieval going stale is a build failure here rather than a page
quietly describing a file that has moved on.

It is not on the pages. A page computing its own staleness would need a wall clock, and
`README.md` promises the artifacts have none: the same inputs produce byte-identical
output. What the artifacts publish instead is the retrieval date and
`staleness_sla_days`, so any consumer can do the subtraction against its own clock and
get the same answer this build would.

400 days is one annual release cycle plus about five weeks, so a retrieval does
not go stale on the eve of the version that would replace it. The acquired file
is `firep25_1`; the layer is published as a versioned annual product.
