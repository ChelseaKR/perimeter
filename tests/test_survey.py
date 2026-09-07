"""The survey reports what a retrieval holds, and decides nothing about it.

Two properties carry most of the weight here.

The first is that the survey and the build read **one list**. The build refuses an
undeclared missing-data marker; the survey exists so a person can see every one of them
before the build refuses the first. If the survey had its own copy of the rule, it would
go quiet exactly when the rule moved, and a refresh would still be driven one crash at a
time. `test_the_survey_finds_exactly_what_the_build_refuses` holds them together over
every value the fixtures contain plus a planted set.

The second is that nothing the survey withholds is published as nothing. A field above
the listing bound reports the bound, not an empty list. A field with no published domain
reports `null`, not zero values outside one. A numeric field with no numbers has no zero
share, not a zero one. Those are the same three distinctions the artifacts already make,
and this module is a third place they can be lost.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from perimeter.cells import SUSPECTED_SENTINELS, SentinelDriftError, normalize_marker
from perimeter.records import load_rows
from perimeter.schema import (
    DINS_FIELDS,
    DINS_FIELDS_BY_NAME,
    DINS_REQUIRED_COLUMNS,
    FRAP_FIELDS,
    FieldSpec,
    SchemaDriftError,
)
from perimeter.survey import (
    LISTING_BOUND,
    ZERO_SHARE_REPORTING_FLOOR_TENTHS_PCT,
    FieldSurvey,
    SourceSurvey,
    ZeroReading,
    console,
    main,
    markdown,
    survey_field,
    survey_file,
    survey_rows,
    write,
)

ROOT = Path(__file__).resolve().parents[1]
DINS_FIXTURE = ROOT / "fixtures" / "dins_postfire.sample.json"
FRAP_FIXTURE = ROOT / "fixtures" / "frap_perimeters.sample.json"


def dins_rows() -> list[dict[str, object]]:
    return load_rows(DINS_FIXTURE)


def surveyed(rows: list[Mapping[str, object]]) -> SourceSurvey:
    return survey_rows(
        rows, specs=DINS_FIELDS, required=DINS_REQUIRED_COLUMNS, source="dins"
    )


def field_of(survey: SourceSurvey, name: str) -> FieldSurvey:
    for field in survey.fields:
        if field.name == name:
            return field
    raise AssertionError(f"{name} was not surveyed")


# --------------------------------------------------------------------------------------
# One list, shared with the gate
# --------------------------------------------------------------------------------------


def test_the_survey_finds_exactly_what_the_build_refuses() -> None:
    """A candidate is reported if and only if `classify` would stop the build on it.

    The planted values are deliberately drawn from the sentinel vocabulary itself rather
    than invented, so this compares the two readers over the values that actually decide
    the question rather than over a fixture that happens to be clean.
    """
    planted = [*sorted(SUSPECTED_SENTINELS), "Road", "No Damage", "0", "1975", "Butte"]
    for spec in (*DINS_FIELDS, *FRAP_FIELDS):
        for text in planted:
            refused = False
            try:
                spec.classify(text, where="probe")
            except SentinelDriftError:
                refused = True
            except SchemaDriftError:
                # A numeric field refusing a non-number is a different rule, and the
                # survey is not claiming to mirror it.
                continue
            assert (spec.undeclared_marker(text) is not None) is refused, (
                f"{spec.name}: undeclared_marker and classify disagree about {text!r}"
            )


def test_the_sentinel_refusal_names_the_survey_command() -> None:
    spec = DINS_FIELDS_BY_NAME["STREETTYPE"]
    with pytest.raises(SentinelDriftError) as caught:
        spec.classify("NA", where="probe")
    assert "perimeter.survey" in str(caught.value)


# --------------------------------------------------------------------------------------
# Candidates
# --------------------------------------------------------------------------------------


def test_a_marker_the_field_has_not_reviewed_is_a_candidate_with_its_count() -> None:
    """`STREETTYPE` declares `n/a`, `unk` and `-`; it has never declared `na`.

    That non-overlap is the case docs/MARKERS.md records for the `NA` and `N/A`
    spellings, and it is what a refresh hits first.
    """
    rows = dins_rows()
    rows[0]["STREETTYPE"] = "NA"
    rows[1]["STREETTYPE"] = "NA"
    field = field_of(surveyed(rows), "STREETTYPE")
    assert [(c.value, c.normalized, c.count) for c in field.candidates] == [
        ("NA", "na", 2)
    ]
    assert field.needs_review is True
    assert all(c.as_json()["basis"] == "unreviewed" for c in field.candidates)


def test_a_marker_the_field_has_reviewed_is_not_a_candidate() -> None:
    rows = dins_rows()
    rows[0]["CITY"] = "N/A"  # CITY declares n/a, na, none and unknown
    assert field_of(surveyed(rows), "CITY").candidates == ()


def test_a_published_recorded_absence_is_not_a_candidate() -> None:
    """`None` is a published street type. It is a finding, not an absent value."""
    rows = dins_rows()
    for row in rows:
        row["STREETTYPE"] = "None"
    assert field_of(surveyed(rows), "STREETTYPE").candidates == ()


def test_a_field_whose_values_are_all_in_its_published_domain_has_no_candidates() -> (
    None
):
    field = field_of(surveyed(dins_rows()), "DAMAGE")
    assert field.candidates == ()
    assert field.outside_domain == ()
    assert field.needs_review is False


def test_the_console_says_no_candidates_rather_than_printing_nothing() -> None:
    survey = survey_rows(
        load_rows(FRAP_FIXTURE),
        specs=FRAP_FIELDS,
        required=(),
        source="perimeters",
    )
    assert survey.needs_review == ()
    assert "no candidates" in console([survey])


# --------------------------------------------------------------------------------------
# Nothing withheld is published as nothing
# --------------------------------------------------------------------------------------


def test_no_published_domain_is_null_and_not_an_empty_list() -> None:
    """ADR-0010, in the survey. `[]` would say the comparison ran and found nothing."""
    survey = surveyed(dins_rows())
    free_text = field_of(survey, "SITEADDRESS")
    assert DINS_FIELDS_BY_NAME["SITEADDRESS"].domain_values is None
    assert free_text.outside_domain is None
    assert free_text.as_json()["outside_published_domain"] is None

    constrained = field_of(survey, "DAMAGE")
    assert constrained.as_json()["outside_published_domain"] == []


def test_a_value_outside_a_published_domain_is_listed_with_its_count() -> None:
    rows = dins_rows()
    rows[0]["DAMAGE"] = "Scorched"
    field = field_of(surveyed(rows), "DAMAGE")
    assert [(v.value, v.count) for v in field.outside_domain or ()] == [("Scorched", 1)]


def test_a_field_above_the_listing_bound_says_so_instead_of_listing_nothing() -> None:
    spec = FieldSpec("F", "Field")
    rows: list[Mapping[str, object]] = [
        {"F": f"value {index}"} for index in range(LISTING_BOUND + 3)
    ]
    field = survey_field(rows, spec)
    assert field.distinct == LISTING_BOUND + 3
    assert field.values is None
    payload = field.as_json()
    assert payload["values_listed"] is False
    assert "values" not in payload
    assert str(LISTING_BOUND) in str(payload["values_withheld_because"])


def test_a_field_at_the_listing_bound_is_still_listed() -> None:
    spec = FieldSpec("F", "Field")
    rows: list[Mapping[str, object]] = [
        {"F": f"value {index}"} for index in range(LISTING_BOUND)
    ]
    field = survey_field(rows, spec)
    assert field.values is not None
    assert len(field.values) == LISTING_BOUND
    assert field.as_json()["values_listed"] is True


def test_a_numeric_field_with_no_numbers_has_no_zero_share() -> None:
    """Nothing to divide by is not zero percent. It does not exist."""
    reading = ZeroReading(zeros=0, declared_zeros=0, numbers=0)
    assert reading.tenths_pct is None
    assert reading.undeclared_tenths_pct is None
    assert reading.worth_reviewing is False


def test_a_field_that_is_not_numeric_reports_no_zero_reading_at_all() -> None:
    assert field_of(surveyed(dins_rows()), "DAMAGE").zeros is None


# --------------------------------------------------------------------------------------
# Zeros
# --------------------------------------------------------------------------------------


def test_a_numeric_field_whose_zeros_nobody_has_ruled_on_is_flagged() -> None:
    rows = dins_rows()
    rows[0]["ASSESSEDIMPROVEDVALUE"] = 0
    rows[1]["ASSESSEDIMPROVEDVALUE"] = 0
    field = field_of(surveyed(rows), "ASSESSEDIMPROVEDVALUE")
    assert field.zeros is not None
    assert field.zeros.undeclared_zeros == 2
    assert field.zeros.declared_zeros == 0
    assert field.zeros.worth_reviewing is True
    assert field.needs_review is True


def test_a_zero_the_registry_has_already_reviewed_is_reported_and_not_flagged() -> None:
    """`YEARBUILT` declares the literal `0`. Asking about it again every run is noise.

    This is the case issue #66 named as the day-one finding. It was reviewed in the
    meantime, and the survey has to be able to tell a reviewed judgment from an open
    question or a reader learns to skip the section.
    """
    rows = dins_rows()
    rows[0]["YEARBUILT"] = 0
    field = field_of(surveyed(rows), "YEARBUILT")
    assert field.zeros is not None
    assert field.zeros.zeros == 1
    assert field.zeros.declared_zeros == 1
    assert field.zeros.undeclared_zeros == 0
    assert field.zeros.worth_reviewing is False
    assert field.needs_review is False


def test_the_zero_floor_is_a_reporting_threshold_and_nothing_is_dropped_by_it() -> None:
    """A field under the floor still publishes its zero count; it is only not flagged."""
    spec = FieldSpec("N", "Number", numeric=True)
    rows: list[Mapping[str, object]] = [{"N": 0}] + [
        {"N": index + 1} for index in range(999)
    ]
    field = survey_field(rows, spec)
    assert field.zeros is not None
    assert field.zeros.zeros == 1
    assert field.zeros.undeclared_tenths_pct == 1
    assert field.zeros.undeclared_tenths_pct < ZERO_SHARE_REPORTING_FLOOR_TENTHS_PCT
    assert field.zeros.worth_reviewing is False
    assert field.as_json()["recorded_zeros"] is not None


# --------------------------------------------------------------------------------------
# The survey is not a way around schema drift
# --------------------------------------------------------------------------------------


def test_a_column_missing_from_the_last_row_is_refused_not_surveyed_as_empty() -> None:
    """A column that vanishes part way down a file is intact in the first row.

    Surveying it as a column every later row left blank would report a field the agency
    stopped publishing as a field the agency left empty, which is the one reading this
    project exists to refuse.
    """
    rows = dins_rows()
    del rows[-1]["EAVES"]
    with pytest.raises(SchemaDriftError, match="EAVES"):
        surveyed(rows)


def test_an_empty_file_surveys_as_zero_rows_rather_than_refusing() -> None:
    survey = surveyed([])
    assert survey.rows == 0
    assert survey.needs_review == ()
    assert all(field.rows == 0 and field.distinct == 0 for field in survey.fields)


def test_a_source_with_no_registry_is_refused_by_name() -> None:
    with pytest.raises(SchemaDriftError, match="no field registry"):
        survey_file(DINS_FIXTURE, source="counties")


# --------------------------------------------------------------------------------------
# Ordering and byte stability
# --------------------------------------------------------------------------------------


def test_numbers_sort_as_numbers_and_text_after_them() -> None:
    spec = FieldSpec("N", "Number")
    rows: list[Mapping[str, object]] = [
        {"N": "10"},
        {"N": "9"},
        {"N": "alpha"},
        {"N": "2"},
        {"N": "Beta"},
    ]
    field = survey_field(rows, spec)
    assert field.values is not None
    assert [value.value for value in field.values] == ["2", "9", "10", "Beta", "alpha"]


def test_the_survey_is_byte_identical_across_interpreters(tmp_path: Path) -> None:
    """Across processes, under different hash seeds, over a fixture with real breadth.

    Twice inside one interpreter proves nothing: set and dict iteration over the same
    strings is stable within a process, so a dropped `sorted` would be invisible. The
    fixture is the whole DINS sample rather than one crafted row, because a field with
    one value has no order to get wrong.
    """
    outputs = []
    for seed in ("0", "1", "524287"):
        out = tmp_path / f"seed-{seed}"
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-m",
                "perimeter.survey",
                "--dins",
                str(DINS_FIXTURE),
                "--perimeters",
                str(FRAP_FIXTURE),
                "--out",
                str(out),
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        outputs.append(
            (
                (out / "survey.json").read_bytes(),
                (out / "survey.md").read_bytes(),
            )
        )
    assert len(set(outputs)) == 1


def test_the_fixture_holds_enough_distinct_values_for_order_to_be_observable() -> None:
    """Guards the determinism test above against becoming vacuous.

    A fixture whose every measured field holds one value would pass that test with every
    `sorted` removed. This pins the property the test depends on rather than trusting it.
    """
    survey = surveyed(dins_rows())
    assert sum(1 for field in survey.fields if field.distinct > 1) >= 8


# --------------------------------------------------------------------------------------
# What gets written
# --------------------------------------------------------------------------------------


def test_the_draft_marks_every_candidate_unreviewed() -> None:
    rows = dins_rows()
    rows[0]["STREETTYPE"] = "NA"
    draft = markdown([surveyed(rows)])
    assert "basis: unreviewed" in draft
    assert "`NA`" in draft
    assert "Nothing here is declared" in draft


def test_the_draft_says_so_when_a_source_has_no_candidates() -> None:
    draft = markdown(
        [
            survey_rows(
                load_rows(FRAP_FIXTURE),
                specs=FRAP_FIELDS,
                required=(),
                source="perimeters",
            )
        ]
    )
    assert "No candidates." in draft


def test_the_artifact_says_it_declares_nothing(tmp_path: Path) -> None:
    written = write([surveyed(dins_rows())], tmp_path / "out")
    assert [path.name for path in written] == ["survey.json", "survey.md"]
    payload: dict[str, Any] = json.loads(written[0].read_text(encoding="utf-8"))
    assert "decides nothing" in str(payload["declares_nothing"])
    assert payload["listing_bound"] == LISTING_BOUND
    assert (
        payload["zero_share_reporting_floor_tenths_pct"]
        == ZERO_SHARE_REPORTING_FLOOR_TENTHS_PCT
    )


def test_the_survey_writes_nothing_into_the_repository(tmp_path: Path) -> None:
    """It is a review aid. No part of the build reads it, and it edits no registry."""
    before = {spec.name: spec.unknown_markers for spec in DINS_FIELDS}
    rows = dins_rows()
    rows[0]["STREETTYPE"] = "NA"
    write([surveyed(rows)], tmp_path / "out")
    assert {spec.name: spec.unknown_markers for spec in DINS_FIELDS} == before


def test_main_needs_at_least_one_source(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["--out", str(tmp_path)])
    assert caught.value.code == 2


def test_main_surveys_both_sources_and_writes_both_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "survey"
    assert (
        main(
            [
                "--dins",
                str(DINS_FIXTURE),
                "--perimeters",
                str(FRAP_FIXTURE),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    printed = capsys.readouterr().out
    assert "dins: 10 rows" in printed
    assert "perimeters: 10 rows" in printed
    assert (out / "survey.json").is_file()
    assert (out / "survey.md").is_file()


def test_main_honours_a_narrower_listing_bound(tmp_path: Path) -> None:
    out = tmp_path / "survey"
    assert (
        main(["--dins", str(DINS_FIXTURE), "--out", str(out), "--listing-bound", "1"])
        == 0
    )
    payload = json.loads((out / "survey.json").read_text(encoding="utf-8"))
    withheld = [
        field
        for field in payload["sources"][0]["fields"]
        if field["values_listed"] is False
    ]
    assert withheld, "a bound of one should withhold at least one listing"
    assert all("values" not in field for field in withheld)


def test_survey_file_reads_a_real_source_by_name() -> None:
    survey = survey_file(FRAP_FIXTURE, source="perimeters")
    assert survey.source == "perimeters"
    assert survey.rows == 10


def test_normalize_is_the_one_the_registry_uses() -> None:
    """The candidate's normalized form is the form the registry is declared in."""
    rows = dins_rows()
    rows[0]["STREETTYPE"] = "  Na  "
    field = field_of(surveyed(rows), "STREETTYPE")
    assert [c.normalized for c in field.candidates] == [normalize_marker("Na")]
