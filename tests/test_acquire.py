"""The refusals in `acquire.py`, exercised offline.

`acquire.py` is the only module that touches the network, and it is the module that
carries the promises CONTRIBUTING.md makes about how this project behaves towards
somebody else's server: HTTPS only, an honest User-Agent, geometry left behind, a pause
between pages, and a hard stop rather than a workaround when an endpoint declines.

None of that needs a network to test. Every test here substitutes the one function that
opens a socket, so the refusals are checked as behaviour rather than described in a
docstring. The real endpoints are never contacted, from here or from any other test.
"""

from __future__ import annotations

import inspect
import io
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest

from perimeter import acquire as acquire_mod
from perimeter.acquire import (
    DEFAULT_OUT_FORMAT,
    IDENTIFIER_FIELD,
    PAGE_SIZE,
    PAGEABLE_OUT_FORMATS,
    USER_AGENT,
    AcquisitionBlocked,
    AcquisitionFailed,
    UnpageableFormatError,
    acquire,
    fetch_layer,
    identifier_failure,
    iter_features,
    layer_record_count,
    main,
    write_rows,
)
from perimeter.sources import DINS, FRAP


@pytest.fixture(autouse=True)
def no_socket_reaches_cal_fire(monkeypatch: pytest.MonkeyPatch) -> None:
    """The docstring above says the real endpoints are never contacted. Enforce it.

    Every test here substitutes either `fetch_document` or `urlopen`, and until this fixture
    existed that was a convention rather than a rule: a test that forgot, or a code path
    that grew a second request, would quietly fetch from CAL FIRE's servers instead of
    failing. A test that reaches this now fails with a message saying what to substitute.
    """

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            "a test tried to open a socket to a real endpoint; substitute "
            "acquire.fetch_document or urllib.request.urlopen in the test"
        )

    monkeypatch.setattr(acquire_mod.urllib.request, "urlopen", refuse)


class FakeResponse(io.BytesIO):
    """The two attributes `fetch_document` reads off a urlopen result, and nothing else."""

    def __init__(self, body: bytes, content_type: str = "application/json") -> None:
        super().__init__(body)
        self.headers = {"Content-Type": content_type}

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def json_response(
    payload: object, content_type: str = "application/json"
) -> FakeResponse:
    return FakeResponse(json.dumps(payload).encode("utf-8"), content_type)


def http_error(code: int) -> HTTPError:
    return HTTPError("https://example.invalid/query", code, "no", {}, None)  # type: ignore[arg-type]


# --- write_rows: the same records must always produce the same bytes ----------------


def test_write_rows_is_byte_identical_for_the_same_records(tmp_path: Path) -> None:
    rows = [{"b": 2, "a": 1}, {"a": 3, "b": 4}]
    first = write_rows(tmp_path / "one.json", rows)
    second = write_rows(tmp_path / "two.json", list(reversed([*reversed(rows)])))
    assert first.sha256 == second.sha256
    assert first.raw_bytes == second.raw_bytes


def test_write_rows_sorts_keys_so_field_order_cannot_change_the_hash(
    tmp_path: Path,
) -> None:
    a = write_rows(tmp_path / "a.json", [{"z": 1, "a": 2}])
    b = write_rows(tmp_path / "b.json", [{"a": 2, "z": 1}])
    assert a.sha256 == b.sha256


def test_write_rows_reports_what_it_wrote(tmp_path: Path) -> None:
    result = write_rows(tmp_path / "nested" / "rows.json", [{"a": 1}, {"a": 2}])
    assert result.path.is_file()
    assert result.record_count == 2
    assert result.raw_bytes == result.path.stat().st_size
    assert result.source_key == "rows"
    assert len(result.sha256) == 64


# --- fetch_document: the refusals -------------------------------------------------------------


def test_a_non_https_endpoint_is_refused_before_any_socket_opens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("urlopen must not be reached for a non-HTTPS URL")

    monkeypatch.setattr(acquire_mod.urllib.request, "urlopen", explode)
    with pytest.raises(AcquisitionFailed, match="non-HTTPS"):
        acquire_mod.fetch_document("http://example.invalid/query")
    with pytest.raises(AcquisitionFailed, match="non-HTTPS"):
        acquire_mod.fetch_document("file:///etc/passwd")


def test_the_request_names_the_project_rather_than_imitating_a_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    def fake_urlopen(request: Any, timeout: int | None = None) -> FakeResponse:
        seen.update(request.headers)
        return json_response({"features": []})

    monkeypatch.setattr(acquire_mod.urllib.request, "urlopen", fake_urlopen)
    acquire_mod.fetch_document("https://example.invalid/query")
    assert seen["User-agent"] == USER_AGENT
    assert "perimeter" in USER_AGENT
    assert "github.com/ChelseaKR/perimeter" in USER_AGENT


@pytest.mark.parametrize("code", [401, 403, 429])
def test_a_declined_request_stops_instead_of_working_around_it(
    monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    """401, 403 and 429 are access controls. CONTRIBUTING.md forbids routing around them."""

    def fake_urlopen(request: Any, timeout: int | None = None) -> FakeResponse:
        raise http_error(code)

    monkeypatch.setattr(acquire_mod.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(AcquisitionBlocked) as caught:
        acquire_mod.fetch_document("https://example.invalid/query")
    assert "by hand" in str(caught.value)
    assert "PROVENANCE.md" in str(caught.value)


@pytest.mark.parametrize("code", [404, 500, 503])
def test_an_endpoint_that_is_broken_rather_than_closed_fails_loudly(
    monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    def fake_urlopen(request: Any, timeout: int | None = None) -> FakeResponse:
        raise http_error(code)

    monkeypatch.setattr(acquire_mod.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(AcquisitionFailed, match=str(code)):
        acquire_mod.fetch_document("https://example.invalid/query")


def test_an_html_answer_is_read_as_a_challenge_page_and_not_parsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Any, timeout: int | None = None) -> FakeResponse:
        return FakeResponse(b"<html>are you a robot</html>", "text/html; charset=utf-8")

    monkeypatch.setattr(acquire_mod.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(AcquisitionBlocked, match="rather than JSON"):
        acquire_mod.fetch_document("https://example.invalid/query")


def test_an_arcgis_error_payload_is_not_mistaken_for_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A GeoServices layer answers 200 with an `error` object. That is not a page of rows."""

    def fake_urlopen(request: Any, timeout: int | None = None) -> FakeResponse:
        return json_response({"error": {"code": 400, "message": "Invalid field"}})

    monkeypatch.setattr(acquire_mod.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(AcquisitionFailed, match="error payload"):
        acquire_mod.fetch_document("https://example.invalid/query")


def test_a_json_content_type_with_a_charset_is_still_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Any, timeout: int | None = None) -> FakeResponse:
        return json_response({"features": []}, "Application/JSON;charset=UTF-8")

    monkeypatch.setattr(acquire_mod.urllib.request, "urlopen", fake_urlopen)
    assert acquire_mod.fetch_document("https://example.invalid/query") == {
        "features": []
    }


# --- fetch_layer: paging, and what it asks the server for ---------------------------


def page(count: int, *, exceeded: bool, start: int = 0) -> dict[str, Any]:
    return {
        "features": [
            {"attributes": {"OBJECTID": start + i, "YEAR_": 2020}} for i in range(count)
        ],
        "exceededTransferLimit": exceeded,
    }


def test_the_query_leaves_geometry_behind_and_orders_the_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urls: list[str] = []

    def fake_get(url: str, **_: object) -> dict[str, Any]:
        urls.append(url)
        return page(1, exceeded=False)

    monkeypatch.setattr(acquire_mod, "fetch_document", fake_get)
    fetch_layer("https://example.invalid/query", ("YEAR_", "GIS_ACRES"))
    assert "returnGeometry=false" in urls[0]
    assert "orderByFields=OBJECTID+ASC" in urls[0]
    assert f"resultRecordCount={PAGE_SIZE}" in urls[0]
    assert "outFields=YEAR_%2CGIS_ACRES" in urls[0]


def test_paging_continues_while_the_layer_says_there_is_more(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        page(PAGE_SIZE, exceeded=True, start=0),
        page(PAGE_SIZE, exceeded=True, start=PAGE_SIZE),
        page(7, exceeded=False, start=2 * PAGE_SIZE),
    ]
    calls: list[str] = []

    def fake_get(url: str, **_: object) -> dict[str, Any]:
        calls.append(url)
        return pages[len(calls) - 1]

    monkeypatch.setattr(acquire_mod, "fetch_document", fake_get)
    monkeypatch.setattr(acquire_mod.time, "sleep", lambda _: None)
    rows = fetch_layer("https://example.invalid/query", ("OBJECTID",))
    assert len(rows) == 2 * PAGE_SIZE + 7
    assert f"resultOffset={PAGE_SIZE}" in calls[1]
    assert f"resultOffset={2 * PAGE_SIZE}" in calls[2]


def test_paging_pauses_between_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pause is a courtesy to somebody else's server. It has to actually happen."""
    slept: list[float] = []
    pages = [page(PAGE_SIZE, exceeded=True), page(1, exceeded=False)]
    calls = 0

    def fake_get(url: str, **_: object) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return pages[calls - 1]

    monkeypatch.setattr(acquire_mod, "fetch_document", fake_get)
    monkeypatch.setattr(acquire_mod.time, "sleep", slept.append)
    fetch_layer("https://example.invalid/query", ("OBJECTID",))
    assert slept == [acquire_mod.PAUSE_SECONDS]


def test_an_empty_first_page_ends_the_walk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        acquire_mod, "fetch_document", lambda url, **_: {"features": []}
    )
    assert fetch_layer("https://example.invalid/query", ("OBJECTID",)) == []


def test_a_short_page_ends_the_walk_even_without_the_transfer_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_get(url: str, **_: object) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return page(3, exceeded=False)

    monkeypatch.setattr(acquire_mod, "fetch_document", fake_get)
    fetch_layer("https://example.invalid/query", ("OBJECTID",))
    assert calls == 1


def test_a_full_page_without_the_transfer_flag_is_still_followed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A layer that fills the page but omits the flag may still have more rows."""
    pages = [page(PAGE_SIZE, exceeded=False), page(0, exceeded=False)]
    calls = 0

    def fake_get(url: str, **_: object) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return pages[calls - 1]

    monkeypatch.setattr(acquire_mod, "fetch_document", fake_get)
    monkeypatch.setattr(acquire_mod.time, "sleep", lambda _: None)
    rows = fetch_layer("https://example.invalid/query", ("OBJECTID",))
    assert calls == 2
    assert len(rows) == PAGE_SIZE


def capped_layer(total: int, cap: int) -> Callable[..., dict[str, Any]]:
    """A layer holding `total` records that never returns more than `cap` per page.

    This is not a hypothetical shape. It is what a GeoServices layer does whenever
    `resultRecordCount` is above its own `maxRecordCount`: it answers with a short page
    and sets `exceededTransferLimit`. Measured against the live POSTFIRE layer on
    2026-08-16, a request for 3,000 records came back with 2,000 and the flag set.

    The fake honours `resultOffset` the way the real service does, so a walk that steps
    its offset by more than the page it was handed steps over real records.
    """

    def fake_get(url: str, **_: object) -> dict[str, Any]:
        query = parse_qs(urlparse(url).query)
        offset = int(query["resultOffset"][0])
        asked = int(query["resultRecordCount"][0])
        served = max(0, min(asked, cap, total - offset))
        return {
            "features": [
                {"attributes": {"OBJECTID": offset + i}} for i in range(served)
            ],
            "exceededTransferLimit": offset + served < total,
        }

    return fake_get


def test_a_capped_page_does_not_step_over_the_records_it_withheld(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The walk must advance by the page it got, never by the page it asked for.

    A layer whose maxRecordCount sits below PAGE_SIZE answers every request with a
    shorter page. Advancing the offset by PAGE_SIZE there skips every record between the
    end of the page and the start of the next offset, and nothing says so: the walk ends
    normally, the file is written, the hash is recorded, and every count downstream
    describes a fraction of the layer as though it were the whole of it.
    """
    total, cap = 5_000, 1_000
    monkeypatch.setattr(acquire_mod, "fetch_document", capped_layer(total, cap))
    monkeypatch.setattr(acquire_mod.time, "sleep", lambda _: None)
    rows = fetch_layer("https://example.invalid/query", ("OBJECTID",))
    assert [row["OBJECTID"] for row in rows] == list(range(total)), (
        f"the layer holds {total} records and the walk collected {len(rows)}"
    )


# --- layer_record_count: the second opinion the walk is checked against --------------


def test_the_count_query_asks_the_layer_the_same_question_the_walk_asks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A count under a different predicate would not be a check on this walk at all."""
    urls: list[str] = []

    def fake_get(url: str, **_: object) -> dict[str, Any]:
        urls.append(url)
        return {"count": 7}

    monkeypatch.setattr(acquire_mod, "fetch_document", fake_get)
    assert layer_record_count("https://example.invalid/query") == 7

    def counting_get(url: str, **_: object) -> dict[str, Any]:
        urls.append(url)
        return {"features": []}

    monkeypatch.setattr(acquire_mod, "fetch_document", counting_get)
    fetch_layer("https://example.invalid/query", ("OBJECTID",))

    counted, walked = (parse_qs(urlparse(url).query) for url in urls)
    assert counted["returnCountOnly"] == ["true"]
    assert counted["where"] == walked["where"], (
        "the total is only a check on this walk if both ask the same question"
    )


@pytest.mark.parametrize(
    "payload", [{}, {"count": None}, {"count": "132522"}, {"count": True}]
)
def test_a_count_response_with_no_usable_count_is_refused(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> None:
    """Unverifiable is not the same as verified. Without a total there is no check."""
    monkeypatch.setattr(acquire_mod, "fetch_document", lambda url, **_: payload)
    with pytest.raises(AcquisitionFailed, match="no count"):
        layer_record_count("https://example.invalid/query")


# --- acquire and main ---------------------------------------------------------------


def one_row_layer(monkeypatch: pytest.MonkeyPatch, *, count: int = 1) -> None:
    """A layer holding one record, with its self-reported total under the test's control."""
    monkeypatch.setattr(
        acquire_mod, "fetch_layer", lambda endpoint, fields, **_: [{"OBJECTID": 1}]
    )
    monkeypatch.setattr(acquire_mod, "layer_record_count", lambda endpoint, **_: count)


def test_a_short_walk_writes_nothing_at_all(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The gate behind every published count: a partial download is not an acquisition.

    Without this, a walk that came back with a fraction of the layer would be written,
    hashed, dated and copied into sources.py as though it were the whole file, and the
    pages would report its counts as the coverage of the layer.
    """
    one_row_layer(monkeypatch, count=132_522)
    with pytest.raises(AcquisitionFailed) as caught:
        acquire(FRAP, ("OBJECTID",), tmp_path)
    assert "132522" in str(caught.value)
    assert "collected 1" in str(caught.value)
    assert not (tmp_path / FRAP.raw_file).exists(), "a short download reached disk"


def test_acquire_records_the_source_it_was_asked_for(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    one_row_layer(monkeypatch)
    result = acquire(FRAP, ("OBJECTID",), tmp_path)
    assert result.source_key == FRAP.key
    assert result.endpoint == FRAP.endpoint
    assert result.path == tmp_path / FRAP.raw_file
    assert result.record_count == 1


def test_main_writes_a_manifest_for_both_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    one_row_layer(monkeypatch)
    assert main(["--out", str(tmp_path)]) == 0
    manifest = json.loads((tmp_path / "acquisition.json").read_text(encoding="utf-8"))
    assert [entry["source"] for entry in manifest] == [FRAP.key, DINS.key]
    for entry in manifest:
        assert len(entry["sha256"]) == 64
        assert entry["record_count"] == 1
    assert "Copy record_count" in capsys.readouterr().out


def test_main_can_be_pointed_at_one_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    one_row_layer(monkeypatch)
    assert main(["--out", str(tmp_path), "--source", DINS.key]) == 0
    manifest = json.loads((tmp_path / "acquisition.json").read_text(encoding="utf-8"))
    assert [entry["source"] for entry in manifest] == [DINS.key]
    assert not (tmp_path / FRAP.raw_file).exists()


def test_main_refuses_a_source_it_does_not_publish(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["--out", str(tmp_path), "--source", "somebody_elses_layer"])


def test_the_fetch_field_lists_do_not_ask_for_geometry() -> None:
    for fields in (acquire_mod.FRAP_FETCH_FIELDS, acquire_mod.DINS_FETCH_FIELDS):
        assert fields
        assert "SHAPE" not in fields
        assert "geometry" not in fields


# --- the library surface a consuming project asked for --------------------------------
#
# `wildfire-service-territory-overlap` pins a commit of this package and audited the seam
# on 2026-09-05, recording four gaps in its docs/UPSTREAM.md. Each one below is one of
# them, checked here rather than compensated for there.


def test_a_caller_can_say_who_it_is_and_that_is_what_is_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gap: the walk sent this project's name whoever was calling.

    An operator reading CAL FIRE's logs saw `perimeter-coverage` for requests a different
    project made, so the header identified the library rather than the caller -- which is
    the one thing a User-Agent exists to do.
    """
    sent: list[str] = []

    def fake_urlopen(request: Any, timeout: int = 0) -> FakeResponse:
        sent.append(request.get_header("User-agent"))
        return json_response({"features": []})

    monkeypatch.setattr(acquire_mod.urllib.request, "urlopen", fake_urlopen)
    acquire_mod.fetch_document(
        "https://example.invalid/query",
        user_agent="somebody-else/2.0 (+https://x.test)",
    )
    assert sent == ["somebody-else/2.0 (+https://x.test)"]


def test_the_default_user_agent_still_names_this_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive control for the test above: the default must not have moved."""
    sent: list[str] = []

    def fake_urlopen(request: Any, timeout: int = 0) -> FakeResponse:
        sent.append(request.get_header("User-agent"))
        return json_response({"features": []})

    monkeypatch.setattr(acquire_mod.urllib.request, "urlopen", fake_urlopen)
    acquire_mod.fetch_document("https://example.invalid/query")
    assert sent == [USER_AGENT]
    assert "perimeter" in USER_AGENT
    assert "github.com/ChelseaKR/perimeter" in USER_AGENT


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_a_blank_user_agent_is_refused_rather_than_passed_through(blank: str) -> None:
    """urllib would substitute `Python-urllib/3.x`, which identifies nobody.

    A caller that passes nothing is not anonymous, it is mislabelled: the request still
    goes out, under a header that names no project at all. That is an absent identity
    sent as though it were one, so it is refused before a socket opens.
    """
    with pytest.raises(AcquisitionFailed, match="blank User-Agent"):
        acquire_mod.fetch_document("https://example.invalid/query", user_agent=blank)


def test_the_user_agent_reaches_the_count_query_and_the_walk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Threaded, not just accepted. A parameter the callee drops is not a parameter."""
    seen: list[object] = []

    def fake_get(url: str, **kwargs: object) -> dict[str, Any]:
        seen.append(kwargs.get("user_agent"))
        if "returnCountOnly" in url:
            return {"count": 1}
        return page(1, exceeded=False)

    monkeypatch.setattr(acquire_mod, "fetch_document", fake_get)
    layer_record_count("https://example.invalid/query", user_agent="caller/1.0")
    fetch_layer("https://example.invalid/query", ("OBJECTID",), user_agent="caller/1.0")
    assert seen == ["caller/1.0", "caller/1.0"]


# --- geometry, which fetch_layer discards and a consumer needed ------------------------


GEOMETRY = {
    "rings": [[[-13_600_000.5, 4_500_000.25], [-13_600_001.0, 4_500_002.75]]],
    "spatialReference": {"wkid": 102_100},
}


def test_geometry_requested_through_the_library_round_trips_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The coordinates that come back are the coordinates the service sent.

    Nothing rounds, reprojects, or normalises them on the way through. A consumer that
    copied the offset loop to get at geometry can now ask for it here instead, and the
    thing it gets is the service's own feature.
    """
    urls: list[str] = []

    def fake_get(url: str, **_: object) -> dict[str, Any]:
        urls.append(url)
        return {
            "features": [{"attributes": {"OBJECTID": 1}, "geometry": GEOMETRY}],
            "exceededTransferLimit": False,
        }

    monkeypatch.setattr(acquire_mod, "fetch_document", fake_get)
    features = list(
        iter_features(
            "https://example.invalid/query",
            ("OBJECTID",),
            return_geometry=True,
            out_sr=3310,
        )
    )
    assert [feature["geometry"] for feature in features] == [GEOMETRY]
    query = parse_qs(urlparse(urls[0]).query)
    assert query["returnGeometry"] == ["true"]
    assert query["outSR"] == ["3310"]


def test_the_default_request_is_the_one_this_project_has_always_made(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The raw files pinned in sources.py must stay reproducible.

    Adding geometry as an option must not add it as a default, and `outSR` must be absent
    rather than sent with a default value: a reprojection nobody asked for would change
    every coordinate in a file whose hash is published. The same holds for `f`: another
    output format is another set of bytes on disk under the same recorded hash.
    """
    urls: list[str] = []

    def fake_get(url: str, **_: object) -> dict[str, Any]:
        urls.append(url)
        return page(1, exceeded=False)

    monkeypatch.setattr(acquire_mod, "fetch_document", fake_get)
    fetch_layer("https://example.invalid/query", ("OBJECTID",))
    query = parse_qs(urlparse(urls[0]).query)
    assert query["returnGeometry"] == ["false"]
    assert "outSR" not in query
    assert query["f"] == ["json"]
    assert DEFAULT_OUT_FORMAT == "json"


# --- output format, which the consumer's fourth layer needs and this walk did not send -


def geojson_page(count: int, *, exceeded: bool, start: int = 0) -> dict[str, Any]:
    """What a GeoServices layer answers to `f=geojson`.

    Two things about it decide whether the walk can be shared. The features are GeoJSON
    `Feature` objects -- no `attributes` key anywhere in them -- and the paging signals
    the walk reads sit at the top level exactly as they do under `f=json`.
    """
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-121.5, 38.5 + i]},
                "properties": {"OBJECTID": start + i, "YEAR_": 2020},
            }
            for i in range(count)
        ],
        "exceededTransferLimit": exceeded,
    }


def test_a_caller_asking_for_geojson_gets_the_services_own_features(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The consuming project reads three polygon layers as GeoJSON and had to copy the
    walk to do it, because this one hard-coded `f=json`.

    What comes back is the service's own `Feature`, whole: no conversion, no rename of
    `properties` to `attributes`, no reprojection. A conversion here would be this
    project rewriting the geometry every measurement downstream runs on.
    """
    urls: list[str] = []
    sent = geojson_page(2, exceeded=False)

    def fake_get(url: str, **_: object) -> dict[str, Any]:
        urls.append(url)
        return sent

    monkeypatch.setattr(acquire_mod, "fetch_document", fake_get)
    features = list(
        iter_features(
            "https://example.invalid/query",
            ("OBJECTID",),
            return_geometry=True,
            out_format="geojson",
        )
    )
    assert features == sent["features"]
    assert all("attributes" not in feature for feature in features)
    assert parse_qs(urlparse(urls[0]).query)["f"] == ["geojson"]


def test_the_capped_page_rule_is_shared_by_the_non_default_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole point of exposing the walk is that the offset rule stops being copied.

    A format that reached the same records by a different path would leave the consumer
    with a second implementation of the subtle part after all, so the rule is exercised
    here under `f=geojson` rather than assumed to be shared. The layer caps its pages
    below what is asked for, which is what makes stepping by the page asked for wrong.
    """
    total, cap = 5_000, 1_000

    def fake_get(url: str, **_: object) -> dict[str, Any]:
        query = parse_qs(urlparse(url).query)
        assert query["f"] == ["geojson"]
        offset = int(query["resultOffset"][0])
        asked = int(query["resultRecordCount"][0])
        served = max(0, min(asked, cap, total - offset))
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": None,
                    "properties": {"OBJECTID": offset + i},
                }
                for i in range(served)
            ],
            "exceededTransferLimit": offset + served < total,
        }

    monkeypatch.setattr(acquire_mod, "fetch_document", fake_get)
    monkeypatch.setattr(acquire_mod.time, "sleep", lambda _: None)
    features = list(
        iter_features(
            "https://example.invalid/query", ("OBJECTID",), out_format="geojson"
        )
    )
    identifiers = [feature["properties"]["OBJECTID"] for feature in features]
    assert identifiers == list(range(total)), (
        f"the layer holds {total} records and the geojson walk collected {len(features)}"
    )


def test_a_format_the_walk_cannot_page_is_refused_before_any_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A format carrying no top-level `features` walks zero records and stops.

    That is indistinguishable from an empty layer: no exception, no short-file warning,
    a clean hash over nothing. The refusal is what keeps this walk from publishing an
    absence as a measurement, so it happens before a socket is opened.

    The planted value is not the next plausible format name. A format this service grows
    into would make the assertion silently vacuous, so it is a string no `f=` parameter
    can ever be.
    """
    unpageable = "f-that-no-geoservices-layer-will-ever-publish"
    assert unpageable not in PAGEABLE_OUT_FORMATS

    def fake_get(url: str, **_: object) -> dict[str, Any]:
        raise AssertionError("the refusal must come before the request")

    monkeypatch.setattr(acquire_mod, "fetch_document", fake_get)
    with pytest.raises(UnpageableFormatError) as raised:
        list(
            iter_features(
                "https://example.invalid/query", ("OBJECTID",), out_format=unpageable
            )
        )
    assert unpageable in str(raised.value)
    assert "features" in str(raised.value)


def test_a_page_with_no_features_key_is_refused_rather_than_read_as_the_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`payload.get("features", [])` made two different facts one value.

    An answer the walk cannot read and a layer that holds nothing both produced an empty
    list, so a service that changed the shape of its reply would have ended the walk on
    its first page and written a file with a clean hash and no records in it. The
    published record count is copied out of that file by hand.
    """

    def fake_get(url: str, **_: object) -> dict[str, Any]:
        return {"objectIdFieldName": "OBJECTID", "exceededTransferLimit": False}

    monkeypatch.setattr(acquire_mod, "fetch_document", fake_get)
    with pytest.raises(AcquisitionFailed) as raised:
        list(iter_features("https://example.invalid/query", ("OBJECTID",)))
    assert "features" in str(raised.value)


def test_a_features_value_that_is_not_a_list_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mapping under `features` walks and produces nonsense, silently.

    `yield from` over a dict yields its keys, and `len()` of it is the number of
    them, so a page shaped that way makes the walk emit strings and step its
    offset by a number that has nothing to do with any record. Nothing raises.

    Found by a consuming project's own copy of this walk, which checked the type
    and would have had to keep the check to move onto this one. That is the sort
    of thing the audit in that repository exists to surface: a compensation
    cannot be retired until the thing it compensates for is gone.
    """

    def fake_get(url: str, **_: object) -> dict[str, Any]:
        return {
            "features": {"OBJECTID": 1, "YEAR_": 2020},
            "exceededTransferLimit": False,
        }

    monkeypatch.setattr(acquire_mod, "fetch_document", fake_get)
    with pytest.raises(AcquisitionFailed) as raised:
        list(iter_features("https://example.invalid/query", ("OBJECTID",)))
    assert "rather than a list" in str(raised.value)


def test_a_layer_that_really_is_empty_is_still_walked_to_a_clean_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other side of the same boundary, and the one an over-broad refusal breaks.

    An empty `features` list is the layer answering the question; only a missing key is
    the layer answering a different one. If this ever fails, the refusal above has been
    widened into a rule that refuses honest emptiness.
    """

    def fake_get(url: str, **_: object) -> dict[str, Any]:
        return {"features": [], "exceededTransferLimit": False}

    monkeypatch.setattr(acquire_mod, "fetch_document", fake_get)
    assert list(iter_features("https://example.invalid/query", ("OBJECTID",))) == []


def test_fetch_layer_takes_no_output_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """It reads `feature["attributes"]`, which only the GeoServices formats carry.

    A format argument here would either raise `KeyError` on every row of a GeoJSON page
    or force a rename of `properties`, which would make this function a converter. The
    signature is the documentation of that decision, so it is pinned.
    """
    assert "out_format" not in inspect.signature(fetch_layer).parameters
    assert "out_format" in inspect.signature(iter_features).parameters


def test_a_feature_is_yielded_whole_rather_than_merged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A layer is free to publish a field called `geometry`, and some do.

    Merging the geometry into the attributes would overwrite it, silently, and the loss
    would look exactly like a layer that never published the field.
    """

    def fake_get(url: str, **_: object) -> dict[str, Any]:
        return {
            "features": [
                {
                    "attributes": {"OBJECTID": 1, "geometry": "a column of that name"},
                    "geometry": GEOMETRY,
                }
            ],
            "exceededTransferLimit": False,
        }

    monkeypatch.setattr(acquire_mod, "fetch_document", fake_get)
    feature = next(
        iter_features(
            "https://example.invalid/query", ("OBJECTID",), return_geometry=True
        )
    )
    assert feature["attributes"]["geometry"] == "a column of that name"
    assert feature["geometry"] == GEOMETRY


# --- the post-walk guards: a count that matches is not enough --------------------------


def scripted_layer(
    monkeypatch: pytest.MonkeyPatch,
    *,
    before: int,
    after: int,
    rows: list[dict[str, Any]],
) -> None:
    """A layer whose two self-reported totals and whose walk are each set separately."""
    counts = iter([before, after])
    monkeypatch.setattr(
        acquire_mod, "layer_record_count", lambda endpoint, **_: next(counts)
    )
    monkeypatch.setattr(acquire_mod, "fetch_layer", lambda endpoint, fields, **_: rows)


def rows_with_ids(*identifiers: object) -> list[dict[str, Any]]:
    return [{IDENTIFIER_FIELD: value, "YEAR_": 2020} for value in identifiers]


def test_a_layer_republished_mid_walk_is_refused_naming_both_counts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One count read before the walk cannot see this.

    The walk ends at a total that matches the number the layer held when it started, so
    the pre-walk check passes and a file assembled across two versions of the layer lands
    on disk with a clean hash and a date beside it.
    """
    scripted_layer(monkeypatch, before=3, after=4, rows=rows_with_ids(1, 2, 3))
    with pytest.raises(AcquisitionFailed) as caught:
        acquire(FRAP, ("OBJECTID",), tmp_path)
    message = str(caught.value)
    assert "3 records before the walk" in message
    assert "4 after it" in message
    assert not (tmp_path / FRAP.raw_file).exists(), "a mixed download reached disk"


def test_a_walk_shorter_than_the_post_walk_count_is_refused_naming_both(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scripted_layer(monkeypatch, before=9, after=9, rows=rows_with_ids(1, 2, 3))
    with pytest.raises(AcquisitionFailed) as caught:
        acquire(FRAP, ("OBJECTID",), tmp_path)
    message = str(caught.value)
    assert "reports 9 records" in message
    assert "collected 3" in message
    assert not (tmp_path / FRAP.raw_file).exists()


def test_a_repeated_identifier_is_refused_even_though_the_count_matches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The failure a record count cannot see.

    A page handed back twice leaves the total intact: the walk collected the right number
    of rows, and some of the layer's records are in it twice while others are not in it
    at all.
    """
    scripted_layer(monkeypatch, before=4, after=4, rows=rows_with_ids(1, 2, 2, 3))
    with pytest.raises(AcquisitionFailed) as caught:
        acquire(FRAP, ("OBJECTID",), tmp_path)
    message = str(caught.value)
    assert "appears more than once" in message
    assert "a count that matches is not evidence" in message.lower()
    assert not (tmp_path / FRAP.raw_file).exists()


def test_a_clean_walk_still_writes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The positive control. A guard that refuses everything is not a guard."""
    scripted_layer(monkeypatch, before=3, after=3, rows=rows_with_ids(1, 2, 3))
    result = acquire(FRAP, ("OBJECTID",), tmp_path)
    assert result.record_count == 3
    assert (tmp_path / FRAP.raw_file).exists()


@pytest.mark.parametrize(
    ("identifiers", "expected"),
    [
        ((1, 2, 3), None),
        ((), None),
        ((1, 2, 2), "appears more than once"),
        ((3, 2, 1), "does not follow"),
        ((1, 1), "appears more than once"),
        (("7", 8), "not an integer"),
        ((True, 2), "not an integer"),
        ((None, 2), "not an integer"),
    ],
)
def test_every_identifier_refusal_is_reachable(
    identifiers: tuple[object, ...], expected: str | None
) -> None:
    """Each branch exercised directly, so none of them is reachable only from a fault.

    `True` is in here on purpose: it is an `int` in Python, and an identifier column that
    came back as a boolean would slip past an `isinstance(value, int)` check written
    without the guard.
    """
    failure = identifier_failure(list(identifiers))
    if expected is None:
        assert failure is None
    else:
        assert failure is not None and expected in failure


def test_the_manifest_records_which_guards_this_acquisition_passed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A file written before the post-walk recount existed makes a weaker claim.

    Nothing in the manifest distinguished the two, so a reader could not tell which
    guarantee a given acquisition carried.
    """
    counts = iter([1, 1, 1, 1])
    monkeypatch.setattr(
        acquire_mod, "layer_record_count", lambda endpoint, **_: next(counts)
    )
    monkeypatch.setattr(
        acquire_mod, "fetch_layer", lambda endpoint, fields, **_: rows_with_ids(1)
    )
    assert main(["--out", str(tmp_path)]) == 0
    manifest = json.loads((tmp_path / "acquisition.json").read_text(encoding="utf-8"))
    for entry in manifest:
        assert entry["checks"]["counted_before_walk"] is True
        assert entry["checks"]["counted_after_walk"] is True
        assert entry["checks"]["identifier_field"] == IDENTIFIER_FIELD
        assert entry["checks"]["identifiers_unique_and_ascending"] is True


# --- PEP 561: a consumer running mypy --strict should need no override -----------------


@pytest.mark.slow
def test_a_strict_consumer_needs_no_override_to_import_this_package(
    tmp_path: Path,
) -> None:
    """The fourth gap in the consumer's audit: no `py.typed`, so two mypy overrides.

    This runs mypy over a minimal consumer rather than asserting the marker file exists,
    because the marker existing and the marker being *shipped and honoured* are different
    facts, and only the second one deletes the consumer's overrides.
    """
    consumer = tmp_path / "consumer.py"
    consumer.write_text(
        "from perimeter.acquire import fetch_layer\n"
        "\n"
        "def rows() -> int:\n"
        "    return len(fetch_layer('https://example.invalid/query', ('OBJECTID',)))\n",
        encoding="utf-8",
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "mypy", "--strict", "--no-incremental", str(consumer)],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "py.typed" not in result.stdout, result.stdout
