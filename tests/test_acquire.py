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

import io
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import pytest

from perimeter import acquire as acquire_mod
from perimeter.acquire import (
    PAGE_SIZE,
    USER_AGENT,
    AcquisitionBlocked,
    AcquisitionFailed,
    acquire,
    fetch_layer,
    main,
    write_rows,
)
from perimeter.sources import DINS, FRAP


class FakeResponse(io.BytesIO):
    """The two attributes `_get` reads off a urlopen result, and nothing else."""

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


# --- _get: the refusals -------------------------------------------------------------


def test_a_non_https_endpoint_is_refused_before_any_socket_opens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("urlopen must not be reached for a non-HTTPS URL")

    monkeypatch.setattr(acquire_mod.urllib.request, "urlopen", explode)
    with pytest.raises(AcquisitionFailed, match="non-HTTPS"):
        acquire_mod._get("http://example.invalid/query")
    with pytest.raises(AcquisitionFailed, match="non-HTTPS"):
        acquire_mod._get("file:///etc/passwd")


def test_the_request_names_the_project_rather_than_imitating_a_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    def fake_urlopen(request: Any, timeout: int | None = None) -> FakeResponse:
        seen.update(request.headers)
        return json_response({"features": []})

    monkeypatch.setattr(acquire_mod.urllib.request, "urlopen", fake_urlopen)
    acquire_mod._get("https://example.invalid/query")
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
        acquire_mod._get("https://example.invalid/query")
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
        acquire_mod._get("https://example.invalid/query")


def test_an_html_answer_is_read_as_a_challenge_page_and_not_parsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Any, timeout: int | None = None) -> FakeResponse:
        return FakeResponse(b"<html>are you a robot</html>", "text/html; charset=utf-8")

    monkeypatch.setattr(acquire_mod.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(AcquisitionBlocked, match="rather than JSON"):
        acquire_mod._get("https://example.invalid/query")


def test_an_arcgis_error_payload_is_not_mistaken_for_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A GeoServices layer answers 200 with an `error` object. That is not a page of rows."""

    def fake_urlopen(request: Any, timeout: int | None = None) -> FakeResponse:
        return json_response({"error": {"code": 400, "message": "Invalid field"}})

    monkeypatch.setattr(acquire_mod.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(AcquisitionFailed, match="error payload"):
        acquire_mod._get("https://example.invalid/query")


def test_a_json_content_type_with_a_charset_is_still_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Any, timeout: int | None = None) -> FakeResponse:
        return json_response({"features": []}, "Application/JSON;charset=UTF-8")

    monkeypatch.setattr(acquire_mod.urllib.request, "urlopen", fake_urlopen)
    assert acquire_mod._get("https://example.invalid/query") == {"features": []}


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

    def fake_get(url: str) -> dict[str, Any]:
        urls.append(url)
        return page(1, exceeded=False)

    monkeypatch.setattr(acquire_mod, "_get", fake_get)
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

    def fake_get(url: str) -> dict[str, Any]:
        calls.append(url)
        return pages[len(calls) - 1]

    monkeypatch.setattr(acquire_mod, "_get", fake_get)
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

    def fake_get(url: str) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return pages[calls - 1]

    monkeypatch.setattr(acquire_mod, "_get", fake_get)
    monkeypatch.setattr(acquire_mod.time, "sleep", slept.append)
    fetch_layer("https://example.invalid/query", ("OBJECTID",))
    assert slept == [acquire_mod.PAUSE_SECONDS]


def test_an_empty_first_page_ends_the_walk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acquire_mod, "_get", lambda url: {"features": []})
    assert fetch_layer("https://example.invalid/query", ("OBJECTID",)) == []


def test_a_short_page_ends_the_walk_even_without_the_transfer_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_get(url: str) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return page(3, exceeded=False)

    monkeypatch.setattr(acquire_mod, "_get", fake_get)
    fetch_layer("https://example.invalid/query", ("OBJECTID",))
    assert calls == 1


def test_a_full_page_without_the_transfer_flag_is_still_followed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A layer that fills the page but omits the flag may still have more rows."""
    pages = [page(PAGE_SIZE, exceeded=False), page(0, exceeded=False)]
    calls = 0

    def fake_get(url: str) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return pages[calls - 1]

    monkeypatch.setattr(acquire_mod, "_get", fake_get)
    monkeypatch.setattr(acquire_mod.time, "sleep", lambda _: None)
    rows = fetch_layer("https://example.invalid/query", ("OBJECTID",))
    assert calls == 2
    assert len(rows) == PAGE_SIZE


# --- acquire and main ---------------------------------------------------------------


def test_acquire_records_the_source_it_was_asked_for(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        acquire_mod, "fetch_layer", lambda endpoint, fields: [{"OBJECTID": 1}]
    )
    result = acquire(FRAP, ("OBJECTID",), tmp_path)
    assert result.source_key == FRAP.key
    assert result.endpoint == FRAP.endpoint
    assert result.path == tmp_path / FRAP.raw_file
    assert result.record_count == 1


def test_main_writes_a_manifest_for_both_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        acquire_mod, "fetch_layer", lambda endpoint, fields: [{"OBJECTID": 1}]
    )
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
    monkeypatch.setattr(
        acquire_mod, "fetch_layer", lambda endpoint, fields: [{"OBJECTID": 1}]
    )
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
