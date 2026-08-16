"""The determinism gate has to be able to fail, so this runs it against inputs that should.

README.md claims the build is deterministic, and `tools/determinism.sh` is the check that
backs the claim in CI. A check nobody has ever seen fail is a claim about a claim, so each
case below feeds the script a pair of trees and asserts the exit code it owes.

The two vacuous passes this pins down are the ones the previous inlined version had: a
missing directory (`find` exits 1, but a pipeline under `bash -e` without `pipefail`
reports the last command's status, so the step stayed green) and an empty directory (both
sides hash to the same nothing, so the comparison passed).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

GATE = Path(__file__).resolve().parents[1] / "tools" / "determinism.sh"

IDENTICAL = 0
DIFFERENT = 1
UNUSABLE = 2


def run(*args: Path | str) -> subprocess.CompletedProcess[str]:
    # Fixed argv, absolute interpreter and script, no shell: nothing here is interpolated
    # from anything but the test's own tmp_path.
    return subprocess.run(  # noqa: S603
        [shutil.which("bash") or "/bin/bash", str(GATE), *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
    )


def tree(root: Path, files: dict[str, str]) -> Path:
    for name, body in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def test_the_gate_is_executable() -> None:
    assert GATE.is_file()
    assert GATE.stat().st_mode & 0o111, f"{GATE.name} is not executable"


def test_two_identical_trees_pass(tmp_path: Path) -> None:
    files = {"index.html": "<p>a</p>", "data/x.json": '{"a":1}\n'}
    a = tree(tmp_path / "a", files)
    b = tree(tmp_path / "b", files)
    result = run(a, b)
    assert result.returncode == IDENTICAL, result.stderr
    assert "byte-identical" in result.stdout


def test_a_changed_byte_fails(tmp_path: Path) -> None:
    a = tree(tmp_path / "a", {"index.html": "<p>a</p>"})
    b = tree(tmp_path / "b", {"index.html": "<p>b</p>"})
    result = run(a, b)
    assert result.returncode == DIFFERENT
    assert "differ" in result.stderr


def test_an_extra_file_fails(tmp_path: Path) -> None:
    a = tree(tmp_path / "a", {"index.html": "<p>a</p>"})
    b = tree(tmp_path / "b", {"index.html": "<p>a</p>", "stray.html": "<p>a</p>"})
    assert run(a, b).returncode == DIFFERENT


def test_the_same_bytes_at_a_different_path_fails(tmp_path: Path) -> None:
    """Layout is part of the output, so a moved file is not a determinism pass."""
    a = tree(tmp_path / "a", {"data/x.json": "{}\n"})
    b = tree(tmp_path / "b", {"x.json": "{}\n"})
    assert run(a, b).returncode == DIFFERENT


@pytest.mark.parametrize("side", [0, 1])
def test_an_empty_tree_is_never_a_pass(tmp_path: Path, side: int) -> None:
    """The vacuous pass: two builds that produced nothing are not two identical builds."""
    good = tree(tmp_path / "good", {"index.html": "<p>a</p>"})
    empty = tmp_path / "empty"
    empty.mkdir()
    pair = [empty, good] if side == 0 else [good, empty]
    result = run(*pair)
    assert result.returncode == UNUSABLE
    assert "holds no files" in result.stderr


def test_two_empty_trees_are_never_a_pass(tmp_path: Path) -> None:
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
    assert run(tmp_path / "a", tmp_path / "b").returncode == UNUSABLE


@pytest.mark.parametrize("side", [0, 1])
def test_a_missing_tree_is_never_a_pass(tmp_path: Path, side: int) -> None:
    """The other vacuous pass: a renamed output directory used to keep the step green."""
    good = tree(tmp_path / "good", {"index.html": "<p>a</p>"})
    missing = tmp_path / "not-here"
    pair = [missing, good] if side == 0 else [good, missing]
    result = run(*pair)
    assert result.returncode == UNUSABLE
    assert "not a directory" in result.stderr


def test_a_file_where_a_tree_should_be_is_never_a_pass(tmp_path: Path) -> None:
    good = tree(tmp_path / "good", {"index.html": "<p>a</p>"})
    not_a_dir = tmp_path / "file.txt"
    not_a_dir.write_text("", encoding="utf-8")
    assert run(good, not_a_dir).returncode == UNUSABLE


def test_wrong_arity_is_refused(tmp_path: Path) -> None:
    assert run(tmp_path).returncode == UNUSABLE
    assert run().returncode == UNUSABLE


def test_a_path_with_a_space_in_it_is_hashed_rather_than_split(tmp_path: Path) -> None:
    files = {"a page.html": "<p>a</p>"}
    a = tree(tmp_path / "a", files)
    b = tree(tmp_path / "b", files)
    assert run(a, b).returncode == IDENTICAL
    changed = tree(tmp_path / "c", {"a page.html": "<p>b</p>"})
    assert run(a, changed).returncode == DIFFERENT
