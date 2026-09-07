"""The published contract for the artifacts, held to the writer in both directions.

``site/data/*.json`` are the product and until now their only contract was this
repository's source. The three-state model is the whole point of the measurement and it
is invisible in the JSON: ``"EAVES": [222, 0, 0]`` means nothing without
:data:`perimeter.artifacts.FIELD_STATE_ORDER`.

A schema that merely *describes* an artifact rots the moment the writer moves, and rots
silently, which is the failure mode this repository refuses everywhere else (ADR 0004: a
gate must be able to fail). So every object in these schemas closes with
``additionalProperties: false`` and requires every key it declares, and the schemas are
run against a real build rather than against a hand-written sample. That gives both
directions:

* the **writer** starts emitting a key the schema does not declare — validation fails on
  an unexpected property;
* the **schema** starts requiring a key the writer does not emit — validation fails on a
  missing one.

The one case neither direction catches is a key the schema declares *optional* that
nothing emits, so :func:`test_every_optional_key_is_one_the_writer_can_omit` pins that
set to the two keys :func:`perimeter.artifacts._field_json` actually writes
conditionally, and proves each is omitted for some field of the real artifact.

``TestTheGateCanFail`` is the ADR-0004 half: the validator is shown failing on the
mutations it exists to catch, including the one named in issue #63 — a fixture artifact
with ``field_state_order`` removed must fail, and the error must name the path.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from perimeter.artifacts import ARTIFACT_SCHEMA_VERSION, FIELD_STATE_ORDER
from perimeter.cli import build_site
from perimeter.schema_export import (
    SCHEMAS,
    datapackage,
    dins_schema,
    perimeters_schema,
    write,
)
from perimeter.sources import DINS, FRAP, Source

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE = REPO_ROOT / "site"
SITE_DATA = SITE / "data"
FIXTURES = REPO_ROOT / "fixtures"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

#: Artifact file to the function that declares its contract.
CONTRACTS = {
    "perimeters-coverage.json": perimeters_schema,
    "dins-coverage.json": dins_schema,
}

#: The keys `perimeter.artifacts._field_json` writes conditionally, and nothing else.
#: Every other key in every object of both artifacts is required.
OPTIONAL_FIELD_KEYS = {"recorded_zero_values", "note"}


@pytest.fixture(scope="module")
def fixture_build(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A complete build from the committed fixtures, into a temporary directory."""
    out = tmp_path_factory.mktemp("schema-site")
    build_site(
        perimeters_source=FIXTURES / "frap_perimeters.sample.json",
        dins_source=FIXTURES / "dins_postfire.sample.json",
        out_dir=out,
        is_fixture=True,
    )
    return out / "data"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(CONTRACTS[name]())


def _errors(name: str, document: Any) -> list[str]:
    validator = _validator(name)
    return [
        "/".join(str(part) for part in error.absolute_path) + ": " + error.message
        for error in validator.iter_errors(document)
    ]


# --------------------------------------------------------------------------------------
# The schemas are real schemas, and they are what the build wrote.
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_each_schema_is_a_valid_draft_2020_12_document(name: str) -> None:
    """Otherwise a consumer's validator rejects the contract rather than the data."""
    Draft202012Validator.check_schema(CONTRACTS[name]())


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_the_written_schema_is_the_generated_one(
    fixture_build: Path, name: str
) -> None:
    """Compared, not regenerated in place.

    A gate that rewrites the artifact it checks repairs the drift it exists to report
    and then has nothing to report, which is the shape ``make site-check`` is written
    around.
    """
    assert _load(fixture_build / "schema" / name) == SCHEMAS[name]()


def test_the_build_writes_the_schemas_and_the_descriptor(fixture_build: Path) -> None:
    written = {path.name for path in fixture_build.rglob("*.json")}
    assert written == {
        "perimeters-coverage.json",
        "dins-coverage.json",
        "datapackage.json",
        "perimeters-coverage.schema.json",
        "dins-coverage.schema.json",
    }


def test_writing_twice_produces_the_same_bytes(tmp_path: Path) -> None:
    """These files join the artifacts under the determinism claim, so they must hold it."""
    first = tmp_path / "one"
    second = tmp_path / "two"
    write(first, is_fixture=False)
    write(second, is_fixture=False)
    for path in sorted(first.rglob("*.json")):
        other = second / path.relative_to(first)
        assert path.read_bytes() == other.read_bytes(), path.name


# --------------------------------------------------------------------------------------
# The contract, against a real build and against what is published.
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_the_fixture_build_validates(fixture_build: Path, name: str) -> None:
    assert _errors(name, _load(fixture_build / name)) == []


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_the_committed_artifact_validates(name: str) -> None:
    """The published bytes, not a rebuild of them.

    ``site/`` is a committed artifact standing in for a computation over files that are
    not in git. This is the half of that computation a schema can settle offline.
    """
    assert _errors(name, _load(SITE_DATA / name)) == []


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_the_artifact_declares_the_schema_version(name: str) -> None:
    assert _load(SITE_DATA / name)["artifact_schema_version"] == ARTIFACT_SCHEMA_VERSION


def _objects(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _objects(value)
    elif isinstance(node, list):
        for value in node:
            yield from _objects(value)


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_every_object_in_the_schema_is_closed(name: str) -> None:
    """An open object makes the schema a description rather than a gate.

    Without ``additionalProperties: false`` a key the writer starts emitting validates
    silently, which is exactly how a contract stops describing its artifact.
    """
    open_objects = [
        node
        for node in _objects(CONTRACTS[name]())
        if node.get("type") == "object" and "properties" in node
        if node.get("additionalProperties") is not False
    ]
    assert open_objects == []


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_every_optional_key_is_one_the_writer_can_omit(name: str) -> None:
    """The one direction validation cannot check, named explicitly.

    A key the schema marks optional that nothing ever emits would sit in the contract
    forever without failing anything. There are exactly two, both written conditionally
    by ``_field_json``, and both are shown below to be genuinely absent somewhere in the
    published artifact.
    """
    optional: set[str] = set()
    for node in _objects(CONTRACTS[name]()):
        if node.get("type") == "object" and "properties" in node:
            optional |= set(node["properties"]) - set(node.get("required", []))
    assert optional == OPTIONAL_FIELD_KEYS

    published = _load(SITE_DATA / name)["fields"]
    for key in OPTIONAL_FIELD_KEYS:
        assert any(key not in field for field in published), (
            f"{key!r} is declared optional and every field in {name} carries it"
        )
        assert any(key in field for field in published), (
            f"{key!r} is declared in the schema and no field in {name} carries it"
        )


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_the_schema_publishes_what_the_three_counts_mean(name: str) -> None:
    """The reason this contract exists at all.

    ``[222, 0, 0]`` is unreadable without the order and the meaning of the three states,
    and neither was anywhere in the JSON.
    """
    schema = CONTRACTS[name]()
    assert schema["field_state_order"] == list(FIELD_STATE_ORDER)
    text = json.dumps(schema)
    assert "recorded unknown" in text or "could not be determined" in text
    for state in FIELD_STATE_ORDER:
        assert state in text


# --------------------------------------------------------------------------------------
# The descriptor, held to the reviewed provenance record.
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("source", [FRAP, DINS], ids=lambda s: s.key)
def test_the_descriptor_states_the_reviewed_acquisition_facts(source: Source) -> None:
    """`PROVENANCE.md` is held to `sources.py`; so is this.

    A descriptor is the most quotable place a wrong hash or a wrong retrieval date could
    end up, because it is the file a downstream tool reads rather than a person.
    """
    resource = next(
        item
        for item in datapackage(is_fixture=False)["resources"]
        if item["name"] == source.key
    )
    stated = resource["sources"][0]
    assert stated["hash"] == f"sha256:{source.sha256}"
    assert stated["retrieved"] == source.retrieved
    assert stated["bytes"] == source.raw_bytes
    assert stated["recordCount"] == source.record_count
    assert stated["endpoint"] == source.endpoint
    assert stated["version"] == source.version
    assert resource["licenses"][0]["path"] == source.licence_url


def test_a_fixture_descriptor_publishes_no_acquisition_facts() -> None:
    """A fixture was never downloaded from anywhere, so it states nothing about a file.

    Absence is published as absence, the same way the artifacts do it. A fixture
    descriptor carrying the real file's checksum would be a fixture passing itself off
    as a measurement of CAL FIRE's data, in the one document a machine reads.
    """
    descriptor = datapackage(is_fixture=True)
    assert descriptor["isFixture"] is True
    for resource in descriptor["resources"]:
        stated = resource["sources"][0]
        assert stated["hash"] is None
        assert stated["retrieved"] is None
        assert stated["bytes"] is None
        assert stated["recordCount"] is None
        assert stated["version"] is None
        # Policy, not acquisition: true of the source whatever produced this build.
        assert stated["dataTier"] == "L1"
        assert isinstance(stated["stalenessSlaDays"], int)


def test_the_committed_descriptor_is_a_real_build(fixture_build: Path) -> None:
    committed = _load(SITE_DATA / "datapackage.json")
    assert committed["isFixture"] is False
    assert committed == datapackage(is_fixture=False)
    assert _load(fixture_build / "datapackage.json")["isFixture"] is True


def test_the_descriptor_names_a_schema_that_exists(fixture_build: Path) -> None:
    """A descriptor pointing at a schema nothing writes is a broken contract."""
    for resource in datapackage(is_fixture=False)["resources"]:
        assert (fixture_build / resource["jsonSchema"]).is_file()
        assert (fixture_build / resource["path"]).is_file()
        assert (SITE_DATA / resource["jsonSchema"]).is_file()
        assert (SITE_DATA / resource["path"]).is_file()


def test_the_descriptor_carries_the_state_order_and_its_meaning() -> None:
    descriptor = datapackage(is_fixture=False)
    assert descriptor["fieldStateOrder"] == list(FIELD_STATE_ORDER)
    assert "could not be determined" in descriptor["fieldStateMeaning"]
    assert descriptor["artifactSchemaVersion"] == ARTIFACT_SCHEMA_VERSION


def test_the_pages_link_the_contract() -> None:
    """The artifacts are the product; a reader has to be able to find their terms."""
    for page in ("index.html", "perimeters.html", "dins.html"):
        markup = (SITE / page).read_text(encoding="utf-8")
        assert 'href="data/datapackage.json"' in markup, page
        assert 'href="data/schema/perimeters-coverage.schema.json"' in markup, page
        assert 'href="data/schema/dins-coverage.schema.json"' in markup, page


def test_the_changelog_states_the_rule_for_bumping_the_schema_version() -> None:
    """The rule lives in two places, so neither may be edited alone."""
    text = CHANGELOG.read_text(encoding="utf-8")
    assert "artifact_schema_version" in text
    assert "additionalProperties" in text


# --------------------------------------------------------------------------------------
# ADR 0004: the gate is adopted only once it has been seen to fail.
# --------------------------------------------------------------------------------------


class TestTheGateCanFail:
    """Each mutation is one this contract exists to catch, run against a real build."""

    def test_a_removed_field_state_order_fails_and_names_the_path(
        self, fixture_build: Path
    ) -> None:
        """The case named in the issue, verbatim."""
        document = _load(fixture_build / "dins-coverage.json")
        del document["field_state_order"]
        problems = _errors("dins-coverage.json", document)
        assert problems, "removing field_state_order validated"
        assert any("field_state_order" in problem for problem in problems)

    def test_a_key_the_schema_does_not_declare_fails(self, fixture_build: Path) -> None:
        """The direction that catches the writer moving without the schema."""
        document = _load(fixture_build / "perimeters-coverage.json")
        document["records_measured_last_tuesday"] = 4
        problems = _errors("perimeters-coverage.json", document)
        assert any("records_measured_last_tuesday" in problem for problem in problems)

    def test_a_new_key_inside_a_nested_object_fails(self, fixture_build: Path) -> None:
        """Closure has to hold at every depth, not only at the root."""
        document = _load(fixture_build / "dins-coverage.json")
        document["incidents_detail"][0]["assessed_share"] = 12
        problems = _errors("dins-coverage.json", document)
        assert any("assessed_share" in problem for problem in problems)

    def test_a_count_published_as_a_string_fails(self, fixture_build: Path) -> None:
        document = _load(fixture_build / "perimeters-coverage.json")
        document["records"] = str(document["records"])
        assert _errors("perimeters-coverage.json", document) != []

    def test_a_share_over_nothing_published_as_a_number_is_still_typed(
        self, fixture_build: Path
    ) -> None:
        """Null is the published value for an empty denominator, and it must stay legal.

        The inverse of the usual defect: a schema that forbade null here would push a
        future writer towards publishing ``0`` for a share nothing was computed over.
        """
        document = _load(fixture_build / "perimeters-coverage.json")
        document["fields"][0]["present_tenths_pct"] = None
        assert _errors("perimeters-coverage.json", document) == []
        document["fields"][0]["present_tenths_pct"] = "89.4%"
        assert _errors("perimeters-coverage.json", document) != []

    def test_an_incident_triple_of_the_wrong_length_fails(
        self, fixture_build: Path
    ) -> None:
        """Three states, so three counts. A pair would read as a two-state model."""
        document = _load(fixture_build / "dins-coverage.json")
        first = document["incidents_detail"][0]["fields"]
        key = next(iter(first))
        first[key] = first[key][:2]
        assert _errors("dins-coverage.json", document) != []

    def test_the_wrong_schema_version_fails(self, fixture_build: Path) -> None:
        """A consumer pinned to this contract must reject an artifact from another."""
        document = _load(fixture_build / "dins-coverage.json")
        document["artifact_schema_version"] = ARTIFACT_SCHEMA_VERSION + 1
        assert _errors("dins-coverage.json", document) != []

    def test_a_dropped_caveat_field_fails(self, fixture_build: Path) -> None:
        """The publisher's quote is what every measurement here answers."""
        document = _load(fixture_build / "perimeters-coverage.json")
        del document["source"]["caveats"][0]["quote"]
        problems = _errors("perimeters-coverage.json", document)
        assert any("quote" in problem for problem in problems)
