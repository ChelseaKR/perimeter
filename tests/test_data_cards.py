"""DG-01 and DG-04: a card per source, and a retrieval that goes stale fails the build.

`PROVENANCE.md` already restated `src/perimeter/sources.py` for a reader and
`tests/test_provenance.py` already held the two together. What neither carried was the
two rows the data-governance standard asks for and this project had never written down:
which tier the data is, and how long a retrieval describes the file it came from.

The second is the one with teeth. Every figure these pages publish is a count of a file
downloaded on one day. The pages say the date, which is honest and is not the same thing
as noticing: a reader who does not check the date is served a description of a file that
has moved on, and nothing anywhere raises its hand. DG-04 calls that a staleness alarm
and makes it an AUTO-GATE. This is it.

Where the clock is allowed to be matters here. It is not in the artifacts, because
`README.md` promises the same inputs produce byte-identical output and a page computing
its own staleness would need a wall clock to do it. So the artifacts publish the
retrieval date and `staleness_sla_days`, which are facts, and the subtraction happens
here, in a gate, where a clock is exactly the right thing to have.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from perimeter.sources import SOURCES, Source

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_CARD_FIELDS = (
    "| Source |",
    "| Licence |",
    "| Fetch and refresh cadence |",
    "| Fetch timestamp |",
    "| Tier |",
    "| Known limitations |",
    "| Retention |",
)
"""The seven rows DATA-GOVERNANCE-STANDARD section 1 requires of a data card."""


def card_text(source: Source) -> str:
    return (ROOT / source.card).read_text(encoding="utf-8")


# --- DG-01: one card per declared source ----------------------------------------------


@pytest.mark.parametrize("source", SOURCES, ids=lambda s: s.key)
def test_every_declared_source_has_a_data_card(source: Source) -> None:
    """Enumerated against the declared source list, not against what is on disk.

    A directory listing would pass a repository that added a source and no card. This
    reads `SOURCES` and asks for a file per entry.
    """
    path = ROOT / source.card
    assert path.is_file(), f"{source.key}: no data card at {source.card} (DG-01)"
    assert path.stat().st_size > 0, f"{source.card} is empty"


@pytest.mark.parametrize("source", SOURCES, ids=lambda s: s.key)
@pytest.mark.parametrize("field", REQUIRED_CARD_FIELDS)
def test_every_data_card_carries_every_required_row(source: Source, field: str) -> None:
    assert field in card_text(source), f"{source.card}: no {field.strip('| ')!r} row"


@pytest.mark.parametrize("source", SOURCES, ids=lambda s: s.key)
def test_the_card_restates_the_reviewed_record_without_drifting_from_it(
    source: Source,
) -> None:
    """The card is prose over `sources.py`, so it says the same things or it is wrong."""
    text = card_text(source)
    for value in (
        source.title,
        source.publisher,
        source.landing_page,
        source.endpoint,
        source.licence,
        source.version,
        source.retrieved,
        source.sha256,
        source.tier,
        source.refresh_cadence,
        f"{source.staleness_sla_days} days",
        f"{source.record_count:,}",
        f"{source.raw_bytes:,}",
    ):
        assert value in text, f"{source.card}: {value!r} is not in the card"


@pytest.mark.parametrize("source", SOURCES, ids=lambda s: s.key)
def test_the_card_says_the_sla_is_this_projects_declaration(source: Source) -> None:
    """Neither publisher promised a schedule, and the card must not imply one did."""
    assert "this project's declaration" in card_text(source)


def test_the_cards_carry_no_em_dashes() -> None:
    for source in SOURCES:
        assert "—" not in card_text(source), source.card


# --- DG-04: the staleness alarm --------------------------------------------------------


def stale_sources(
    sources: tuple[Source, ...], today: date
) -> list[tuple[str, int, int]]:
    """Sources whose retrieval is older than the SLA their card states.

    Returns ``(key, days since retrieval, SLA)`` per stale source. A pure function of a
    date so that it can be run against a date it must reject, which is what ADR-0004
    asks of a gate.
    """
    stale = []
    for source in sources:
        age = (today - date.fromisoformat(source.retrieved)).days
        if age > source.staleness_sla_days:
            stale.append((source.key, age, source.staleness_sla_days))
    return stale


def test_no_published_retrieval_is_older_than_the_sla_its_card_states() -> None:
    """DG-04. This gate is meant to fire one day, and firing is it working.

    When it does, the fix is to re-acquire (`uv run python -m perimeter.acquire`), rebuild
    `site/` and update `src/perimeter/sources.py`, or to move the SLA deliberately with a
    reason in the card. What it must not become is a number quietly raised to make a
    build green, which is the same move `CONTRIBUTING.md` forbids for a marker set.
    """
    stale = stale_sources(SOURCES, date.today())
    assert stale == [], (
        "these retrievals are older than the staleness SLA their data card states, so "
        "the published counts describe files that have moved on: "
        + "; ".join(
            f"{key} was retrieved {age} days ago against an SLA of {sla}"
            for key, age, sla in stale
        )
        + ". Re-acquire and rebuild site/, or move the SLA in docs/data/ with a reason."
    )


def test_the_staleness_gate_fires_once_the_sla_is_past() -> None:
    """Run against a date every SLA is behind, the gate must name every source."""
    long_after = date(2099, 1, 1)
    flagged = {key for key, _, _ in stale_sources(SOURCES, long_after)}
    assert flagged == {source.key for source in SOURCES}


@pytest.mark.parametrize("source", SOURCES, ids=lambda s: s.key)
def test_the_staleness_gate_fires_the_day_after_the_sla_and_not_the_day_of(
    source: Source,
) -> None:
    """The boundary, both sides. An off-by-one here is a gate that fires early or late."""
    retrieved = date.fromisoformat(source.retrieved)
    on_the_day = retrieved.toordinal() + source.staleness_sla_days
    assert stale_sources((source,), date.fromordinal(on_the_day)) == []
    assert stale_sources((source,), date.fromordinal(on_the_day + 1)) == [
        (source.key, source.staleness_sla_days + 1, source.staleness_sla_days)
    ]
