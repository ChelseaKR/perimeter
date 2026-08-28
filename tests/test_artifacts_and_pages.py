"""Determinism, the fixture flag, and what the pages are allowed to print."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from perimeter.cli import build_site, main
from perimeter.coverage import (
    DinsReport,
    PerimeterReport,
    dins_report,
    perimeter_report,
)
from perimeter.dins import load_inspections
from perimeter.perimeters import load_perimeters
from perimeter.render import dins_page, index_page, perimeters_page

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
FRAP_FIXTURE = FIXTURES / "frap_perimeters.sample.json"
DINS_FIXTURE = FIXTURES / "dins_postfire.sample.json"


@pytest.fixture(scope="module")
def frap() -> PerimeterReport:
    return perimeter_report(load_perimeters(FRAP_FIXTURE))


@pytest.fixture(scope="module")
def dins() -> DinsReport:
    return dins_report(load_inspections(DINS_FIXTURE))


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("site")
    build_site(
        perimeters_source=FRAP_FIXTURE,
        dins_source=DINS_FIXTURE,
        out_dir=out,
        is_fixture=True,
    )
    return out


def test_the_same_inputs_produce_byte_identical_output(tmp_path: Path) -> None:
    def build_into(name: str) -> dict[str, bytes]:
        out = tmp_path / name
        written = build_site(
            perimeters_source=FRAP_FIXTURE,
            dins_source=DINS_FIXTURE,
            out_dir=out,
            is_fixture=True,
        )
        return {path.name: path.read_bytes() for path in written}

    assert build_into("first") == build_into("second")


def test_a_fixture_build_publishes_no_acquisition_facts(built: Path) -> None:
    """Fixture output must never pass itself off as CAL FIRE's real files."""
    for name in ("perimeters-coverage.json", "dins-coverage.json"):
        payload = json.loads((built / "data" / name).read_text(encoding="utf-8"))
        assert payload["is_fixture"] is True
        source = payload["source"]
        for key in (
            "retrieved",
            "version",
            "acquired_record_count",
            "acquired_bytes",
            "acquired_sha256",
        ):
            assert source[key] is None, f"{name}.{key}"


def test_a_real_build_publishes_the_reviewed_acquisition_facts(tmp_path: Path) -> None:
    build_site(
        perimeters_source=FRAP_FIXTURE,
        dins_source=DINS_FIXTURE,
        out_dir=tmp_path,
        is_fixture=False,
    )
    payload = json.loads(
        (tmp_path / "data" / "perimeters-coverage.json").read_text(encoding="utf-8")
    )
    assert payload["is_fixture"] is False
    assert payload["source"]["retrieved"] == "2026-08-07"
    assert len(payload["source"]["acquired_sha256"]) == 64


def test_no_wall_clock_leaks_into_an_artifact(built: Path) -> None:
    """Any date in the payload must be a reviewed constant, not today."""
    text = (built / "data" / "perimeters-coverage.json").read_text(encoding="utf-8")
    payload = json.loads(text)
    assert payload["source"]["retrieved"] is None
    for match in re.findall(r"\d{4}-\d{2}-\d{2}", text):
        pytest.fail(f"unexpected date in a fixture artifact: {match}")


def test_every_field_publishes_all_three_counts(built: Path) -> None:
    payload = json.loads((built / "data" / "dins-coverage.json").read_text("utf-8"))
    assert payload["fields"]
    for field in payload["fields"]:
        for key in ("present", "explicit_unknown", "not_recorded", "total"):
            assert key in field, f"{field['name']} is missing {key}"
        assert (
            field["present"] + field["explicit_unknown"] + field["not_recorded"]
            == field["total"]
        )


def test_the_incident_matrix_documents_its_own_ordering(built: Path) -> None:
    payload = json.loads((built / "data" / "dins-coverage.json").read_text("utf-8"))
    assert payload["field_state_order"] == [
        "present",
        "explicit_unknown",
        "not_recorded",
    ]
    incident = payload["incidents_detail"][0]
    assert len(incident["fields"]["DAMAGE"]) == 3


def test_pages_are_written(built: Path) -> None:
    for name in ("index.html", "perimeters.html", "dins.html"):
        assert (built / name).read_text(encoding="utf-8").startswith("<!doctype html>")


@pytest.mark.parametrize("name", ["index.html", "perimeters.html", "dins.html"])
def test_every_page_says_it_is_unofficial(built: Path, name: str) -> None:
    text = built / name
    assert "Not affiliated with or endorsed by CAL FIRE" in text.read_text("utf-8")


@pytest.mark.parametrize("name", ["index.html", "perimeters.html", "dins.html"])
def test_a_fixture_page_says_so_on_its_face(built: Path, name: str) -> None:
    assert "Fixture build" in (built / name).read_text(encoding="utf-8")


def test_a_page_quotes_the_publisher_rather_than_paraphrasing(
    frap: PerimeterReport, dins: DinsReport
) -> None:
    perimeters_html = perimeters_page(frap, is_fixture=True)
    dins_html = dins_page(dins, is_fixture=True)
    assert "it is still incomplete" in perimeters_html
    assert "Attributes with null values could not be determined" in dins_html


def test_a_share_over_nothing_is_printed_as_words_not_as_a_number() -> None:
    """An empty report must not render 0% anywhere a rate does not exist."""
    html = perimeters_page(perimeter_report([]), is_fixture=True)
    assert "no records" in html
    assert "0.0%" not in html


def test_the_pages_carry_no_em_dashes(built: Path) -> None:
    for path in sorted(built.glob("*.html")):
        assert "—" not in path.read_text(encoding="utf-8"), path.name


def test_the_index_names_all_three_states(
    frap: PerimeterReport, dins: DinsReport
) -> None:
    html = index_page(frap, dins, is_fixture=True)
    for label in ("Recorded value", "Recorded as unknown", "Empty cell"):
        assert label in html


def test_the_cli_builds_a_site(tmp_path: Path) -> None:
    code = main(
        [
            "--perimeters",
            str(FRAP_FIXTURE),
            "--dins",
            str(DINS_FIXTURE),
            "--out",
            str(tmp_path / "site"),
            "--fixture",
        ]
    )
    assert code == 0
    assert (tmp_path / "site" / "index.html").exists()
    assert (tmp_path / "site" / "data" / "dins-coverage.json").exists()


def test_a_bar_over_nothing_is_words_rather_than_an_empty_bar() -> None:
    from perimeter.render import state_bar

    assert "no records" in state_bar(0, 0, 0)
    assert '<i class="b-present"' in state_bar(1, 0, 0)


def test_the_damage_table_labels_the_two_non_value_states() -> None:
    """Neither state occurs in the published file today; the page must still name
    them correctly rather than printing a raw key if one ever appears."""
    from dataclasses import replace

    report = dins_report(load_inspections(DINS_FIXTURE))
    with_gaps = replace(
        report, damage={**report.damage, "not_recorded": 3, "explicit_unknown": 2}
    )
    html = dins_page(with_gaps, is_fixture=True)
    assert "Empty cell" in html
    assert "A marker was recorded in place of a damage value." in html
    assert "not_recorded<" not in html


def test_a_bar_segment_over_nothing_is_zero_width_not_a_division_error() -> None:
    """Defensive: state_bar already guards this, so the guard needs its own test."""
    from perimeter.render import _width

    assert _width(0, 0) == "0"
    assert _width(1, 2) == "50.00"


def test_the_access_table_publishes_the_population_it_leaves_out(built: Path) -> None:
    """Two of three populations are shown; all three are published, so nothing vanishes."""
    payload = json.loads(
        (built / "data" / "dins-coverage.json").read_text(encoding="utf-8")
    )
    for row in payload["completeness_by_access"]:
        counted = (
            row["assessed_total"]
            + row["inaccessible_total"]
            + row["undetermined_total"]
        )
        assert counted == payload["records"], (
            f"{row['name']}: the access table accounts for {counted} of "
            f"{payload['records']} records"
        )


def test_the_page_says_what_the_two_access_columns_are_counted_over(
    built: Path,
) -> None:
    html = (built / "dins.html").read_text(encoding="utf-8")
    assert "which between them is every record in this file" in html
    assert "There are none here." in html


def test_the_page_names_the_records_the_access_columns_leave_out() -> None:
    """No record in the published file lands here, so the sentence needs its own test."""
    from dataclasses import replace

    report = dins_report(load_inspections(DINS_FIXTURE))
    with_gap = replace(
        report,
        by_access=[
            replace(row, undetermined_present=1, undetermined_total=3)
            for row in report.by_access
        ],
    )
    html = dins_page(with_gap, is_fixture=True)
    assert "are in neither, because their damage field records nothing" in html
    assert "which between them is every record in this file" not in html
