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
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from perimeter.schema import DINS_REQUIRED_COLUMNS, FRAP_REQUIRED_COLUMNS
from perimeter.sources import DINS, FRAP, Source

USER_AGENT = "perimeter-coverage/0.1 (+https://github.com/ChelseaKR/perimeter)"
"""Names the project and where to look it up, so an operator can see who is calling."""

WHERE = "1=1"
"""The predicate every request uses. The count check and the walk must agree on it."""

IDENTIFIER_FIELD = "OBJECTID"
"""The field the walk orders on, and the one the post-walk check reads.

Both layers publish it and both required-column lists in ``schema.py`` name it, so it is
always present in what the walk collects. Ordering on a field and then not checking the
order is a check that cannot fail.
"""

PAGE_SIZE = 2000
"""Records asked for per page. Both layers publish ``maxRecordCount`` 2000, read from the
layer metadata on 2026-08-16.

That number is the layer's to change and is not a promise about what any page will hold.
Asked for 3,000 on 2026-08-16 the POSTFIRE layer answered with 2,000 rows and
``exceededTransferLimit`` true, which is the standard behaviour whenever
``resultRecordCount`` exceeds ``maxRecordCount``. So the walk below steps its offset by the
length of the page it was handed, never by the length it asked for.
"""

PAUSE_SECONDS = 0.2
TIMEOUT_SECONDS = 180

DEFAULT_OUT_FORMAT = "json"
"""The output format every request this project makes asks for.

``sources.py`` pins the sha256 of files fetched with it, so this is not a default that may
drift: changing it changes every acquired byte.
"""

PAGEABLE_OUT_FORMATS: tuple[str, ...] = ("json", "geojson", "pjson")
"""Output formats the walk in :func:`iter_features` is known to be able to page.

The walk is not format-agnostic even though it hands the payload straight back. It reads
two things out of the top level of every answer -- ``features``, to know what to yield and
how far to step, and ``exceededTransferLimit``, to know whether to ask again -- and only a
format that carries both can be walked at all.

The refusal matters more than the list. A format the service accepts but that carries no
top-level ``features`` (``f=html`` is refused earlier by the content-type check, but a
service is free to add JSON-shaped formats that are not GeoServices) would leave the walk
with nothing to yield on its first page, and a walk that ends on its first page is
indistinguishable from a layer with no records in it. That is a wrong answer with no error
attached, which is the one outcome this module is written to make impossible.
"""


class UnpageableFormatError(ValueError):
    """The requested output format is not one this walk can page."""


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


def fetch_document(url: str, *, user_agent: str = USER_AGENT) -> dict[str, Any]:
    """One request, with every refusal this module makes about somebody else's server.

    Public, and named rather than underscored, because the refusals below are the whole
    of what this module promises: HTTPS only, an honest User-Agent, a hard stop on 401,
    403 and 429, a non-JSON answer read as a challenge page rather than parsed, and an
    error payload refused rather than treated as data. A consumer that needs to read one
    JSON document from a publisher this project already talks to should get all five,
    and while this was private the only way to have them was to write them again.

    That is not hypothetical. ``wildfire-service-territory-overlap`` carried a second
    copy of exactly these five for months, and its ``docs/UPSTREAM.md`` named the reason:
    "because ``fetch_feature_pages`` needs a fetch and ``_get`` is private". The walk it
    needed is now shared; this is the other half.

    It is a single request and nothing more. It does no paging, so a caller reading a
    layer wants :func:`iter_features`, whose offset rule is the thing that must not be
    copied.

    ``user_agent`` is what CAL FIRE's logs will see.

    A consuming project that vendored this walk sent *this* project's name, so an
    operator reading their own logs could not tell who was calling. The parameter exists
    so a caller can say who it is; the default still names this project, because a
    library that quietly sends nothing identifiable is worse than one that names the
    wrong caller.

    An empty or blank User-Agent is refused rather than passed through. urllib would
    substitute its own ``Python-urllib/3.x``, which identifies nobody -- an absent
    identity sent as though it were one.
    """
    if not user_agent.strip():
        raise AcquisitionFailed(
            "refusing to fetch with a blank User-Agent: urllib would substitute its own "
            "default, which names no caller at all. Pass a User-Agent that identifies "
            "the calling project, or leave the default, which names this one."
        )
    if not url.startswith("https://"):
        raise AcquisitionFailed(f"refusing to fetch a non-HTTPS endpoint: {url!r}")
    # Audited: both linters flag urllib for accepting schemes such as file://. The
    # scheme is pinned to https immediately above, and the host comes from the reviewed
    # endpoints in sources.py rather than from user input or from any fetched content.
    # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})  # noqa: S310
    try:
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
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


def layer_record_count(endpoint: str, *, user_agent: str = USER_AGENT) -> int:
    """How many records the layer says it holds, under the predicate the walk uses.

    The walk below can only be as honest as the pages it is handed. A layer that stops
    early, a page the walk steps over, a query the service quietly truncates: each of them
    ends in a file that looks finished, hashes cleanly, and describes a fraction of the
    layer. None of that is visible from inside the walk, so this asks the layer for its
    own total and :func:`acquire` refuses to write anything that does not match it.
    """
    query = urllib.parse.urlencode(
        {"where": WHERE, "returnCountOnly": "true", "f": "json"}
    )
    payload = fetch_document(f"{endpoint}?{query}", user_agent=user_agent)
    count = payload.get("count")
    if not isinstance(count, int) or isinstance(count, bool):
        raise AcquisitionFailed(
            f"{endpoint} answered returnCountOnly with no count: {payload!r}. There is "
            "nothing to check a download against without it, and a download nothing "
            "checked is not an acquisition."
        )
    return count


def iter_features(
    endpoint: str,
    fields: tuple[str, ...],
    *,
    user_agent: str = USER_AGENT,
    return_geometry: bool = False,
    out_sr: int | None = None,
    out_format: str = DEFAULT_OUT_FORMAT,
) -> Iterator[dict[str, Any]]:
    """Page through a layer, yielding each feature as the service sent it.

    This is the paged walk itself, exposed. A consuming project needed geometry, could
    not get it from :func:`fetch_layer` -- which discards everything but ``attributes``
    -- and so copied the offset loop, including the part of it that is subtle. The whole
    value of that loop is the offset rule below, and a copy of it drifts.

    A feature is yielded whole: under ``f=json`` that is ``{"attributes": {...}}``, plus
    ``"geometry"`` when ``return_geometry`` is set; under ``f=geojson`` it is the GeoJSON
    ``Feature`` the service built, ``{"type", "geometry", "properties"}``. Nothing is
    merged, converted or renamed on the way through, because a layer is free to publish a
    field called ``geometry`` and a merge would silently overwrite it -- and because a
    conversion here would be this project reprojecting somebody else's data on their
    behalf, which is the one thing it does not do.

    ``out_sr`` is the spatial reference to project coordinates into (a WKID). It is sent
    only when given, and ``out_format`` defaults to the format this project has always
    asked for, so the default request is byte-for-byte the request behind the hashes
    pinned in ``sources.py``.

    ``out_format`` must be one of :data:`PAGEABLE_OUT_FORMATS`; anything else raises
    :class:`UnpageableFormatError` before a single request is made. The walk reads
    ``features`` and ``exceededTransferLimit`` out of every answer, and a format that
    carries neither would walk zero records and stop, which reads exactly like an empty
    layer.
    """
    if out_format not in PAGEABLE_OUT_FORMATS:
        supported = ", ".join(repr(name) for name in PAGEABLE_OUT_FORMATS)
        raise UnpageableFormatError(
            f"out_format={out_format!r} is not a format this walk can page. It reads "
            "'features' and 'exceededTransferLimit' out of the top level of every "
            f"answer, and only {supported} carry both. A format that carries neither "
            "would yield nothing on the first page and stop, which is indistinguishable "
            "from a layer holding no records."
        )
    offset = 0
    while True:
        query: dict[str, Any] = {
            "where": WHERE,
            "outFields": ",".join(fields),
            "returnGeometry": "true" if return_geometry else "false",
            "orderByFields": f"{IDENTIFIER_FIELD} ASC",
            "resultOffset": offset,
            "resultRecordCount": PAGE_SIZE,
            "f": out_format,
        }
        if out_sr is not None:
            query["outSR"] = out_sr
        payload = fetch_document(
            f"{endpoint}?{urllib.parse.urlencode(query)}", user_agent=user_agent
        )
        if "features" not in payload:
            raise AcquisitionFailed(
                f"{endpoint} answered a page with no 'features' key at offset {offset}: "
                f"{sorted(payload)!r}. An answer the walk cannot read is not an answer "
                "that the layer is exhausted, and treating it as one would end the walk "
                "early and write a short file with a clean hash."
            )
        features = payload["features"]
        if not isinstance(features, list):
            raise AcquisitionFailed(
                f"{endpoint} answered a page whose 'features' is a "
                f"{type(features).__name__} rather than a list, at offset {offset}. "
                "The walk yields from it and steps its offset by its length, and both "
                "of those do something plausible to a mapping: it would yield the "
                "field names and step by the number of them. A page shaped like that "
                "is not a page of features."
            )
        if not features:
            break
        yield from features
        if not payload.get("exceededTransferLimit") and len(features) < PAGE_SIZE:
            break
        # Step by the page that arrived, not by the page that was asked for. `resultOffset`
        # means "skip this many records", so a layer capping the page below PAGE_SIZE and
        # setting exceededTransferLimit leaves a block of records between the end of this
        # page and the next offset. Stepping by PAGE_SIZE walks over that block, and the
        # walk still ends normally: the missing records look exactly like records that were
        # never there.
        offset += len(features)
        time.sleep(PAUSE_SECONDS)


def fetch_layer(
    endpoint: str,
    fields: tuple[str, ...],
    *,
    user_agent: str = USER_AGENT,
) -> list[dict[str, Any]]:
    """Page through a layer's attributes, geometry excluded.

    This takes no ``out_format``, deliberately. It reads ``feature["attributes"]``, which
    only the GeoServices formats carry: a GeoJSON ``Feature`` puts the same values under
    ``properties``, so a format argument here would either raise ``KeyError`` on every
    row or need a rename that made this function a converter. Callers who want another
    format want the features themselves, which is :func:`iter_features`.
    """
    return [
        feature["attributes"]
        for feature in iter_features(endpoint, fields, user_agent=user_agent)
    ]


def identifier_failure(identifiers: list[Any]) -> str | None:
    """Why this walk's identifiers do not describe one ordered pass over the layer.

    The walk asks the service to order by ``OBJECTID`` and steps an offset through the
    result. Two things can go wrong that a record count cannot see, because both leave
    the count intact: the service can hand back a page it has already handed back (a
    repeated identifier), and it can reorder under a concurrent edit (an identifier that
    goes backwards). Either one means some records were collected twice and others not at
    all, and the file that lands on disk is the wrong size in two directions at once.

    Split out from the walk so every refusing branch is reachable from a test rather than
    only from a misbehaving service.
    """
    if not identifiers:
        return None
    previous: Any = None
    seen: set[Any] = set()
    for position, value in enumerate(identifiers):
        if not isinstance(value, int) or isinstance(value, bool):
            return (
                f"row {position} carries {IDENTIFIER_FIELD}={value!r}, which is not an "
                "integer. The walk orders on this field, so a non-integer means the "
                "ordering the offset relies on is not the ordering that happened"
            )
        if value in seen:
            return (
                f"{IDENTIFIER_FIELD} {value} appears more than once. A repeated "
                "identifier means a page was handed back twice, so the walk collected "
                "some records twice and missed others"
            )
        if previous is not None and value <= previous:
            return (
                f"{IDENTIFIER_FIELD} {value} at row {position} does not follow "
                f"{previous}. The walk asks for {IDENTIFIER_FIELD} ASC and steps an "
                "offset through the answer; an identifier that goes backwards means the "
                "result was reordered mid-walk"
            )
        seen.add(value)
        previous = value
    return None


def acquire(
    source: Source,
    fields: tuple[str, ...],
    out_dir: Path,
    *,
    user_agent: str = USER_AGENT,
) -> Acquired:
    """Read the layer whole, or write nothing at all.

    The record count this returns is copied into ``sources.py`` by hand, printed on both
    pages under Provenance, and published in the JSON artifacts. A short download that
    reaches the build is not published as a failed download; it is published as a smaller
    dataset, with a hash and a date beside it. So the layer's own total is read first and
    the walk is checked against it before any file is written.

    **The count is read twice, before the walk and after it**, and both are compared to
    what the walk collected. One count read before a walk cannot see a layer that was
    republished while the walk was in progress: the walk ends at a total that matches the
    number the layer held an hour ago, and the file that lands is a mixture of two
    versions with a clean hash on it. Two counts that disagree mean exactly that, and the
    only honest thing to do with them is refuse and say both numbers.

    The identifiers are checked too, for the reason :func:`identifier_failure` gives: a
    repeated or reordered page leaves the count intact and the contents wrong.
    """
    before = layer_record_count(source.endpoint, user_agent=user_agent)
    rows = fetch_layer(source.endpoint, fields, user_agent=user_agent)
    after = layer_record_count(source.endpoint, user_agent=user_agent)
    if before != after:
        raise AcquisitionFailed(
            f"{source.key}: the layer reported {before} records before the walk and "
            f"{after} after it, so it was republished while this was reading it. Nothing "
            f"was written. The walk collected {len(rows)} records, and a file assembled "
            "across two versions of a layer is not either of them. Re-run the "
            "acquisition."
        )
    if len(rows) != after:
        raise AcquisitionFailed(
            f"{source.key}: the layer reports {after} records and the walk collected "
            f"{len(rows)}. Nothing was written. If the layer was republished mid-walk, "
            "re-run the acquisition; if it was not, the walk is dropping records and "
            "must be fixed before any count from this file is published."
        )
    failure = identifier_failure([row.get(IDENTIFIER_FIELD) for row in rows])
    if failure is not None:
        raise AcquisitionFailed(
            f"{source.key}: the walk collected {len(rows)} records, which is what the "
            f"layer reports, but {failure}. Nothing was written. A count that matches is "
            "not evidence that the right records were collected."
        )
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
                # Which guards this acquisition actually passed, rather than which ones
                # the code contains. A manifest from before the post-walk recount existed
                # and one from after it are otherwise indistinguishable, and the whole
                # point of the recount is that a file which passed it is a different
                # claim from a file which did not.
                "checks": {
                    "counted_before_walk": True,
                    "counted_after_walk": True,
                    "identifier_field": IDENTIFIER_FIELD,
                    "identifiers_unique_and_ascending": True,
                },
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
