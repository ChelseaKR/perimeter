"""Compare two coverage artifacts value by value.

A refresh of the pinned retrievals replaces ``site/data/perimeters-coverage.json`` and
``site/data/dins-coverage.json`` wholesale. ``git diff`` over those documents shows which
*lines* moved, which is not the same question: a reordered list reads as hundreds of
changes and a single count that moved reads as two. README.md promises the figures "move
only when those retrievals are deliberately refreshed", and a deliberate refresh should be
able to say, leaf by leaf, exactly what it moved.

Three rules decide the shape of this module.

**A disappearance is not a change.** A key present in the old artifact and absent from the
new one means the build stopped publishing something, and that is a different event from a
number moving. It is refused (exit 2) unless ``--allow-removals`` names it as deliberate.

**Absence is a value, and a removal is not.** ADR-0010 records that a domain the layer
stopped publishing is published as ``null``, not omitted. So a field going from ``12`` to
``null`` is a *change to absence*, reported with both sides, and is never counted as a
removal. Collapsing the two would be this portfolio's most common defect in reverse:
absence and non-publication are different facts and the reader needs both.

**Integers are compared as integers.** Every percentage in these artifacts is a
``*_tenths_pct`` integer precisely so that no float ever decides an equality. Nothing here
converts, rounds, or tolerances a value; ``1000`` and ``1000.0`` are a type change and are
reported as one.

Offline, deterministic, and reads only the two files it is given.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

EMPTY_OBJECT = "<empty object>"
"""Marker leaf for ``{}``.

An empty container holds no leaves, so a walk that emitted only scalars would give
``"markers": {}`` no path at all, and deleting the key entirely would then look like no
change. Emitting a marker keeps the key visible to the removal check.
"""

EMPTY_ARRAY = "<empty array>"
"""Marker leaf for ``[]``, for the same reason."""

Leaf = str | int | float | bool | None


@dataclass(frozen=True)
class Change:
    """One leaf whose value differs between the two artifacts."""

    path: str
    old: Leaf
    new: Leaf

    @property
    def is_type_change(self) -> bool:
        """``1000`` to ``1000.0``, or ``0`` to ``"0"``: equal-looking, differently typed."""
        return type(self.old) is not type(self.new)

    def as_row(self) -> dict[str, Any]:
        return {"path": self.path, "old": self.old, "new": self.new}


@dataclass(frozen=True)
class Removal:
    """A leaf the old artifact published and the new one does not carry at all."""

    path: str
    old: Leaf

    def as_row(self) -> dict[str, Any]:
        return {"path": self.path, "old": self.old}


@dataclass(frozen=True)
class Addition:
    """A leaf the new artifact publishes and the old one did not."""

    path: str
    new: Leaf

    def as_row(self) -> dict[str, Any]:
        return {"path": self.path, "new": self.new}


@dataclass(frozen=True)
class Comparison:
    """The whole result, sorted by path so two runs produce identical bytes."""

    changes: tuple[Change, ...]
    additions: tuple[Addition, ...]
    removals: tuple[Removal, ...]
    old_leaves: int
    new_leaves: int

    @property
    def unchanged(self) -> bool:
        return not (self.changes or self.additions or self.removals)

    def as_document(self) -> dict[str, Any]:
        return {
            "changes": [c.as_row() for c in self.changes],
            "additions": [a.as_row() for a in self.additions],
            "removals": [r.as_row() for r in self.removals],
            "leaves_compared": {"old": self.old_leaves, "new": self.new_leaves},
        }


class ArtifactUnreadable(Exception):
    """The input is not an artifact this can compare, so no comparison is reported.

    Per ADR-0004: a check that could not run is not a check that passed. Every way of
    failing to read a file ends here rather than in an empty document that would then
    compare equal to another empty document.
    """


def read_artifact(path: Path) -> dict[str, Any]:
    """Parse one artifact, or refuse. Never returns an empty document as a default."""
    if not path.is_file():
        raise ArtifactUnreadable(f"{path}: no such file")
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        raise ArtifactUnreadable(
            f"{path}: file is empty. An empty file compares equal to another empty "
            "file, which would report 'no change' about two artifacts that were "
            "never read."
        )
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ArtifactUnreadable(f"{path}: not parseable JSON: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ArtifactUnreadable(
            f"{path}: top level is {type(loaded).__name__}, not a JSON object"
        )
    return loaded


def _escape(segment: str) -> str:
    """Keep a path unambiguous when a key contains the characters paths are built from."""
    return segment.replace("~", "~0").replace("/", "~1")


def flatten(document: Any, prefix: str = "") -> dict[str, Leaf]:
    """Every leaf in the document, keyed by a path like ``/fields[3]/present``.

    Lists are walked by index. These artifacts write every list in a declared order
    (fields in registry order, incidents sorted, years ascending), so index is a stable
    identity here and a reordering is a real finding rather than diff noise.
    """
    if isinstance(document, dict):
        if not document:
            return {prefix or "/": EMPTY_OBJECT}
        leaves: dict[str, Leaf] = {}
        for key, value in document.items():
            leaves.update(flatten(value, f"{prefix}/{_escape(str(key))}"))
        return leaves
    if isinstance(document, list):
        if not document:
            return {prefix or "/": EMPTY_ARRAY}
        listed: dict[str, Leaf] = {}
        for index, value in enumerate(document):
            listed.update(flatten(value, f"{prefix}[{index}]"))
        return listed
    return {prefix or "/": document}


def _ignored(path: str, ignore: frozenset[str]) -> bool:
    """True when any segment of the path is a name the caller asked to ignore.

    ``--ignore is_fixture`` is the documented use: comparing a fixture build against
    itself, where that one flag is expected to differ and nothing else is.
    """
    if not ignore:
        return False
    segments = path.replace("[", "/").replace("]", "").split("/")
    return any(segment in ignore for segment in segments)


def compare(
    old: dict[str, Any],
    new: dict[str, Any],
    *,
    ignore: frozenset[str] = frozenset(),
) -> Comparison:
    """Leaf-by-leaf comparison of two parsed artifacts.

    A pure function of two documents, so the tests can run it over documents it must
    report on rather than only over the committed pair.
    """
    old_leaves = {p: v for p, v in flatten(old).items() if not _ignored(p, ignore)}
    new_leaves = {p: v for p, v in flatten(new).items() if not _ignored(p, ignore)}

    changes = tuple(
        sorted(
            (
                Change(path, old_leaves[path], new_leaves[path])
                for path in old_leaves.keys() & new_leaves.keys()
                if old_leaves[path] != new_leaves[path]
                or type(old_leaves[path]) is not type(new_leaves[path])
            ),
            key=lambda change: change.path,
        )
    )
    additions = tuple(
        sorted(
            (Addition(p, new_leaves[p]) for p in new_leaves.keys() - old_leaves.keys()),
            key=lambda addition: addition.path,
        )
    )
    removals = tuple(
        sorted(
            (Removal(p, old_leaves[p]) for p in old_leaves.keys() - new_leaves.keys()),
            key=lambda removal: removal.path,
        )
    )
    return Comparison(
        changes=changes,
        additions=additions,
        removals=removals,
        old_leaves=len(old_leaves),
        new_leaves=len(new_leaves),
    )


def _render(value: Leaf) -> str:
    """One rendering for every value, so ``null`` never prints as a blank."""
    if value is None:
        return "null (absent, per ADR-0010)"
    if isinstance(value, bool):
        return "true" if value else "false"
    return json.dumps(value)


def render_text(comparison: Comparison, *, allow_removals: bool) -> str:
    """The console rendering. States the population it compared, never only the diff."""
    lines: list[str] = []
    if comparison.unchanged:
        lines.append(
            f"no change: {comparison.old_leaves} leaves compared, none differ, "
            "none added, none removed"
        )
        return "\n".join(lines) + "\n"

    if comparison.removals:
        heading = (
            "removed (allowed)" if allow_removals else "REMOVED (refused, see below)"
        )
        lines.append(f"{heading}: {len(comparison.removals)}")
        for removal in comparison.removals:
            lines.append(f"  {removal.path}: {_render(removal.old)} -> not published")
    if comparison.additions:
        lines.append(f"added: {len(comparison.additions)}")
        for addition in comparison.additions:
            lines.append(f"  {addition.path}: not published -> {_render(addition.new)}")
    if comparison.changes:
        lines.append(f"changed: {len(comparison.changes)}")
        for change in comparison.changes:
            note = "  [type change]" if change.is_type_change else ""
            lines.append(
                f"  {change.path}: {_render(change.old)} -> {_render(change.new)}{note}"
            )
    lines.append(
        f"{comparison.old_leaves} leaves in the earlier artifact, "
        f"{comparison.new_leaves} in the later one"
    )
    if comparison.removals and not allow_removals:
        lines.append(
            "refusing: the later artifact stops publishing a key the earlier one "
            "published. If that is deliberate, re-run with --allow-removals; it is "
            "not the same event as a value moving, and ADR-0010 says a domain the "
            "layer stopped publishing is written as null rather than dropped."
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None, stdout: TextIO | None = None) -> int:
    """``0`` no change, ``1`` changes reported, ``2`` removals refused or unreadable."""
    out = stdout if stdout is not None else sys.stdout
    parser = argparse.ArgumentParser(
        prog="python -m perimeter.diff",
        description=(
            "Compare two coverage artifacts leaf by leaf. Offline; reads only the two "
            "files given."
        ),
    )
    parser.add_argument("old", type=Path, help="the earlier artifact")
    parser.add_argument("new", type=Path, help="the later artifact")
    parser.add_argument(
        "--allow-removals",
        action="store_true",
        help="accept a key the later artifact stops publishing (exit 1 instead of 2)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="write the comparison as JSON rows sorted by path",
    )
    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        metavar="NAME",
        help="ignore any path segment with this name (repeatable, e.g. is_fixture)",
    )
    args = parser.parse_args(argv)

    try:
        old = read_artifact(args.old)
        new = read_artifact(args.new)
    except ArtifactUnreadable as exc:
        print(f"perimeter.diff: {exc}", file=sys.stderr)
        return 2

    comparison = compare(old, new, ignore=frozenset(args.ignore))
    if args.json:
        print(
            json.dumps(comparison.as_document(), indent=2, sort_keys=True),
            file=out,
        )
    else:
        print(
            render_text(comparison, allow_removals=args.allow_removals),
            end="",
            file=out,
        )

    if comparison.removals and not args.allow_removals:
        return 2
    if comparison.unchanged:
        return 0
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
