"""The artifact diff, and the artifacts it must refuse.

Per ADR-0004 a gate is not adopted until it has been seen to fail, so most of this module
is documents the comparison has to report on: a removed key, a changed count, a type
change, a reordered list, an empty file, an unparseable one, and a file that is not there.
The positive control matters as much: an artifact compared against itself must report
nothing, or "no change" would just be what this prints when it cannot see.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from perimeter.diff import (
    EMPTY_ARRAY,
    EMPTY_OBJECT,
    ArtifactUnreadable,
    compare,
    flatten,
    main,
    read_artifact,
    render_text,
)

ROOT = Path(__file__).resolve().parents[1]
COMMITTED = ROOT / "site" / "data"


def artifact() -> dict[str, Any]:
    """A small document with every shape these artifacts actually contain."""
    return {
        "measurement": "Coverage of something",
        "is_fixture": False,
        "records": 132522,
        "duplicate_signals": [
            {"key": "irwin_id", "reused_keys": 8, "records_sharing_a_key": 23},
        ],
        "fields": [
            {"name": "DAMAGE", "present": 132522, "tenths_pct": 1000},
            {"name": "EAVES", "present": 0, "tenths_pct": None},
        ],
        "markers": {},
        "years": [],
    }


def write(tmp_path: Path, name: str, document: dict[str, Any]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return path


# --- the walk -----------------------------------------------------------------


def test_every_scalar_gets_a_path() -> None:
    leaves = flatten(artifact())
    assert leaves["/records"] == 132522
    assert leaves["/fields[0]/present"] == 132522
    assert leaves["/duplicate_signals[0]/reused_keys"] == 8


def test_a_null_is_a_leaf_with_a_value_not_a_missing_path() -> None:
    """ADR-0010: a domain the layer stopped publishing is written as null."""
    leaves = flatten(artifact())
    assert "/fields[1]/tenths_pct" in leaves
    assert leaves["/fields[1]/tenths_pct"] is None


def test_empty_containers_are_visible_to_the_walk() -> None:
    """Otherwise deleting the key outright would compare as no change."""
    leaves = flatten(artifact())
    assert leaves["/markers"] == EMPTY_OBJECT
    assert leaves["/years"] == EMPTY_ARRAY


def test_a_key_containing_a_slash_cannot_forge_another_path() -> None:
    assert flatten({"a/b": 1}) == {"/a~1b": 1}
    assert flatten({"a": {"b": 1}}) == {"/a/b": 1}


# --- the positive control -----------------------------------------------------


def test_an_artifact_against_itself_reports_nothing() -> None:
    result = compare(artifact(), artifact())
    assert result.unchanged
    assert result.changes == ()
    assert result.additions == ()
    assert result.removals == ()
    assert result.old_leaves > 0, "a walk that found nothing would also look unchanged"


def test_no_change_states_the_population_it_compared() -> None:
    text = render_text(compare(artifact(), artifact()), allow_removals=False)
    assert "no change" in text
    assert "leaves compared" in text


@pytest.mark.parametrize("name", ["perimeters-coverage.json", "dins-coverage.json"])
def test_the_committed_artifacts_compare_equal_to_themselves(name: str) -> None:
    """Over the real documents, not only the small one written for this module."""
    document = read_artifact(COMMITTED / name)
    result = compare(document, document)
    assert result.unchanged
    assert result.old_leaves > 500, f"{name} walked to only {result.old_leaves} leaves"


# --- the changes it must report ------------------------------------------------


def test_a_changed_count_is_reported_with_both_values() -> None:
    later = artifact()
    later["records"] = 132600
    result = compare(artifact(), later)
    assert not result.unchanged
    assert [c.as_row() for c in result.changes] == [
        {"path": "/records", "old": 132522, "new": 132600}
    ]


def test_a_number_becoming_null_is_a_change_and_never_a_removal() -> None:
    later = artifact()
    later["fields"][0]["tenths_pct"] = None
    result = compare(artifact(), later)
    assert result.removals == ()
    assert result.changes[0].path == "/fields[0]/tenths_pct"
    assert result.changes[0].new is None
    assert "null" in render_text(result, allow_removals=False)


def test_a_type_change_is_reported_even_when_the_values_look_equal() -> None:
    """1000 and 1000.0 are equal in Python and are not the same published value."""
    later = artifact()
    later["fields"][0]["tenths_pct"] = 1000.0
    result = compare(artifact(), later)
    assert len(result.changes) == 1
    assert result.changes[0].is_type_change
    assert "[type change]" in render_text(result, allow_removals=False)


def test_a_reordered_list_is_reported_rather_than_smoothed_away() -> None:
    later = artifact()
    later["fields"] = list(reversed(later["fields"]))
    result = compare(artifact(), later)
    assert result.changes, "these artifacts write lists in a declared order"


def test_a_removed_key_is_a_removal_not_a_change() -> None:
    later = artifact()
    del later["duplicate_signals"]
    result = compare(artifact(), later)
    assert [r.path for r in result.removals] == [
        "/duplicate_signals[0]/key",
        "/duplicate_signals[0]/records_sharing_a_key",
        "/duplicate_signals[0]/reused_keys",
    ]
    assert result.changes == ()


def test_an_added_key_is_reported_as_an_addition() -> None:
    later = artifact()
    later["geometry_acquired"] = False
    result = compare(artifact(), later)
    assert [a.as_row() for a in result.additions] == [
        {"path": "/geometry_acquired", "new": False}
    ]


def test_rows_are_sorted_by_path_so_two_runs_agree() -> None:
    later = artifact()
    later["records"] = 1
    later["fields"][0]["present"] = 2
    later["duplicate_signals"][0]["reused_keys"] = 3
    paths = [c.path for c in compare(artifact(), later).changes]
    assert paths == sorted(paths)


def test_ignore_drops_the_named_segment_and_nothing_else() -> None:
    later = artifact()
    later["is_fixture"] = True
    later["records"] = 1
    assert len(compare(artifact(), later).changes) == 2
    ignored = compare(artifact(), later, ignore=frozenset({"is_fixture"}))
    assert [c.path for c in ignored.changes] == ["/records"]


# --- the inputs it must refuse -------------------------------------------------


def test_a_missing_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ArtifactUnreadable, match="no such file"):
        read_artifact(tmp_path / "absent.json")


def test_an_empty_file_is_refused_rather_than_compared(tmp_path: Path) -> None:
    """Two empty files compare equal, which would print 'no change' about nothing.

    The filename here deliberately does not contain the word being matched. It did once,
    and a negative control (deleting the emptiness check outright) still passed: the file
    then failed as unparseable JSON, and `match="empty"` was satisfied by `empty.json` in
    the message. A pattern a path can satisfy is not an assertion about a reason.
    """
    path = tmp_path / "nothing-here.json"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ArtifactUnreadable, match="file is empty"):
        read_artifact(path)


def test_an_unparseable_file_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ArtifactUnreadable, match="not parseable"):
        read_artifact(path)


def test_a_json_document_that_is_not_an_object_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ArtifactUnreadable, match="not a JSON object"):
        read_artifact(path)


# --- exit codes ----------------------------------------------------------------


def run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, stdout=out)
    return code, out.getvalue()


def test_identical_artifacts_exit_zero(tmp_path: Path) -> None:
    old = write(tmp_path, "old.json", artifact())
    new = write(tmp_path, "new.json", artifact())
    code, text = run([str(old), str(new)])
    assert code == 0
    assert "no change" in text


def test_a_changed_value_exits_one(tmp_path: Path) -> None:
    later = artifact()
    later["records"] = 9
    old = write(tmp_path, "old.json", artifact())
    new = write(tmp_path, "new.json", later)
    code, text = run([str(old), str(new)])
    assert code == 1
    assert "/records" in text
    assert "132522" in text and "9" in text


def test_a_removal_exits_two_and_names_the_key(tmp_path: Path) -> None:
    later = artifact()
    del later["duplicate_signals"]
    old = write(tmp_path, "old.json", artifact())
    new = write(tmp_path, "new.json", later)
    code, text = run([str(old), str(new)])
    assert code == 2
    assert "duplicate_signals" in text
    assert "--allow-removals" in text


def test_the_same_removal_exits_one_when_it_is_declared_deliberate(
    tmp_path: Path,
) -> None:
    later = artifact()
    del later["duplicate_signals"]
    old = write(tmp_path, "old.json", artifact())
    new = write(tmp_path, "new.json", later)
    code, text = run([str(old), str(new), "--allow-removals"])
    assert code == 1
    assert "duplicate_signals" in text
    assert "removed (allowed)" in text


def test_an_unreadable_input_exits_two(tmp_path: Path) -> None:
    old = write(tmp_path, "old.json", artifact())
    code, _ = run([str(old), str(tmp_path / "absent.json")])
    assert code == 2


def test_json_output_is_byte_identical_on_repeat(tmp_path: Path) -> None:
    later = artifact()
    later["records"] = 9
    later["fields"][0]["present"] = 4
    old = write(tmp_path, "old.json", artifact())
    new = write(tmp_path, "new.json", later)
    first = run([str(old), str(new), "--json"])
    second = run([str(old), str(new), "--json"])
    assert first == second
    document = json.loads(first[1])
    assert document["changes"] == [
        {"path": "/fields[0]/present", "old": 132522, "new": 4},
        {"path": "/records", "old": 132522, "new": 9},
    ]
    assert document["leaves_compared"]["old"] == document["leaves_compared"]["new"]


def test_the_committed_pair_compares_clean_through_the_command(tmp_path: Path) -> None:
    """End to end over a real artifact, so the command is exercised on the real shape."""
    source = COMMITTED / "dins-coverage.json"
    copy = tmp_path / "copy.json"
    copy.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    code, text = run([str(source), str(copy)])
    assert code == 0, text
