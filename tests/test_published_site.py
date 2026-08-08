"""The committed ``site/`` is the thing that gets published, so check that, not a rebuild.

Every other page check in this repository runs over pages built from the committed
fixtures into a temporary directory. That is the right place to check the renderer, and
it says nothing at all about ``site/``, which is the directory the Pages workflow
uploads. ``site/`` is built from CAL FIRE's acquired files, and those are not in git and
never in CI, so a full rebuild cannot be repeated here to prove the committed bytes are
current. What can be checked without them is checked here:

* The five files the workflow publishes are present and not empty.
* They are a measurement of the real files, not fixture output wearing its clothes.
* The provenance they publish is still the reviewed provenance in
  :mod:`perimeter.sources`. A retrieval that bumps a version, a byte count or a hash
  without rebuilding ``site/`` fails here instead of being published.
* Every link is relative. The site is served from a subpath,
  ``chelseakr.github.io/perimeter/``, where an href rooted at ``/`` lands outside the
  site and 404s. Nothing about that failure is visible locally, where the pages are
  opened from a directory.
* The unofficial framing is on every page that gets served.

What this cannot claim: it does not prove ``site/`` is what the current pipeline would
produce from CAL FIRE's files. Only a machine holding those files can settle that, by
running ``make site`` and finding no diff.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from perimeter.artifacts import _source_json
from perimeter.sources import DINS, FRAP, Source

SITE = Path(__file__).resolve().parents[1] / "site"
PAGES = ("index.html", "perimeters.html", "dins.html")
ARTIFACTS = (("perimeters-coverage.json", FRAP), ("dins-coverage.json", DINS))
MEASUREMENTS = (("perimeters.html", FRAP), ("dins.html", DINS))

ROOTED = re.compile(r"""(?:href|src)\s*=\s*["']/[^"']*["']""")
"""A link rooted at the server, which is the one shape a subpath deploy breaks."""


def artifact(name: str) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(
        (SITE / "data" / name).read_text(encoding="utf-8")
    )
    return payload


@pytest.mark.parametrize(
    "name", [*PAGES, "data/perimeters-coverage.json", "data/dins-coverage.json"]
)
def test_the_published_site_holds_every_file_the_workflow_uploads(name: str) -> None:
    path = SITE / name
    assert path.is_file(), f"{name} is missing from site/"
    assert path.stat().st_size > 0, f"{name} is empty"


@pytest.mark.parametrize("name", [name for name, _ in ARTIFACTS])
def test_the_published_artifacts_are_not_fixture_output(name: str) -> None:
    """Fixture output must never be able to pass itself off as a measurement."""
    assert artifact(name)["is_fixture"] is False


@pytest.mark.parametrize(("name", "source"), ARTIFACTS)
def test_the_published_artifacts_carry_the_reviewed_provenance(
    name: str, source: Source
) -> None:
    """The published provenance must still be the reviewed provenance.

    This is the staleness check the acquired files are not needed for. If a new
    acquisition changes a version, a record count, a byte count, a hash or a quoted
    caveat in :mod:`perimeter.sources`, and ``site/`` is not rebuilt from the new files,
    the published block stops matching and this fails.
    """
    assert artifact(name)["source"] == _source_json(source, is_fixture=False)


@pytest.mark.parametrize(("name", "source"), MEASUREMENTS)
def test_a_published_measurement_page_names_its_source_and_when_it_was_read(
    name: str, source: Source
) -> None:
    text = (SITE / name).read_text(encoding="utf-8")
    assert source.retrieved in text, (
        f"{name} does not state the reviewed retrieval date"
    )
    assert source.version in text, f"{name} does not state the reviewed source version"
    assert "not applicable to a fixture build" not in text, f"{name} is fixture output"


@pytest.mark.parametrize("name", PAGES)
def test_no_published_link_is_rooted_at_the_server(name: str) -> None:
    """Served from /perimeter/, an href rooted at / leaves the site. None may be."""
    found = ROOTED.findall((SITE / name).read_text(encoding="utf-8"))
    assert not found, (
        f"{name} links to an absolute path, which breaks under a subpath: {found}"
    )


@pytest.mark.parametrize("name", PAGES)
def test_every_published_page_says_it_is_not_affiliated_with_cal_fire(
    name: str,
) -> None:
    text = (SITE / name).read_text(encoding="utf-8")
    assert "Not affiliated with or endorsed by CAL FIRE" in text
