"""PROVENANCE.md must not drift from the reviewed record in sources.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from perimeter.sources import SOURCES, Source

ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = (ROOT / "PROVENANCE.md").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


def flatten(markdown: str) -> str:
    """One long line, blockquote markers gone, so a wrapped quote still matches."""
    return " ".join(markdown.replace("\n> ", " ").split())


PROVENANCE_FLAT = flatten(PROVENANCE)


@pytest.mark.parametrize("source", SOURCES, ids=lambda s: s.key)
def test_provenance_states_where_the_file_came_from(source: Source) -> None:
    for value in (source.landing_page, source.endpoint, source.layer, source.licence):
        assert value in PROVENANCE, (
            f"{source.key}: {value!r} missing from PROVENANCE.md"
        )


@pytest.mark.parametrize("source", SOURCES, ids=lambda s: s.key)
def test_provenance_states_what_was_acquired(source: Source) -> None:
    assert source.retrieved in PROVENANCE
    assert source.sha256 in PROVENANCE
    assert f"{source.record_count:,}" in PROVENANCE
    assert f"{source.raw_bytes:,}" in PROVENANCE
    assert source.raw_file in PROVENANCE


@pytest.mark.parametrize("source", SOURCES, ids=lambda s: s.key)
def test_every_measurement_names_the_caveat_it_answers(source: Source) -> None:
    """A measurement without a published limitation behind it does not belong here."""
    assert source.caveats
    for caveat in source.caveats:
        assert caveat.topic
        assert caveat.quote
        assert caveat.measured_as


@pytest.mark.parametrize("source", SOURCES, ids=lambda s: s.key)
def test_the_quotes_are_reproduced_in_provenance(source: Source) -> None:
    """A distinctive clause from each quote must appear verbatim in the document."""
    for caveat in source.caveats:
        clause = " ".join(max(caveat.quote.split(". "), key=len)[:60].split()).strip()
        assert clause in PROVENANCE_FLAT, f"{source.key}/{caveat.topic}: {clause!r}"


def test_provenance_records_what_is_excluded() -> None:
    assert "## Exclusions" in PROVENANCE
    assert "geometry" in PROVENANCE.lower()


def test_provenance_records_the_manual_route_if_an_endpoint_declines() -> None:
    assert "AcquisitionBlocked" in PROVENANCE
    assert "by hand" in PROVENANCE


def test_the_fixtures_are_declared_as_hand_written() -> None:
    assert "hand-written, not sampled" in PROVENANCE


@pytest.mark.parametrize(
    "document", [PROVENANCE, README], ids=["PROVENANCE.md", "README.md"]
)
def test_the_prose_carries_no_em_dashes(document: str) -> None:
    assert "—" not in document


def test_the_readme_says_the_project_is_unofficial() -> None:
    assert "Not affiliated with or endorsed by CAL FIRE" in README
