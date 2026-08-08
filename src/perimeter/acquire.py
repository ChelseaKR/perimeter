"""Download the two sources from their published endpoints, once, by hand.

Both datasets list a GeoServices REST endpoint among their own resources on
data.cnra.ca.gov and data.ca.gov, and both are published under Creative Commons
Attribution. This module reads those endpoints the way they are documented to be read:
an honest User-Agent naming the project, one page at a time, geometry left behind because
no measurement here needs it, and a short pause between pages.

There is no fallback path. If an endpoint declines automated access, this raises
:class:`AcquisitionBlocked` and stops, with the landing page to download from by hand.
Nothing in this module retries with a different identity, and nothing in it attempts to
look like a browser. A source that does not want to be fetched this way is acquired
manually and recorded in PROVENANCE.md as a manual acquisition.

This module is the only part of the project that touches the network. It never runs in
CI, and the coverage build never calls it: artifacts are built from files already on
disk, so a build is reproducible without asking CAL FIRE's servers for anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from perimeter.schema import DINS_REQUIRED_COLUMNS, FRAP_REQUIRED_COLUMNS
from perimeter.sources import DINS, FRAP, Source

USER_AGENT = "perimeter-coverage/0.1 (+https://github.com/ChelseaKR/perimeter)"
"""Names the project and where to look it up, so an operator can see who is calling."""

PAGE_SIZE = 2000
"""The layers publish maxRecordCount 2000. Asking for more would just be ignored."""

PAUSE_SECONDS = 0.2
TIMEOUT_SECONDS = 180

FRAP_FETCH_FIELDS: tuple[str, ...] = FRAP_REQUIRED_COLUMNS
DINS_FETCH_FIELDS: tuple[str, ...] = (
    *DINS_REQUIRED_COLUMNS,
    "CITY",
    "COMMUNITY",
    "STREETNAME",
    "STREETTYPE",
    "NUMBEROFUNITPERSTRUCTURE",
    "NOOUTBUILDINGSDAMAGED",
    "NOOUTBUILDINGSNOTDAMAGED",
    "NOOFCARSONPROPERTY",
)


class AcquisitionBlocked(RuntimeError):
    """The endpoint declined automated access. Acquire the file by hand instead."""


class AcquisitionFailed(RuntimeError):
    """The endpoint answered with something that is not the documented payload."""


@dataclass(frozen=True)
class Acquired:
    source_key: str
    path: Path
    record_count: int
    raw_bytes: int
    sha256: str
    retrieved: str
    endpoint: str


def write_rows(path: Path, rows: list[dict[str, Any]]) -> Acquired:
    """Write attribute rows so that the same records always produce the same bytes.

    Keys are sorted and the separators are pinned, so a re-download of an unchanged layer
    yields a byte-identical file and its hash can be compared against PROVENANCE.md.
    """
    text = json.dumps(rows, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    payload = path.read_bytes()
    return Acquired(
        source_key=path.stem,
        path=path,
        record_count=len(rows),
        raw_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        retrieved=datetime.now(tz=UTC).date().isoformat(),
        endpoint="",
    )


def _get(url: str) -> dict[str, Any]:
    if not url.startswith("https://"):
        raise AcquisitionFailed(f"refusing to fetch a non-HTTPS endpoint: {url!r}")
    # S310: the scheme is pinned to https above and the host comes from the reviewed
    # endpoints in sources.py. No URL here is built from user input.
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as error:
        if error.code in {401, 403, 429}:
            raise AcquisitionBlocked(
                f"{url} answered {error.code}. This project does not work around access "
                "controls. Download the file from the dataset's landing page by hand and "
                "record the manual acquisition in PROVENANCE.md."
            ) from error
        raise AcquisitionFailed(f"{url} answered {error.code}") from error
    if "json" not in content_type.lower():
        raise AcquisitionBlocked(
            f"{url} answered {content_type!r} rather than JSON, which is what an "
            "interstitial or a challenge page looks like. This project does not work "
            "around that. Acquire the file by hand from the dataset landing page."
        )
    parsed: dict[str, Any] = json.loads(body)
    if "error" in parsed:
        raise AcquisitionFailed(f"{url} returned an error payload: {parsed['error']}")
    return parsed


def fetch_layer(endpoint: str, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    """Page through a layer's attributes, geometry excluded."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        query = urllib.parse.urlencode(
            {
                "where": "1=1",
                "outFields": ",".join(fields),
                "returnGeometry": "false",
                "orderByFields": "OBJECTID ASC",
                "resultOffset": offset,
                "resultRecordCount": PAGE_SIZE,
                "f": "json",
            }
        )
        payload = _get(f"{endpoint}?{query}")
        features = payload.get("features", [])
        if not features:
            break
        rows.extend(feature["attributes"] for feature in features)
        if not payload.get("exceededTransferLimit") and len(features) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(PAUSE_SECONDS)
    return rows


def acquire(source: Source, fields: tuple[str, ...], out_dir: Path) -> Acquired:
    rows = fetch_layer(source.endpoint, fields)
    acquired = write_rows(out_dir / source.raw_file, rows)
    return Acquired(
        source_key=source.key,
        path=acquired.path,
        record_count=acquired.record_count,
        raw_bytes=acquired.raw_bytes,
        sha256=acquired.sha256,
        retrieved=acquired.retrieved,
        endpoint=source.endpoint,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="perimeter-acquire",
        description=(
            "Download the two public source layers into a local directory. "
            "Run by hand; never part of a build or CI."
        ),
    )
    parser.add_argument("--out", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--source",
        choices=[FRAP.key, DINS.key],
        action="append",
        help="acquire only this source; repeatable, defaults to both",
    )
    args = parser.parse_args(argv)
    wanted = set(args.source or [FRAP.key, DINS.key])
    plan = [
        (FRAP, FRAP_FETCH_FIELDS),
        (DINS, DINS_FETCH_FIELDS),
    ]
    manifest: list[dict[str, object]] = []
    for source, fields in plan:
        if source.key not in wanted:
            continue
        print(f"acquiring {source.key} from {source.endpoint}")
        result = acquire(source, fields, args.out)
        print(
            f"  {result.record_count} records, {result.raw_bytes} bytes, "
            f"sha256 {result.sha256}"
        )
        manifest.append(
            {
                "source": result.source_key,
                "endpoint": result.endpoint,
                "file": result.path.name,
                "record_count": result.record_count,
                "raw_bytes": result.raw_bytes,
                "sha256": result.sha256,
                "retrieved": result.retrieved,
            }
        )
    manifest_path = args.out / "acquisition.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {manifest_path}")
    print("Copy record_count, raw_bytes and sha256 into src/perimeter/sources.py")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
