"""The committed ``site/`` must be what the current renderer produces, wherever that is decidable.

``tests/test_published_site.py`` says what it cannot claim, in as many words: "it does not
prove ``site/`` is what the current pipeline would produce from CAL FIRE's files. Only a
machine holding those files can settle that." That is true of the numbers. It is not true of
the rest of the page, and the rest of the page is most of it.

``site/`` is a committed artifact standing in for a computation. It is built from acquired
files that are not in git and never in CI, so no gate regenerated it and compared, and until
this file every byte of it that the renderer decides was unchecked. Change the palette, the
skip link, the nav, the canonical, the footer prose, the three-state key, a quoted CAL FIRE
caveat or a line of the provenance table, and the pages the workflow uploads keep saying the
old thing while every check stays green. The measurement pages would be the last place
anyone looked, because they look right.

What is decidable without CAL FIRE's files
------------------------------------------

Every part of a page that does not depend on how many records were counted. Two kinds:

* **Chrome.** Everything before ``<main id="content">`` and everything from ``</main>``: the
  doctype, the head, the title, the description, the canonical and Open Graph block, the
  whole stylesheet with both palettes inline, the skip link, the nav, and the footer with the
  disclaimer and the licence note. This is compared against a build from the committed
  fixtures, into a temporary directory, byte for byte. A fixture build and a real build
  differ inside ``<main>`` and nowhere else, which is why the split is where it is.
* **Blocks the renderer writes from committed constants.** ``render.legend()``,
  ``render.caveat_block(source)`` and ``render.provenance_block(source, is_fixture=False)``
  are pure functions of :mod:`perimeter.render` and :mod:`perimeter.sources`. Each must
  appear in the committed page verbatim. The provenance block is the one that cannot come
  from a fixture build, because a fixture publishes nulls where the acquisition facts go, so
  it is called directly rather than compared against a rebuild.

The rebuild is written into ``tmp_path`` and never into the working tree. A gate that
regenerates an artifact where the committed copy lives repairs the drift it exists to report
and then has nothing to report, which is how a stale file survives a green build.

What is still not decidable here: every count. Those measure CAL FIRE's files, the fixtures
hold ten records each, and no offline check can settle them. ``make site`` on a machine
holding ``data/raw/`` and no diff is still the only thing that can, and
``tests/test_published_site.py`` still holds the properties that do not need a rebuild.

Measured 2026-08-29, before this file existed: ``make site`` against the acquired FRAP and
DINS files reproduced the committed ``site/`` byte for byte, so nothing had drifted. Nothing
was keeping it that way.

Per ADR 0004 a check is not adopted until it has been seen to fail on the input it exists to
catch, in the preferred form: the comparison lives in :func:`chrome_problems`,
:func:`block_problems` and :func:`spine_problems`, and ``TestTheGateCanFail`` runs all three
against pages and payloads that must not pass.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from perimeter import render
from perimeter.cli import build_site
from perimeter.sources import DINS, FRAP, Source

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE = REPO_ROOT / "site"
FIXTURES = REPO_ROOT / "fixtures"

CONTENT_OPEN = '<main id="content">'
"""Where a page stops being chrome and starts being the measurement."""

CONTENT_CLOSE = "</main>"

PAGES = ("index.html", "perimeters.html", "dins.html")

PAGE_SOURCES: Mapping[str, tuple[Source, ...]] = {
    "index.html": (FRAP, DINS),
    "perimeters.html": (FRAP,),
    "dins.html": (DINS,),
}
"""Which sources each published page carries a provenance table for."""

PAGES_WITH_A_KEY = ("perimeters.html", "dins.html")
"""The two measurement pages. The overview carries no three-state table, so no key."""

ARTIFACTS = ("perimeters-coverage.json", "dins-coverage.json")
"""The two published JSON artifacts, named as the workflow uploads them."""


def chrome(markup: str) -> tuple[str, str]:
    """The head and the foot of one page: everything outside ``<main id="content">``.

    Raises rather than returning something empty if either marker is missing. A gate that
    can find nothing to examine fails; it does not report a clean run over nothing.
    """
    if markup.count(CONTENT_OPEN) != 1:
        raise ValueError(
            f"expected exactly one {CONTENT_OPEN!r}, found {markup.count(CONTENT_OPEN)}"
        )
    if markup.count(CONTENT_CLOSE) != 1:
        raise ValueError(
            f"expected exactly one {CONTENT_CLOSE!r}, found {markup.count(CONTENT_CLOSE)}"
        )
    head, rest = markup.split(CONTENT_OPEN)
    _, foot = rest.split(CONTENT_CLOSE)
    return head + CONTENT_OPEN, CONTENT_CLOSE + foot


def chrome_problems(name: str, committed: str, rebuilt: str) -> list[str]:
    """Every way the committed page's chrome differs from a fresh build's."""
    found: list[str] = []
    committed_head, committed_foot = chrome(committed)
    rebuilt_head, rebuilt_foot = chrome(rebuilt)
    for part, was, now in (
        ("head", committed_head, rebuilt_head),
        ("foot", committed_foot, rebuilt_foot),
    ):
        if was != now:
            found.append(
                f"site/{name}: the published {part} is not what the renderer now writes. "
                f"{len(was)} bytes committed, {len(now)} bytes rebuilt. "
                "Rebuild the site with `make site` on a machine holding data/raw/."
            )
    return found


def block_problems(name: str, committed: str, blocks: Mapping[str, str]) -> list[str]:
    """Every named block the current code writes that the committed page does not carry."""
    return [
        f"site/{name}: does not carry the {label} the current code writes "
        f"({len(block)} bytes). Rebuild the site with `make site`."
        for label, block in blocks.items()
        if block not in committed
    ]


def spine(payload: Mapping[str, Any]) -> dict[str, Any]:
    """The parts of a coverage payload that :mod:`perimeter.artifacts` decides, not the data.

    Deliberately not a whole-document comparison. Several of these payloads' dictionary
    *keys* are measurements too, because a marker table is keyed by the marker strings the
    file actually holds, so a fixture and a real build cannot agree on them and must not be
    made to. What both builds must agree on is the shape the writer imposes: which top-level
    keys exist, which fields are reported and in what order, what each field record carries,
    and the fixed prose and thresholds the writer supplies.
    """
    found: dict[str, Any] = {
        "top_level_keys": sorted(payload),
        "measurement": payload["measurement"],
        "source_keys": sorted(payload["source"]),
        "fields": [
            [field["name"], field["label"], field["marker_basis"], sorted(field)]
            for field in payload["fields"]
        ],
    }
    if "field_state_order" in payload:
        found["field_state_order"] = payload["field_state_order"]
    if "access" in payload:
        found["access_keys"] = sorted(payload["access"])
    if "completeness_by_access" in payload:
        found["by_access"] = [
            [row["name"], row["label"], sorted(row)]
            for row in payload["completeness_by_access"]
        ]
    if "acre_thresholds" in payload:
        thresholds = payload["acre_thresholds"]
        found["acre_thresholds"] = {
            "keys": sorted(thresholds),
            "thresholds": thresholds["thresholds"],
            "note": thresholds["note"],
        }
    for key in ("duplicate_signals", "marker_counterfactuals"):
        if key in payload:
            found[key] = [
                [signal["key"], signal["description"], sorted(signal)]
                for signal in payload[key]
            ]
    return found


def spine_problems(
    name: str, committed: Mapping[str, Any], rebuilt: Mapping[str, Any]
) -> list[str]:
    """Every way the committed artifact's shape differs from a fresh build's."""
    was, now = spine(committed), spine(rebuilt)
    return [
        f"site/data/{name}: {key} is {was.get(key)!r} in the published artifact and "
        f"{now.get(key)!r} in a fresh build. Rebuild the site with `make site`."
        for key in sorted(set(was) | set(now))
        if was.get(key) != now.get(key)
    ]


@pytest.fixture(scope="module")
def rebuilt(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    """The same pipeline over the committed fixtures, into a temporary directory.

    Never into ``site/``. See the module docstring.
    """
    out = tmp_path_factory.mktemp("site-rebuild")
    build_site(
        perimeters_source=FIXTURES / "frap_perimeters.sample.json",
        dins_source=FIXTURES / "dins_postfire.sample.json",
        out_dir=out,
        is_fixture=True,
    )
    built = {name: (out / name).read_text(encoding="utf-8") for name in PAGES}
    built.update(
        {name: (out / "data" / name).read_text(encoding="utf-8") for name in ARTIFACTS}
    )
    return built


def published(name: str) -> str:
    return (SITE / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", PAGES)
def test_the_published_chrome_is_what_the_renderer_now_writes(
    name: str, rebuilt: dict[str, str]
) -> None:
    assert not chrome_problems(name, published(name), rebuilt[name])


@pytest.mark.parametrize("name", PAGES)
def test_the_published_page_carries_the_current_provenance_table(name: str) -> None:
    """The provenance table is a pure function of :mod:`perimeter.sources`.

    ``tests/test_published_site.py`` already holds this for the JSON artifacts. The pages
    are what a reader actually sees, and until now a version, a byte count or a hash could
    move in ``sources.py`` and leave the published tables saying the old thing.
    """
    blocks = {
        f"provenance table for {source.key}": render.provenance_block(
            source, is_fixture=False
        )
        for source in PAGE_SOURCES[name]
    }
    assert not block_problems(name, published(name), blocks)


@pytest.mark.parametrize("name", PAGES_WITH_A_KEY)
def test_the_published_measurement_page_carries_the_current_caveats_and_key(
    name: str,
) -> None:
    """CAL FIRE's quoted caveats, and the three-state key the tables are read with."""
    (source,) = PAGE_SOURCES[name]
    blocks = {
        f"quoted caveats for {source.key}": render.caveat_block(source),
        "three-state key": render.legend(),
    }
    assert not block_problems(name, published(name), blocks)


@pytest.mark.parametrize("name", ARTIFACTS)
def test_the_published_artifact_has_the_shape_the_writer_now_produces(
    name: str, rebuilt: dict[str, str]
) -> None:
    committed = json.loads((SITE / "data" / name).read_text(encoding="utf-8"))
    assert not spine_problems(name, committed, json.loads(rebuilt[name]))


class TestTheGateCanFail:
    """ADR 0004, form 1: the comparisons above, run against input that must not pass."""

    def test_a_changed_stylesheet_is_caught(self, rebuilt: dict[str, str]) -> None:
        damaged = published("index.html").replace("--accent:", "--accent-was:", 1)
        assert damaged != published("index.html")
        assert chrome_problems("index.html", damaged, rebuilt["index.html"])

    def test_a_changed_canonical_is_caught(self, rebuilt: dict[str, str]) -> None:
        damaged = published("dins.html").replace("<link rel=", "<link data-rel=", 1)
        assert damaged != published("dins.html")
        assert chrome_problems("dins.html", damaged, rebuilt["dins.html"])

    def test_a_changed_footer_is_caught(self, rebuilt: dict[str, str]) -> None:
        damaged = published("perimeters.html").replace(
            "</footer>", "<p>added</p></footer>", 1
        )
        assert damaged != published("perimeters.html")
        assert chrome_problems("perimeters.html", damaged, rebuilt["perimeters.html"])

    @pytest.mark.parametrize("marker", [CONTENT_OPEN, CONTENT_CLOSE])
    def test_a_page_with_no_content_marker_fails_rather_than_passing_over_nothing(
        self, marker: str
    ) -> None:
        with pytest.raises(ValueError):
            chrome(published("index.html").replace(marker, ""))

    def test_a_page_with_a_second_content_marker_fails(self) -> None:
        with pytest.raises(ValueError):
            chrome(published("index.html") + CONTENT_CLOSE)

    def test_a_missing_block_is_caught(self) -> None:
        block = render.provenance_block(FRAP, is_fixture=False)
        damaged = published("perimeters.html").replace(block, "", 1)
        assert block not in damaged
        assert block_problems("perimeters.html", damaged, {"provenance table": block})

    def test_a_block_altered_by_one_character_is_caught(self) -> None:
        block = render.provenance_block(DINS, is_fixture=False)
        damaged = published("dins.html").replace(
            block, block.replace("<dt>", "<dt >", 1), 1
        )
        assert damaged != published("dins.html")
        assert block_problems("dins.html", damaged, {"provenance table": block})

    def test_a_present_block_is_not_reported(self) -> None:
        """The other direction, so the check is not passing by always finding a problem."""
        assert not block_problems(
            "dins.html", published("dins.html"), {"three-state key": render.legend()}
        )

    def test_a_dropped_payload_key_is_caught(self, rebuilt: dict[str, str]) -> None:
        fresh: dict[str, Any] = json.loads(rebuilt["dins-coverage.json"])
        damaged = {
            key: value for key, value in fresh.items() if key != "field_state_order"
        }
        assert spine_problems("dins-coverage.json", damaged, fresh)

    def test_a_renamed_field_is_caught(self, rebuilt: dict[str, str]) -> None:
        fresh: dict[str, Any] = json.loads(rebuilt["perimeters-coverage.json"])
        damaged = json.loads(rebuilt["perimeters-coverage.json"])
        fields: Sequence[dict[str, Any]] = damaged["fields"]
        fields[0]["label"] = fields[0]["label"] + " (renamed)"
        assert spine_problems("perimeters-coverage.json", damaged, fresh)

    def test_an_unchanged_payload_is_not_reported(
        self, rebuilt: dict[str, str]
    ) -> None:
        fresh = json.loads(rebuilt["perimeters-coverage.json"])
        assert not spine_problems("perimeters-coverage.json", fresh, fresh)
