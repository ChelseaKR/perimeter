# Marker audit

Every value this project treats as a missing-data marker rather than as a recorded value,
with the evidence behind it, the document it can be checked against, what it does to the
published numbers, and how much confidence it deserves.

The reason this file exists: deciding that `00000000` is a placeholder rather than an
incident number changes a published figure by a factor of thirty, and a reader cannot
tell from the value which kind of decision that was. Some of these calls are read
straight off a coded-value domain the publisher maintains. Others are read off the
distribution of the acquired file. Both are counted the same way and neither is a defect
in either dataset: CAL FIRE and FRAP publish domains for the fields they constrain and
say plainly which fields are free text. What follows is a record of this project's
judgment, not of theirs.

Audited 2026-08-07 against the files recorded in `PROVENANCE.md`.
`src/perimeter/schema.py` is the registry itself; this document is the audit of it.
`tests/test_schema.py` keeps the two from drifting apart.

## Sources this audit was checked against

| # | Document | URL |
|---|---|---|
| D1 | FRAP layer metadata, coded-value domains as the service publishes them | `https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/California_Historic_Fire_Perimeters/FeatureServer/0?f=pjson` |
| D2 | FRAP, Wildland Fire Perimeters metadata (PDF), attribute table and release notes | https://calfire-forestry.maps.arcgis.com/home/item.html?id=a31aa1efe1d6466f8530b501c30ab00a |
| D3 | DINS layer metadata, coded-value domains as the service publishes them | `https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/POSTFIRE_MASTER_DATA_SHARE/FeatureServer/0?f=pjson` |
| D4 | Damage Inspection (DINS) Database Dictionary (PDF), linked from the dataset page | https://calfire-forestry.maps.arcgis.com/sharing/rest/content/items/db241103701846fa8c5b945cfeedda07/data |
| D5 | FRAP dataset description | https://data.cnra.ca.gov/dataset/california-historical-fire-perimeters |
| D6 | DINS dataset description | https://data.ca.gov/dataset/cal-fire-damage-inspection-dins-data |
| F1 | The acquired files themselves, hashes in `PROVENANCE.md` | not a document |

**Basis** below is one of two values, and it is also carried in `schema.py`, in the JSON
artifacts as `marker_basis`, and on the pages beside each field's marker list:

- **published**: every declared value appears in a coded-value domain in D1 or D3, or in
  the field definitions in D2 or D4.
- **inferred**: at least one declared value appears in none of those, and was read off
  the distribution of the acquired file.

Twenty-eight of the fifty-four measured fields declare a marker, a code or a finding of
absence. **Twelve are published. Sixteen rest on inference.**

## 1. The all-zeros local incident number

**Endorsed, with its basis corrected from published to inferred.**

`INC_NUM` on 12,469 of 23,334 perimeter records holds `00000000`, and this project counts
that apart from the 9,910 recorded numbers rather than reading it as an identifier.

What the documentation says. D2 defines the field as "Number assigned by the Emergency
Command Center of the responsible agency for the fire", `Text`, maximum 8 characters. D1
and D2 agree that `INC_NUM` carries **no coded-value domain**: of the eighteen attributes,
only `STATE`, `AGENCY`, `UNIT_ID`, `CAUSE`, `C_METHOD` and `OBJECTIVE` are constrained.
Nothing in D1, D2 or D5 documents an all-zeros value or any placeholder convention for
this field. **The previous claim in `schema.py` that every marker in the file was read off
a published domain was therefore wrong for this field, and is corrected.**

What the file shows (F1, all reproducible from the acquired file):

| Observation | Value |
|---|---|
| Records holding `00000000` | 12,469 (53.4% of the layer) |
| Distinct reporting units among them | 64 |
| Distinct fire years among them | 115, spanning 1878 to 2025 |
| Distinct reporting agencies among them | 9 |
| Distinct fire names among them | 4,794 |
| (year, unit) groups holding it more than once | 1,778 of 2,384 |
| Largest single group | 61 records, Los Angeles County, 1975 |
| Records holding it, 1878 to 1939 | 3,800, against 0 recorded numbers |
| Records holding it, 2020 to 2025 | 1, against 2,552 recorded numbers |

The definition in D2 is what settles it. A number an Emergency Command Center assigns to
a fire identifies that fire for that agency. Sixty-one separate Los Angeles County fires
in 1975 did not receive the same assignment, and the value's collapse from universal
before 1940 to a single record in the 2020s is the shape of a placeholder written into
records digitised before the field was captured, not the shape of an identifier.

**Effect on published figures.** Both figures reproduce exactly, and both are now in the
JSON artifact rather than asserted in prose. The reviewed reading is published in
`duplicate_signals`; the other reading is published beside it in
`marker_counterfactuals`, so the cost of the call is a number a reader can see.

| Reading | Records keyed | Distinct keys | Keys used more than once | Records sharing a key |
|---|---|---|---|---|
| `00000000` read as a number | 22,361 | 12,028 | 1,897 | 12,230 |
| `00000000` read as a placeholder (published) | 9,901 | 9,644 | 119 | 376 |

It also sets `INC_NUM` coverage: 9,910 recorded, 12,469 recorded-as-unknown, 955 empty.

**Confidence: high.** The inference is not documented, but the field's own published
definition and six independent properties of the distribution all point one way, and no
reading of the file supports the alternative.

## 2. `NA` against `N/A` in the utility structure distance

**Changed. The two spellings are one marker, and that marker is the published finding.**

Previously `NA` was counted as a recorded value and `N/A` as missing data. Both are now
counted as the published Not Applicable finding.

What the documentation says. D3 publishes the domain for
`UTILITYMISCSTRUCTUREDISTANCE` as four codes: `<30'`, `30-50'`, `>50'`, and `NA`, whose
display label is **"Not Applicable"**. The sibling field `PROPANETANKDISTANCE` publishes
its own Not Applicable code as **`N/A`**. D4 lists the propane field's values as
"(0-10', 11-20', 21-30', >30', Not Applicable)" and records that the utility field
carries a domain without spelling its values out. So both spellings are CAL FIRE's own
way of writing the same phrase, in two fields on the same inspection form. Nothing
published describes the utility field's domain history, so reading `N/A` as its earlier
spelling is an inference.

What the file shows (F1). Four things, and they agree:

1. **The spellings never share an incident.** 113 incidents use only `NA`, 24 use only
   `N/A`, and none use both.
2. **They fall on opposite sides of one year.** Every one of the 6,544 `N/A` records
   belongs to an incident that started in 2018 or 2019. Every one of the 12,234 `NA`
   records belongs to an incident that started in 2020 or later.
3. **The question was asked on both sides of that line.** Recorded distances appear in
   both eras at comparable rates, 7,229 in 2018 alone against 2,799 in 2020, so the
   change is a change of spelling and not of whether the field was collected.
4. **Both behave like the finding, not like a blank.** Where the utility field says `NA`,
   the propane field says its own Not Applicable on 82% of records; where the utility
   field says `N/A`, it does so on 85%. `PROPANETANKDISTANCE` keeps the `N/A` spelling
   across the same 2019-to-2020 boundary unchanged, which is what a revision to one
   field's domain looks like. The structure-type mix behind the two spellings is also
   alike, 24.1% and 20.8% utility structures, and close to the 27.2% behind `<30'`.

**Effect on published figures**, for `UTILITYMISCSTRUCTUREDISTANCE` over 132,522 records:

| | Before | After |
|---|---|---|
| Recorded value | 31,239 (23.6%) | **37,783 (28.5%)** |
| Recorded as unknown | 6,544 | **0** |
| Empty cell | 94,739 | 94,739 |
| Outside the published domain | 243 | **6,787** |
| Present, assessed records | 31,210 (23.7%) | **37,740 (28.6%)** |
| Present, inaccessible records | 29 (4.9%) | **43 (7.3%)** |

`N/A` is counted as present **and** reported under `outside_published_domain`, because the
domain published today does not carry that spelling. Both facts reach the reader rather
than one being chosen over the other.

**Confidence: high** that the two spellings mean one thing, on the strength of the
sibling field's published label and four agreeing properties of the distribution.
**Moderate** on the further reading that `N/A` is specifically the pre-2020 spelling,
since no domain history is published to check that against.

## 3. Every other declaration

Counts are over the acquired files in `PROVENANCE.md`. "Effect" is the number of records
the declaration moves out of the recorded-value count.

### FRAP perimeters, 23,334 records

| Field | Declared | Kind | Basis | Evidence | Effect | Confidence |
|---|---|---|---|---|---|---|
| `CAUSE` | code `14` | unknown | **published** | D1, D2: domain value "Unknown / Unidentified" | 10,514 records; cause reads 54.9% recorded rather than 100% complete | high |
| `C_METHOD` | code `8` | unknown | **published** | D1, D2: domain value "Unknown". D5 records 12,097 collection methods edited from null to Unknown | 15,081 records; 35.4% recorded rather than 100% | high |
| `FIRE_NAME` | `unknown`, `none`, `n/a` | markers | *inferred* | No domain (D1, D2). D2 defines the field as the name of the fire in upper case | 85 records (72 `N/A`, 12 `UNKNOWN`, 1 `NONE`) | high: a fire named N/A is not a name |
| `INC_NUM` | `00000000` | marker | *inferred* | Section 1 | 12,469 records | high |
| `FIRE_NUM` | `<null>`, `00000000` | markers | *inferred* | No domain (D1). D2: "Former numbering system preceding incident numbers" | 3,623 records (3,620 zeros, 3 literal `<Null>`) | high |
| `COMPLEX_ID` | `00000000` | marker | *inferred* | No domain (D1). D2: "If part of complex, the complex incident number", and release notes describe the field transitioning between local incident numbers and complex IRWIN IDs | 1 record | moderate: one record, read by analogy with the two fields above |

### DINS damage inspections, 132,522 records

| Field | Declared | Kind | Basis | Evidence | Effect | Confidence |
|---|---|---|---|---|---|---|
| `DAMAGE` | `No Damage` | finding | **published** | D3, D4: domain value. D6 describes the inspection process | 0 moved; keeps 54,414 findings out of the blanks and 591 `Inaccessible` out of "undamaged" | high |
| `ROOFCONSTRUCTION` | `Unknown` | marker | **published** | D3, D4 both list Unknown | 18,535 | high |
| `VENTSCREEN` | `Unknown`, `No Vents` | marker, finding | **published** | D3, D4 | 40,139 | high |
| `EXTERIORSIDING` | `Unknown` | marker | **published** | D3, D4 | 17,540 | high |
| `WINDOWPANE` | `Unknown`, `No Windows` | marker, finding | **published** | D3, D4 | 33,469 | high |
| `DECKPORCHONGRADE` | `Unknown`, `No Deck/Porch` | marker, finding | **published** | D3, D4 | 15,777 | high |
| `DECKPORCHELEVATED` | `Unknown`, `No Deck/Porch` | marker, finding | **published** | D3, D4 | 18,750 | high |
| `PATIOCOVERCARPORT` | `Unknown`, `No Patio Cover/Carport` | marker, finding | **published** | D3, D4 | 20,235 | high |
| `FENCEATTACHEDTOSTRUCTURE` | `Unknown`, `No Fence` | marker, finding | **published** | D3, D4 | 15,133 | high |
| `DEFENSIVEACTIONS` | `Unknown` | marker | **published** | D3, D4 | 27,707 | high |
| `EAVES` | `Unknown`, `No Eaves` published; `Not Applicable` not | markers, finding | *inferred* | D3 and D4 give the domain as Enclosed, Unenclosed, No Eaves, Unknown. `Not Applicable` is in the file and in neither document | 893 of 52,364 rest on the inference | moderate: the field already publishes `No Eaves` for the absence, so what `Not Applicable` adds is not documented. Counted as undetermined, which is the reading that does not invent an observation |
| `PROPANETANKDISTANCE` | `N/A` published as a finding; `Unknown` not | marker, finding | *inferred* | D3 domain label "Not Applicable" for `N/A`; D4 lists the same five values. `Unknown` is in the file and in neither | 6,646 | high: `Unknown` is the published unknown in nine sibling domains |
| `UTILITYMISCSTRUCTUREDISTANCE` | `NA`, `N/A` | findings | *inferred* | Section 2 | 6,544 records moved into the recorded count | high on the merge, moderate on the era reading |
| `WHEREFIRESTARTEDONSTRUCTURE` | `Unknown` published; `Not Applicable` not | markers | *inferred* | D3, D4 list Unknown and not Not Applicable. D4: "Only recorded for Affected 1-9% damage category" | 23 of 8,739 rest on the inference | moderate: 23 records, and on an if-affected field `Not Applicable` could as easily be a finding that the structure was not affected |
| `WHATDIDFIRESTARTFROM` | `Unknown` published; `Not Applicable` not | markers | *inferred* | D3, D4. D4 adds "May not be reliably determined" | 18 of 5,828 | moderate, same reasoning |
| `CITY` | `na`, `n/a`, `unknown`, `none` | markers | *inferred* | No domain (D3, D4). D4: "Physical city observed by the field inspector in which the inspected property resides" | 27,565, of which 26,824 are `NA` | high that these are not cities; see the note below on what kind of marker they are |
| `COMMUNITY` | `unknown`, `n/a`, `na`, `none`, `-` | markers | *inferred* | No domain (D3, D4). D4: "Used if a local area has an unofficial name but commonly recognized name" | 772 | high |
| `STREETNAME` | `unknown`, `na`, `none`, `n/a` | markers | *inferred* | No domain (D3, D4). D4: "Physical street name observed by the field inspector" | 1,529 | high |
| `STREETTYPE` | `None` published as a finding; `-`, `unk`, `n/a` not | markers, finding | *inferred* | D3 lists `None` among eighteen domain values. The three markers are in neither document | 9 records | high on `None` being a finding, moderate on three markers covering nine records |
| `APN` | `none`, `unknown` | markers | *inferred* | No domain (D3, D4). D4: "Assessor Parcel Number assigned by the local assessor. Source: County parcels" | 43 | high |
| `SITEADDRESS` | `none`, `-`, `no address available`, `null null unknown ca 00000` | markers | *inferred* | No domain (D3, D4). D4: "The site address is usually comprised of the street number, name, type and address suffix, city, state and zip Code. Source: County parcels" | 732, up from 59 before this audit | high; see below |
| `YEARBUILT` | `0` | marker | *inferred* | No domain published for it. Section 7 | 12,148 records; the field reads 67.9% recorded rather than 77.0% | high that a 0 is not a construction year; moderate on what kind of absence it stands for |

## 4. What this audit changed

### `SITEADDRESS`: two placeholder addresses that the marker net was not catching

The marker net in `cells.py` matches single tokens. Two values in this field are whole
placeholder strings and so passed through it, and were being published as recorded
addresses:

| Value | Records |
|---|---|
| `No Address Available` | 513 |
| `NULL  NULL    UNKNOWN CA 00000` | 160 |

Both are now declared markers. `SITEADDRESS` moves from 124,811 recorded (94.2%) to
**124,138 (93.7%)**, and from 59 recorded-as-unknown to **732**. On assessed records the
share moves from 94.3% to 93.8%.

This is a limit of the marker net worth stating: it catches a cell that *is* a marker
word, not a cell that *contains* one inside a longer string. Both datasets were read
field by field for this audit; a future field could carry a composed placeholder that
neither the net nor a reader has noticed.

### `CITY`: the marker is endorsed, and one thing about it is now on the record

All 26,824 records holding `NA` belong to incidents that started in 2020, and no record in
that cohort holds `Unincorporated`, which is the value the 2015 to 2019 incidents use for
a structure outside a city. The value therefore looks like one applied to a load rather
than determined per structure.

That does not change the call: `NA` is not a city and is not counted as one. It does mean
the distinction between "recorded as unknown" and "empty cell" cannot be settled for these
cells from the file. Neither state counts as a recorded value, so **no published present
count or share depends on which of the two it is**, and the field's note now says so.

## 5. Declarations this audit considered and did not make

Recorded so the omissions are deliberate rather than accidental.

- **`FIRE_NUM` holding a bare `0`.** One record carries `0` rather than the padded
  `00000000`. Numerically it is the same value, and reading it as a placeholder would be
  consistent. It is left as a recorded number: extending an inference to a shape the file
  uses once is a bigger step than the one record is worth, and a reader can see the
  single-record difference here.
- **`STREETTYPE` holding `not given` (2 records) and `not noted` (1).** These read like
  markers and are left as recorded values outside the published domain, where they are
  counted and named in `outside_published_domain_values`. Three cells is not enough to
  read a convention from.
- **Merging spelling variants of a place name.** `COMMUNITY` holds the same community
  under several spellings, with and without trailing spaces. This project counts whether
  a cell holds a community, not how many communities there are, so no merging is done.

## 6. One difference between two published documents

D2's attribute table lists thirteen `AGENCY` codes, including `CSP` for California State
Parks. The domain D1 publishes for the same field lists twelve and does not include it.
This project follows D1, because D1 is what the endpoint being read returns. It changes no
number: no record in the acquired file carries `CSP`, and the file has no `AGENCY` value
outside the published domain at all. Recorded here because a later file might.

D4 writes two damage bands as "Major (26-50%)" and "Affected (1-9%)" where D3 and the
acquired file both use "Major (25-50%)" and "Affected (>0-10%)". This project follows D3
and the file.

## 7. Zeros in numeric fields

A zero is a judgment call of exactly the same kind as a marker word, and until this
section existed nothing here made it. `docs/MARKERS.md` audited every field that
*declares* a vocabulary, and a numeric field deciding that its zeros are measurements
declares nothing at all, so it was audited by nobody. Six fields publish a
`recorded_zero_values` count above zero. This is what each one's zeros are.

`tests/test_schema.py` now fails when a numeric field publishes recorded zeros and this
document does not cover it.

| Field | Recorded zeros | Reading | Declared? |
|---|---|---|---|
| `NOOUTBUILDINGSDAMAGED` | 59,628 | a count of no outbuildings damaged | no, a zero is the measurement |
| `NOOUTBUILDINGSNOTDAMAGED` | 58,888 | a count of no undamaged outbuildings | no, a zero is the measurement |
| `NOOFCARSONPROPERTY` | 55,831 | a count of no cars | no, a zero is the measurement |
| `NUMBEROFUNITPERSTRUCTURE` | 58,411 | contested; see below | no, and the reason is recorded |
| `ASSESSEDIMPROVEDVALUE` | 6,613 | contested; see below | no, and the reason is recorded |
| `YEARBUILT` | 12,148 | a parcel record with no year on it | **yes**, marker `0`, inferred |

`GIS_ACRES` on the FRAP side, and `LATITUDE` and `LONGITUDE` on the DINS side, hold no
recorded zeros at all in the acquired files, so they make no call to audit. A `0` turning
up in any of them later would need this section extended before the build goes green.

### `YEARBUILT`: 12,148 records built in year 0

**Declared.** `0` is read as a marker, on an inference, and the field moves from 102,091
recorded values (77.0%) to 89,943 (67.9%), with 12,148 counted as recorded-as-unknown.
30,431 empty cells are unaffected.

What the documentation says. CAL FIRE describes the parcel fields as added after
collection: "The Address (parcel) and APN (parcel) fields are added through a spatial
join after data collection is complete", quoted in `src/perimeter/sources.py`. No
coded-value domain is published for `YEARBUILT`, so nothing documents a placeholder
convention, and this reading is an inference like `INC_NUM` in section 1.

What settles it is that no reading makes the value a year. A structure standing in a
California wildfire between 2013 and 2025 was not built in year 0. The remaining question
is only whether `0` is a placeholder or noise, and the file answers that:

| Observation | Value |
|---|---|
| Records holding `0` | 12,148 (9.2% of the file) |
| Distinct incidents holding it | 186 |
| Distinct counties holding it | 45 |
| Distinct fire years holding it | 8, from 2017 to 2025 |
| Incident groups holding it at all | 199 of 436 |
| Incident groups where *every* record holds it | 55 |
| Largest such group | 446 of 446 records, Valley, 2020 |
| Records holding it that also carry an APN | 11,779 of 12,148 |
| Records holding it whose assessed improved value is also `0` | 5,527 (45.5%) |
| Records holding a real year whose assessed improved value is `0` | 391 of 89,943 (0.4%) |

Two things follow. The zero is not one bad load: it is in 186 incidents, 45 counties and
eight fire years, and it is scattered inside incidents as often as it takes one whole.
And it travels with the *other* parcel number being zero at a hundred times the rate a
real year does, which is what a parcel record with nothing on file looks like and is not
what a construction year looks like. The APN is present on 97% of them, so the join found
a parcel and the parcel had no year, rather than the join failing.

**Confidence: high** that a `0` is not a construction year. **Moderate** on the further
reading that it means the parcel record carried no year: no domain history is published
to check that against, and `Not Applicable` and `not on file` are indistinguishable here.
Either way it is not a value, and counting it as one was the error.

Eight other records carry years that are also not plausible: four hold `1`, three hold
`89`, one holds `1543`. They are left as recorded values, on the same reasoning as
`FIRE_NUM`'s bare `0` in section 5: eight cells across a file of 132,522 is a scatter of
typos, not a convention, and a reader can see the difference here.

### `NUMBEROFUNITPERSTRUCTURE`: considered, and not declared

58,411 records hold `0`, 3,518 hold a positive number and 70,593 are blank. The zeros are
not distributed like the positives:

| Structure category | Holding `0` | Holding a positive number |
|---|---|---|
| Single Residence | 39,438 | 1,453 |
| Other Minor Structure | 15,946 | 337 |
| Nonresidential Commercial | 2,008 | 242 |
| Multiple Residence | 254 | 1,443 |

Positive values concentrate where a unit count is the point: 1,443 of the 2,007 Multiple
Residence records carry one. A zero on a utility or miscellaneous structure is a coherent
observation, and 15,946 of the zeros are exactly that. A zero on 39,438 single residences
is harder, since a single residence has one unit, and 1,668 records do write `1`.

Not declared, and the reason is that unlike `YEARBUILT` this field has a reading in which
the zero is real. "No separately counted units" is a possible finding for a structure that
is not multi-unit, and the file cannot separate that from "not counted". Declaring it a
marker would move 58,411 records on a reading the file does not settle, which is the
opposite of the discipline in `CONTRIBUTING.md`. The count is published as
`recorded_zero_values` so a reader can apply either reading.

### `ASSESSEDIMPROVEDVALUE`: considered, and not declared

6,613 records hold `0`, from the same post-collection parcel join as `YEARBUILT`. 5,527 of
them sit on records whose year built is also `0`, against 391 of the 89,943 records that
carry a real year, so the two zeros travel together and the co-occurrence is a hundredfold.

It is still left as a recorded value. A parcel assessed at zero improved value is a thing
that exists: an unimproved parcel, an exempt one, or a structure not separately assessed.
The zeros also spread across 126 incidents and across the damage bands, 3,718 on
undamaged structures and 2,499 on destroyed ones, which is not the shape of a field that
stopped being collected. Unlike a year of 0, a dollar value of 0 is inside the field's own
range.

**This is the entry to revisit first.** If a later retrieval shows the two zeros still
locked together, or CAL FIRE publishes a domain for the parcel fields, the reading here
changes. It is recorded now so that the next reader starts from the number rather than
from scratch.

### The three count fields

`NOOUTBUILDINGSDAMAGED` (59,628 zeros against 2,311 positive), `NOOUTBUILDINGSNOTDAMAGED`
(58,888 against 3,070) and `NOOFCARSONPROPERTY` (55,831 against 357) are inspector counts,
and a count of zero is what an inspector writes when there were none. Their positive
values run from 1 upward in the shape a real count has. Nothing is declared and nothing
moves; they are listed here because "we looked and a zero is a measurement" is a finding a
reader is entitled to, and because the gate that reads this file has no way to tell a
reviewed decision from an unexamined one.
