# Data card: CAL FIRE Damage Inspection (DINS) Data

Required by DATA-GOVERNANCE-STANDARD section 1 (DG-01). The reviewed record this card
restates is `src/perimeter/sources.py`; `tests/test_data_cards.py` fails if the two
disagree, the same way `tests/test_provenance.py` holds `PROVENANCE.md` to it.

| Field | |
|---|---|
| Source | CAL FIRE Damage Inspection (DINS) Data, published by California Department of Forestry and Fire Protection. Landing page: https://data.ca.gov/dataset/cal-fire-damage-inspection-dins-data. Read from the GeoServices endpoint `https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/POSTFIRE_MASTER_DATA_SHARE/FeatureServer/0/query`, layer "POSTFIRE" |
| Licence | Creative Commons Attribution (http://www.opendefinition.org/licenses/cc-by). No SPDX identifier is published by the source; this is the licence string the dataset itself carries |
| Fetch and refresh cadence | After each fire season. The layer carries no version string and is appended to as inspections complete, so there is no release to wait for. Staleness SLA: **180 days** after the retrieval date, after which `tests/test_data_cards.py` fails |
| Fetch timestamp | `2026-08-07`, machine-readable in `src/perimeter/sources.py` as `retrieved`, in `data/raw/acquisition.json` per run, and in every published artifact under `source.retrieved` |
| Tier | L1: openly licensed public reference data, republished here only as counts |
| Known limitations | The publisher's own, quoted in `PROVENANCE.md` and in `src/perimeter/sources.py`, and measured rather than paraphrased. In short: CAL FIRE states that attributes with null values could not be determined, and that fire damage and access limit what an inspector can record, so blanks are counted apart from findings and assessed records apart from inaccessible ones. |
| Retention | DG-06, L1: indefinite, because the acquired file is what the measurement describes, unless the publisher revokes or relicenses it, in which case it is removed within 30 days of notice. `data/raw/` is gitignored and never in CI, so retention here is one working copy on one machine |

## What was acquired

| | |
|---|---|
| Version | `POSTFIRE_MASTER_DATA_SHARE` |
| Retrieved | 2026-08-07 |
| Records | 132,522 |
| Bytes | 163,728,068 |
| SHA-256 | `7683850bec00c201ad05ae55ab3c70baf53acd298a1da2fe8fd3c5432a624761` |
| File | `dins_postfire.json` |

## The staleness SLA is this project's declaration

Neither CAL FIRE nor FRAP promises a publication schedule, and neither is asked to. The
number exists so that a retrieval going stale is a build failure here rather than a page
quietly describing a file that has moved on.

It is not on the pages. A page computing its own staleness would need a wall clock, and
`README.md` promises the artifacts have none: the same inputs produce byte-identical
output. What the artifacts publish instead is the retrieval date and
`staleness_sla_days`, so any consumer can do the subtraction against its own clock and
get the same answer this build would.

180 days is about one fire season. The layer carries no version string and is
appended to as inspections complete, so there is no release to wait for and no
moment at which the file is finished. After a season the file has grown by
incidents this measurement does not describe, and the record count on the page is
a count of an older file.
