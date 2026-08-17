"""The standards pin and the conformance table have to be read by something.

DOC-01 wants `.standards-version` to name a released tag. DOC-11 wants the README's
Standards Conformance table to carry all fifteen standards, each with a non-empty state.
Both are AUTO-GATEs, which means a file sitting in the repository is not enough: a pin
nothing parses is decoration, and decoration is the failure mode this repository spent
2026-08-15 removing. These tests are the reader. They run inside `make verify`, so they
run in CI, and they fail when the pin drifts to a branch, when a standard is dropped from
the table, or when a row is left blank.

What they cannot check is whether a state is *true*. `tests/test_provenance.py` is the
model for the parts that can be checked mechanically; the rest is a review obligation and
is named as one here rather than implied to be automatic.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PIN = ROOT / ".standards-version"
README = (ROOT / "README.md").read_text(encoding="utf-8")

RELEASED_TAG = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

STANDARDS = (
    "Code Quality",
    "Security & Supply-Chain",
    "CI/CD",
    "Observability",
    "Accessibility",
    "Internationalization",
    "AI Evaluation",
    "Quality & Metrics",
    "Documentation",
    "Release & Versioning",
    "Responsible-Tech Framework",
    "Performance",
    "Incident Response",
    "Data Governance",
    "AI Development Measurement",
)

# The verdict has to be the first thing in the cell, and it has to be one of these
# forms. The punctuation is not decoration: the portfolio's conformance reader accepts
# a verdict only when the character straight after `Applies` is whitespace, `:`, `(`,
# `-` or an em dash, so `Applies.` and `Applies, not met.` were unreadable to it and
# this table's fifteen honest rows scored as one invalid state. Keep any new form
# inside that grammar.
STATES = (
    "Applies:",
    "Applies (not met)",
    "Applies (Tier",
    "Applies (L",
    "N/A (",
)


def pin() -> str:
    return PIN.read_text(encoding="utf-8").strip()


def conformance_rows() -> dict[str, str]:
    """The table under `## Standards conformance`, as {standard: state}."""
    section = README.split("## Standards conformance", 1)
    assert len(section) == 2, (
        "README has no '## Standards conformance' section (DOC-11)"
    )
    body = section[1].split("\n## ", 1)[0]
    rows: dict[str, str] = {}
    for line in body.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if (
            len(cells) != 2
            or cells[0] in {"Standard", ""}
            or set(cells[0]) <= {"-", ":"}
        ):
            continue
        rows[cells[0]] = cells[1]
    return rows


# --- DOC-01: the pin ----------------------------------------------------------------


def test_the_standards_pin_exists() -> None:
    assert PIN.is_file(), ".standards-version is missing (DOC-01)"


def test_the_standards_pin_names_a_released_tag() -> None:
    """Never `main`, never a `heads/` ref: a moving pin is not a pin."""
    value = pin()
    assert RELEASED_TAG.match(value), (
        f".standards-version is {value!r}; DOC-01 wants a vMAJOR.MINOR.PATCH tag"
    )
    assert value != "main"
    assert not value.startswith(("heads/", "refs/"))


def test_the_readme_cites_the_pinned_version() -> None:
    """If the pin moves and the table still names the old one, one of them is lying."""
    assert f"`{pin()}`" in README, (
        f"README does not cite the pinned standards version {pin()!r}"
    )


# --- DOC-11: the conformance table --------------------------------------------------


@pytest.mark.parametrize("standard", STANDARDS)
def test_every_standard_has_a_row(standard: str) -> None:
    assert standard in conformance_rows(), (
        f"'{standard}' is missing from the Standards Conformance table (DOC-11)"
    )


@pytest.mark.parametrize("standard", STANDARDS)
def test_no_row_is_blank(standard: str) -> None:
    state = conformance_rows().get(standard, "")
    assert state.strip(), f"'{standard}' has a blank state (DOC-11)"


@pytest.mark.parametrize("standard", STANDARDS)
def test_every_state_opens_with_a_recognised_verdict(standard: str) -> None:
    """A gap has to be recorded as a gap. Prose that avoids saying which is not a state."""
    state = conformance_rows().get(standard, "")
    assert state.startswith(STATES), (
        f"'{standard}' opens with {state[:40]!r}; expected one of {STATES}"
    )


def test_the_table_carries_no_standard_this_portfolio_does_not_have() -> None:
    unknown = set(conformance_rows()) - set(STANDARDS)
    assert not unknown, f"unrecognised standards in the table: {sorted(unknown)}"


def test_the_table_says_the_applicability_manifest_has_no_entry_for_this_repo() -> None:
    """FIX-02. Remove this test on the day the manifest entry exists, not before.

    The scoping above was derived from each standard's own applicability section rather
    than read from the registry, and a reader is owed that caveat while it is true.
    """
    section = README.split("## Standards conformance", 1)[1].split("\n## ", 1)[0]
    assert "applicability manifest has no entry" in section
