"""Three cuts of the DINS file, each a partition, none of them a comparison.

Completeness is published for the whole file and per incident. The file spans a decade of
inspection practice, fifty-two counties and several classes of structure, and completeness
differs along each: fields that exist only in later forms, the two spellings of Not
Applicable that occupy non-overlapping eras, construction attributes that apply to a
residence and not to a shed. A reader planning to use ``EAVES`` needs to know it is blank
in the early years and not the late ones, and an average over the file hides that.

What a cut must not become is a league table. Nothing here compares one county against
another, no row is a rate of anything but its own cells, and no cohort is ranked. The
tests below hold three properties that keep it that way:

* **Each cut partitions the file.** Summing a cut per field and per state returns the
  file totals, so nothing is dropped into a cohort that is not published and nothing is
  counted twice. This is the assertion the issue asks for by name.
* **An absence is not a value.** A record with no county, and a record whose county cell
  carries a marker, are two cohorts and neither is a county. A recorded structure category
  outside the publisher's domain is counted in one cohort rather than given a row, because
  a row would publish a category CAL FIRE does not define as though this project had found
  one (ADR 0002).
* **An empty denominator is never a share.** A cohort holding no assessed records has
  nothing to divide by, and the page writes that in words. ``0.0%`` there would say the
  inspectors found nothing when what happened is that nobody could reach anything, which
  is the defect this whole repository is organised against.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from perimeter.coverage import (
    CohortCoverage,
    cohort_coverages,
    dins_report,
    not_applicable_spellings_by_year,
)
from perimeter.dins import (
    NOT_APPLICABLE_FIELD,
    OUTSIDE_PUBLISHED_DOMAIN,
    county_cohort_key,
    load_inspections,
    parse_inspections,
    structure_category_cohort_key,
    year_cohort_key,
)
from perimeter.render import INCIDENT_FIELD_COLUMNS, dins_page
from perimeter.schema import DINS_FIELDS

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "fixtures"
SITE_DATA = REPO_ROOT / "site" / "data"
MARKERS = REPO_ROOT / "docs" / "MARKERS.md"

#: Milliseconds since the epoch for 1 July of each year, which is what the layer
#: publishes in ``INCIDENTSTARTDATE``. Written as the literal the fixtures use rather
#: than computed, so a test cannot agree with the code by sharing its arithmetic.
JULY_2019 = 1_561_939_200_000
JULY_2021 = 1_625_097_600_000


def _rows() -> list[dict[str, object]]:
    text = (FIXTURES / "dins_postfire.sample.json").read_text(encoding="utf-8")
    loaded = json.loads(text)
    assert isinstance(loaded, list)
    return [dict(row) for row in loaded]


def _cut(rows: list[dict[str, object]], key: str) -> list[CohortCoverage]:
    keys = {
        "year": year_cohort_key,
        "county": county_cohort_key,
        "category": structure_category_cohort_key,
    }
    return cohort_coverages(parse_inspections(rows), keys[key])


def _by_label(cohorts: list[CohortCoverage]) -> dict[str, CohortCoverage]:
    return {cohort.label: cohort for cohort in cohorts}


# --------------------------------------------------------------------------------------
# The partition. The assertion the issue asks for by name.
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("cut", ["by_year", "by_county", "by_structure_category"])
def test_each_cut_sums_back_to_the_file_totals(cut: str) -> None:
    """Per field and per state, in all three states, across the whole registry.

    A cut that lost records would publish smaller denominators than the file has and
    nothing on the page would say so. Summing is the only way to know.
    """
    report = dins_report(load_inspections(FIXTURES / "dins_postfire.sample.json"))
    cohorts: list[CohortCoverage] = getattr(report, cut)
    whole = {field.name: field for field in report.fields}

    assert sum(cohort.records for cohort in cohorts) == report.records
    for name, field in whole.items():
        present = sum(
            row.present
            for cohort in cohorts
            for row in cohort.fields
            if row.name == name
        )
        unknown = sum(
            row.explicit_unknown
            for cohort in cohorts
            for row in cohort.fields
            if row.name == name
        )
        empty = sum(
            row.not_recorded
            for cohort in cohorts
            for row in cohort.fields
            if row.name == name
        )
        assert (present, unknown, empty) == (
            field.present,
            field.explicit_unknown,
            field.not_recorded,
        ), name


@pytest.mark.parametrize("cut", ["by_year", "by_county", "by_structure_category"])
def test_each_cut_sums_back_to_the_files_access_split(cut: str) -> None:
    """The assessed / inaccessible / neither split partitions each cohort too."""
    report = dins_report(load_inspections(FIXTURES / "dins_postfire.sample.json"))
    cohorts: list[CohortCoverage] = getattr(report, cut)

    assert sum(c.access.assessed for c in cohorts) == report.access.assessed
    assert sum(c.access.inaccessible for c in cohorts) == report.access.inaccessible
    assert sum(c.access.damage_not_recorded for c in cohorts) == (
        report.access.damage_not_recorded
    )
    assert sum(c.access.damage_explicit_unknown for c in cohorts) == (
        report.access.damage_explicit_unknown
    )
    for cohort in cohorts:
        assert cohort.access.total == cohort.records


def test_every_cohort_publishes_every_registered_field() -> None:
    """A cohort short a field is a row whose later values sit under the wrong heading."""
    report = dins_report(load_inspections(FIXTURES / "dins_postfire.sample.json"))
    expected = [spec.name for spec in DINS_FIELDS]
    for cut in (report.by_year, report.by_county, report.by_structure_category):
        for cohort in cut:
            assert [field.name for field in cohort.fields] == expected
            assert [row.name for row in cohort.by_access] == expected


# --------------------------------------------------------------------------------------
# Hand-computed tables over the committed fixtures.
# --------------------------------------------------------------------------------------


def test_the_year_cut_is_what_the_fixture_holds() -> None:
    """Counted by hand from the ten committed records, not read back from the code."""
    report = dins_report(load_inspections(FIXTURES / "dins_postfire.sample.json"))
    assert [(c.label, c.records) for c in report.by_year] == [("1995", 4), ("2021", 6)]

    first = report.by_year[0]
    assert first.value == "1995"
    assert (first.access.assessed, first.access.inaccessible) == (3, 1)


def test_the_county_cut_is_what_the_fixture_holds() -> None:
    report = dins_report(load_inspections(FIXTURES / "dins_postfire.sample.json"))
    assert [(c.label, c.records) for c in report.by_county] == [("Butte", 10)]


def test_the_structure_category_cut_is_what_the_fixture_holds() -> None:
    report = dins_report(load_inspections(FIXTURES / "dins_postfire.sample.json"))
    assert [(c.label, c.records) for c in report.by_structure_category] == [
        ("Infrastructure", 1),
        ("Nonresidential Commercial", 2),
        ("Other Minor Structure", 2),
        ("Single Residence", 5),
    ]


def test_recorded_cohorts_come_before_absences_and_in_order() -> None:
    rows = _rows()
    rows[0]["COUNTY"] = ""
    rows[1]["COUNTY"] = "Alpine"
    labels = [cohort.label for cohort in _cut(rows, "county")]
    assert labels == ["Alpine", "Butte", "No county recorded"]


# --------------------------------------------------------------------------------------
# An absence is not a value.
# --------------------------------------------------------------------------------------


def test_a_record_with_no_county_is_its_own_cohort_with_its_own_counts() -> None:
    """Named in the issue: it appears under "no county recorded" with its counts."""
    rows = _rows()
    rows[0]["COUNTY"] = ""
    rows[1]["COUNTY"] = ""

    cohorts = _by_label(_cut(rows, "county"))
    assert set(cohorts) == {"Butte", "No county recorded"}

    absent = cohorts["No county recorded"]
    assert absent.value is None, "an absence must not be published as a recorded value"
    assert absent.records == 2
    assert absent.access.total == 2
    damage = next(field for field in absent.fields if field.name == "DAMAGE")
    assert damage.present + damage.explicit_unknown + damage.not_recorded == 2


def test_a_cohort_of_absences_is_never_a_cohort_of_the_empty_string() -> None:
    """The label is prose and the value is the fact. A consumer reads the fact.

    A cut that published ``""`` as a county would put a county named nothing in every
    downstream group-by. ``value`` is null instead, and it is the key a machine reads.
    """
    rows = _rows()
    rows[0]["COUNTY"] = ""
    absent = next(c for c in _cut(rows, "county") if c.value is None)
    assert absent.label == "No county recorded"
    assert absent.value is None


def test_a_year_that_was_never_recorded_is_not_a_year() -> None:
    rows = _rows()
    for row in rows[:3]:
        row["INCIDENTSTARTDATE"] = None

    cohorts = _by_label(_cut(rows, "year"))
    assert "No incident start date recorded" in cohorts
    absent = cohorts["No incident start date recorded"]
    assert absent.value is None
    assert absent.records == 3
    assert sum(c.records for c in cohorts.values()) == 10


def test_a_structure_category_outside_the_published_domain_is_one_cohort() -> None:
    """ADR 0002. Counted, never dropped, and never given a row of its own.

    Two different unpublished spellings land in the same cohort, because publishing
    either as a category would say CAL FIRE defines it.
    """
    rows = _rows()
    rows[0]["STRUCTURECATEGORY"] = "Floating Home"
    rows[1]["STRUCTURECATEGORY"] = "Grain Silo"

    cohorts = _by_label(_cut(rows, "category"))
    assert OUTSIDE_PUBLISHED_DOMAIN in cohorts
    assert cohorts[OUTSIDE_PUBLISHED_DOMAIN].records == 2
    assert "Floating Home" not in cohorts
    assert "Grain Silo" not in cohorts
    assert sum(c.records for c in cohorts.values()) == 10


def test_no_empty_cohort_is_published() -> None:
    """A row of zeros reads as a finding about a county the file never names."""
    report = dins_report(load_inspections(FIXTURES / "dins_postfire.sample.json"))
    for cut in (report.by_year, report.by_county, report.by_structure_category):
        assert cut, "a cut with no cohorts at all"
        for cohort in cut:
            assert cohort.records > 0


# --------------------------------------------------------------------------------------
# An empty denominator is never a share.
# --------------------------------------------------------------------------------------


def test_a_cohort_of_only_inaccessible_records_has_no_assessed_share() -> None:
    """Named in the issue: the assessed denominator is published as none, in words.

    ``assessed_tenths_pct`` is ``None`` rather than ``0``, and the page renders that in
    words. A zero would say the inspectors recorded nothing about these structures, when
    what happened is that nobody could walk up to one.
    """
    rows = _rows()
    for row in rows:
        row["INCIDENTSTARTDATE"] = JULY_2019
    rows[0]["INCIDENTSTARTDATE"] = JULY_2021
    rows[0]["DAMAGE"] = "Inaccessible"

    cohorts = _by_label(_cut(rows, "year"))
    lonely = cohorts["2021"]
    assert lonely.records == 1
    assert lonely.access.assessed == 0
    assert lonely.access.inaccessible == 1

    for row in lonely.by_access:
        assert row.assessed_total == 0
        assert row.assessed_tenths_pct is None, (
            f"{row.name} published a share over an empty assessed population"
        )
        assert row.inaccessible_total == 1

    markup = dins_page(
        dins_report(parse_inspections(rows)),
        is_fixture=True,
    )
    # The row itself, not the table. `"0.0%" not in table` was the first form of this
    # assertion and it is wrong twice over: `100.0%` contains `0.0%`, so a healthy
    # cohort fails it, and a percentage in some other row would fail it too. The claim
    # is about this cohort's cells.
    table = markup.split('id="cap-by-year"')[1].split("</table>")[0]
    row = table.split('<th scope="row" class="name">2021</th>')[1].split("</tr>")[0]
    assert "%" not in row, row
    assert row.count("no records") == len(
        [
            name
            for name, _ in INCIDENT_FIELD_COLUMNS
            if name in {f.name for f in DINS_FIELDS}
        ]
    )


def test_the_three_access_populations_account_for_every_record_in_a_cohort() -> None:
    """ADR 0007: the population a split leaves out is published, not dropped."""
    rows = _rows()
    rows[0]["DAMAGE"] = None
    report = dins_report(parse_inspections(rows))
    for cohort in report.by_county:
        for row in cohort.by_access:
            assert row.counted_records == cohort.records


# --------------------------------------------------------------------------------------
# The marker era claim, measured rather than typed.
# --------------------------------------------------------------------------------------


def test_the_spelling_cut_counts_only_declared_recorded_absences() -> None:
    rows = _rows()
    for row in rows:
        row[NOT_APPLICABLE_FIELD] = "NA"
    rows[0][NOT_APPLICABLE_FIELD] = "<30'"

    cohorts = not_applicable_spellings_by_year(parse_inspections(rows))
    counted = sum(sum(c.spellings.values()) for c in cohorts)
    assert counted == 9, "a recorded distance was counted as a Not Applicable spelling"
    assert {s for c in cohorts for s in c.spellings} == {"NA"}


def test_the_spelling_cut_partitions_the_same_years_as_the_year_cut() -> None:
    report = dins_report(load_inspections(FIXTURES / "dins_postfire.sample.json"))
    assert [c.label for c in report.not_applicable_spellings] == [
        c.label for c in report.by_year
    ]


def test_the_published_era_claim_is_what_the_published_file_holds() -> None:
    """`docs/MARKERS.md` rests a marker decision on two numbers and an era boundary.

    They were measured once by a person and typed into a document, which is the shape
    this repository refuses everywhere else. They are computed and published now, and
    this holds the document to the artifact in both directions: the sentence must state
    the measured counts, and the boundary the sentence claims must still hold in the
    file.
    """
    artifact = json.loads(
        (SITE_DATA / "dins-coverage.json").read_text(encoding="utf-8")
    )
    published = artifact["not_applicable_spellings_by_year"]
    assert published["field"] == NOT_APPLICABLE_FIELD

    totals: dict[str, int] = {}
    years: dict[str, set[str]] = {}
    for row in published["by_year"]:
        for spelling, count in row["spellings"].items():
            totals[spelling] = totals.get(spelling, 0) + count
            years.setdefault(spelling, set()).add(row["label"])

    document = " ".join(MARKERS.read_text(encoding="utf-8").split())
    for spelling, count in sorted(totals.items()):
        assert f"{count:,} `{spelling}` records" in document, (
            f"docs/MARKERS.md does not state the measured count of {spelling!r} "
            f"({count:,}); the sentence and the file disagree"
        )

    assert years["N/A"] <= {"2018", "2019"}, years["N/A"]
    assert min(years["NA"]) >= "2020", years["NA"]
    assert not (years["N/A"] & years["NA"]), (
        "a year carries both spellings, and docs/MARKERS.md says they fall on opposite "
        "sides of one year"
    )


# --------------------------------------------------------------------------------------
# The page.
# --------------------------------------------------------------------------------------


def test_the_page_publishes_all_three_cuts_and_the_spellings() -> None:
    report = dins_report(load_inspections(FIXTURES / "dins_postfire.sample.json"))
    markup = dins_page(report, is_fixture=True)
    for caption in ("cap-by-year", "cap-by-county", "cap-by-category", "cap-spellings"):
        assert f'id="{caption}"' in markup, caption
        assert f'aria-labelledby="{caption}"' in markup, caption


def test_every_cut_table_is_a_reachable_scroll_region_with_row_headers() -> None:
    """A container that scrolls and cannot be focused is a WCAG 2.1.1 failure.

    The browser half of the accessibility gate found exactly this once, on the tables
    that were already here; these are the same shape and get the same treatment.
    """
    report = dins_report(load_inspections(FIXTURES / "dins_postfire.sample.json"))
    markup = dins_page(report, is_fixture=True)
    for caption in ("cap-by-year", "cap-by-county", "cap-by-category", "cap-spellings"):
        section = markup.split(f'aria-labelledby="{caption}"')[0]
        assert section.rstrip().endswith('<section class="scroll tall" tabindex="0"'), (
            caption
        )
    assert markup.count('<th scope="row" class="name">') >= len(report.by_county)


def test_the_page_names_the_denominator_the_field_columns_use() -> None:
    """A share whose population is not stated is a number a reader cannot use."""
    report = dins_report(load_inspections(FIXTURES / "dins_postfire.sample.json"))
    markup = " ".join(dins_page(report, is_fixture=True).split())
    assert "share of that cohort's <strong>assessed</strong> records" in markup
    assert "Cohorts with no records are not published at all" in markup
