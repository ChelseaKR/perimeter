"""Build the JSON artifacts and the two pages from files already on disk.

The build never touches the network. It reads the files acquisition put in place, or the
committed fixtures, and writes byte-identical output for byte-identical input.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from perimeter.artifacts import build
from perimeter.render import SOCIAL_CARD, dins_page, index_page, perimeters_page
from perimeter.sources import DINS, FRAP

ASSETS = Path(__file__).resolve().parents[2] / "assets"
"""Committed source assets copied verbatim into the built site.

Only the social card so far. It is copied rather than left sitting in ``site/`` because
``make site-check`` diffs ``site/`` against a fresh build: a file served from ``site/``
that no build writes would report as drift every time the check ran, and a check that
always reports the same thing stops being read. Copying is also what keeps the card in
``build/site-offline`` and ``build/run-one``, where the page checks and the determinism
gate actually look at the pages that reference it.
"""


def build_site(
    *,
    perimeters_source: Path,
    dins_source: Path,
    out_dir: Path,
    is_fixture: bool,
) -> list[Path]:
    """Write both JSON artifacts and all three pages, and return what was written."""
    perimeters, inspections = build(
        perimeters_source=perimeters_source,
        dins_source=dins_source,
        out_dir=out_dir / "data",
        is_fixture=is_fixture,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    pages = {
        "index.html": index_page(perimeters, inspections, is_fixture=is_fixture),
        "perimeters.html": perimeters_page(perimeters, is_fixture=is_fixture),
        "dins.html": dins_page(inspections, is_fixture=is_fixture),
    }
    written = [
        out_dir / "data" / "perimeters-coverage.json",
        out_dir / "data" / "dins-coverage.json",
    ]
    for name, markup in pages.items():
        path = out_dir / name
        path.write_text(markup, encoding="utf-8")
        written.append(path)
    card = out_dir / SOCIAL_CARD
    shutil.copyfile(ASSETS / SOCIAL_CARD, card)
    written.append(card)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="perimeter",
        description="Build the coverage artifacts and pages from local source files.",
    )
    parser.add_argument(
        "--perimeters",
        type=Path,
        required=True,
        help=f"attribute rows for the FRAP layer (see PROVENANCE.md {FRAP.key})",
    )
    parser.add_argument(
        "--dins",
        type=Path,
        required=True,
        help=f"attribute rows for the DINS layer (see PROVENANCE.md {DINS.key})",
    )
    parser.add_argument("--out", type=Path, required=True, help="output site directory")
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="mark the output as built from committed fixtures, not acquired files",
    )
    args = parser.parse_args(argv)
    written = build_site(
        perimeters_source=args.perimeters,
        dins_source=args.dins,
        out_dir=args.out,
        is_fixture=args.fixture,
    )
    for path in written:
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
