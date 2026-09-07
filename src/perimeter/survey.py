"""Inventory the candidate markers in a retrieval, before a build refuses one.

A refresh currently begins from a crash. :class:`~perimeter.cells.SentinelDriftError`
fails the build the first time a field holds something that reads like a missing-data
marker nobody has reviewed for that field, which is the right behaviour and a poor way to
find out: it reports one cell, in one field, and says nothing about the next one. Working
through a new retrieval that way means running the build, reading a refusal, reviewing a
field, and running it again, once per undeclared marker in the file.

This reads the same files the build reads and reports every candidate at once. It
declares nothing. It writes no schema, edits no registry, and touches neither artifact:
its output is a review aid, and every candidate it finds carries ``basis: unreviewed``
so it cannot be mistaken for a decision somebody made.

The intended sequence for a refresh is survey, review, declare, build, diff.

Four rules govern what it prints, and they are the same rules the rest of this project
publishes under.

* **The sentinel decision is not re-implemented here.** Every candidate is found through
  :meth:`~perimeter.schema.FieldSpec.undeclared_marker`, which is what the build's gate
  itself calls. A survey with its own copy of the rule would go quiet at exactly the
  moment the rule moved.
* **A bound that hides values says so.** A field with more distinct values than the
  listing bound reports its distinct count and ``values_listed: false``. It does not
  report an empty list, which would read as a field holding nothing.
* **No published domain is not zero values outside one.** ``outside_published_domain`` is
  ``null`` for a field that publishes no domain, and a list (possibly empty) for a field
  that does. The distinction is ADR-0010's and it is the reason this file never writes
  ``0`` for a comparison that did not happen.
* **A share over nothing does not exist.** The zero share of a numeric field with no
  parsable numbers is ``null``, not ``0``.

It is offline, reads only the files it is pointed at, and writes byte-identical output
for byte-identical input.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from perimeter.cells import normalize_marker, present_tenths_of_percent
from perimeter.records import load_rows
from perimeter.schema import (
    DINS_FIELDS,
    DINS_REQUIRED_COLUMNS,
    FRAP_FIELDS,
    FRAP_REQUIRED_COLUMNS,
    FieldSpec,
    SchemaDriftError,
    require_columns,
)

LISTING_BOUND = 25
"""How many distinct values a field may hold before the survey stops listing them.

A free-text column holds tens of thousands of distinct values and listing them is not a
review aid, it is the file again. Above this bound the survey reports the distinct count,
the marker candidates, and the out-of-domain values, and says in the artifact that the
full listing was withheld. It never substitutes an empty list for the listing it declined
to print: a reader must be able to tell "this field holds nothing" from "this field holds
too much to show".
"""

ZERO_SHARE_REPORTING_FLOOR_TENTHS_PCT = 10
"""The share of recorded zeros, in tenths of a percent, worth a reviewer's attention.

One percent. ADR-0006 is the reason this is here at all: a numeric field whose most
common value is zero may be recording a measurement of zero or a parcel record carrying
no number, and ``YEARBUILT`` was the second for 12,148 records. The floor is a reporting
threshold and nothing more. Nothing is declared, excluded, or classified by it, and the
zero count itself is published for every numeric field whatever the share.
"""


@dataclass(frozen=True)
class ValueCount:
    """One distinct value as it arrived, and how many rows carried it."""

    value: str
    count: int

    def as_json(self) -> dict[str, object]:
        return {"value": self.value, "count": self.count}


@dataclass(frozen=True)
class MarkerCandidate:
    """A value that reads like a missing-data marker, and whether anyone reviewed it."""

    value: str
    normalized: str
    count: int

    def as_json(self) -> dict[str, object]:
        return {
            "value": self.value,
            "normalized": self.normalized,
            "count": self.count,
            # Every candidate in this list is by construction one the registry has not
            # declared for this field: `undeclared_marker` returns None for a reviewed
            # one. The key is written out anyway, and always with this value, so that a
            # reader of survey.json does not have to know that to read it, and so that a
            # future survey which does report reviewed markers has somewhere to put them.
            "basis": "unreviewed",
        }


@dataclass(frozen=True)
class ZeroReading:
    """How often a numeric field recorded a zero, and out of how many numbers.

    Split by whether the registry has already reviewed that zero. ``YEARBUILT`` declares
    the literal ``0`` as a marker, because 12,148 records carry a parcel with no year and
    no structure in a California wildfire was built in year 0. Reporting that field again
    as an open question every time somebody surveys a retrieval would train a reviewer to
    skip the section, which is how a review aid stops being read.
    """

    zeros: int
    """Rows whose value parses to zero, declared and undeclared together."""

    declared_zeros: int
    """Of those, the ones the registry already treats as a marker or absence here."""

    numbers: int

    @property
    def undeclared_zeros(self) -> int:
        return self.zeros - self.declared_zeros

    @property
    def tenths_pct(self) -> int | None:
        """Zeros as a share of parsable numbers, or ``None`` when there were none.

        A field in which nothing parsed as a number has no zero share. It is not zero
        percent, and publishing it as zero percent would say the field recorded numbers
        and none of them were zero.
        """
        return present_tenths_of_percent(self.zeros, self.numbers)

    @property
    def undeclared_tenths_pct(self) -> int | None:
        return present_tenths_of_percent(self.undeclared_zeros, self.numbers)

    @property
    def worth_reviewing(self) -> bool:
        """True when enough zeros nobody has ruled on sit in this field to ask about.

        Measured on the undeclared share, so a field whose zero has been reviewed is
        reported and not flagged, and a field with a mix is flagged for the part that
        is still a question.
        """
        share = self.undeclared_tenths_pct
        return share is not None and share >= ZERO_SHARE_REPORTING_FLOOR_TENTHS_PCT

    def as_json(self) -> dict[str, object]:
        return {
            "zeros": self.zeros,
            "declared_zeros": self.declared_zeros,
            "undeclared_zeros": self.undeclared_zeros,
            "numbers": self.numbers,
            "tenths_pct": self.tenths_pct,
            "undeclared_tenths_pct": self.undeclared_tenths_pct,
            "worth_reviewing": self.worth_reviewing,
        }


@dataclass(frozen=True)
class FieldSurvey:
    """What one measured column holds in this retrieval, and what needs a person."""

    name: str
    label: str
    rows: int
    empty: int
    """Rows where the column was absent, null, or blank after stripping."""

    distinct: int
    values: tuple[ValueCount, ...] | None
    """Every distinct value with its count, or ``None`` when above the listing bound."""

    candidates: tuple[MarkerCandidate, ...]
    outside_domain: tuple[ValueCount, ...] | None
    """Values not in the published domain, or ``None`` where no domain is published."""

    zeros: ZeroReading | None
    """Only for a field declared ``numeric``; ``None`` otherwise."""

    @property
    def needs_review(self) -> bool:
        """True when this field has anything a person should look at."""
        return bool(self.candidates) or (
            self.zeros is not None and self.zeros.worth_reviewing
        )

    def as_json(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "field": self.name,
            "label": self.label,
            "rows": self.rows,
            "empty": self.empty,
            "distinct": self.distinct,
            "values_listed": self.values is not None,
            "candidates": [candidate.as_json() for candidate in self.candidates],
            "outside_published_domain": (
                None
                if self.outside_domain is None
                else [item.as_json() for item in self.outside_domain]
            ),
            "needs_review": self.needs_review,
        }
        if self.values is None:
            # Not an empty list. The listing was withheld and the artifact says which of
            # the two happened, because a reader cannot tell them apart from `[]`.
            payload["values_withheld_because"] = (
                f"the field holds {self.distinct} distinct values, "
                f"more than the listing bound of {LISTING_BOUND}"
            )
        else:
            payload["values"] = [item.as_json() for item in self.values]
        payload["recorded_zeros"] = None if self.zeros is None else self.zeros.as_json()
        return payload


@dataclass(frozen=True)
class SourceSurvey:
    """One source file, surveyed."""

    source: str
    rows: int
    fields: tuple[FieldSurvey, ...]

    @property
    def needs_review(self) -> tuple[FieldSurvey, ...]:
        return tuple(field for field in self.fields if field.needs_review)

    def as_json(self) -> dict[str, object]:
        return {
            "source": self.source,
            "rows": self.rows,
            "fields_measured": len(self.fields),
            "fields_needing_review": len(self.needs_review),
            "fields": [field.as_json() for field in self.fields],
        }


def _cell_text(row: Mapping[str, object], name: str) -> str:
    """The cell as the build sees it: stripped, with absent and null both empty."""
    raw = row.get(name)
    if raw is None:
        return ""
    return str(raw).strip()


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _is_unknown(spec: FieldSpec, text: str) -> bool:
    """True when the build would classify this value as explicit-unknown, not present."""
    return text in spec.unknown_codes or normalize_marker(text) in spec.unknown_markers


def _is_declared(spec: FieldSpec, text: str) -> bool:
    """True when the registry has already reviewed this exact value for this field."""
    return _is_unknown(spec, text) or text in spec.recorded_absences


def survey_field(
    rows: Sequence[Mapping[str, object]],
    spec: FieldSpec,
    *,
    listing_bound: int = LISTING_BOUND,
) -> FieldSurvey:
    """Count what one column holds, without deciding anything about it."""
    counts: dict[str, int] = {}
    empty = 0
    for row in rows:
        text = _cell_text(row, spec.name)
        if text == "":
            empty += 1
            continue
        counts[text] = counts.get(text, 0) + 1

    ordered = tuple(
        ValueCount(value, counts[value]) for value in sorted(counts, key=_value_order)
    )
    candidates = tuple(
        MarkerCandidate(item.value, marker, item.count)
        for item in ordered
        if (marker := spec.undeclared_marker(item.value)) is not None
    )
    outside: tuple[ValueCount, ...] | None
    if spec.domain_values is None:
        # ADR-0010. A field with no published domain has no values outside one; it does
        # not have zero of them. `null` is the honest answer and `[]` is a false one.
        outside = None
    else:
        # The population is the one `FieldSpec.outside_domain` asks about: values the
        # build would classify as *present*. A declared unknown marker or code is
        # explicit-unknown rather than a present value outside the domain, and an
        # undeclared marker is reported above as a candidate rather than counted here,
        # because it would stop the build before any domain comparison happened.
        outside = tuple(
            item
            for item in ordered
            if item.value not in spec.domain_values
            and not _is_unknown(spec, item.value)
            and spec.undeclared_marker(item.value) is None
        )

    zeros: ZeroReading | None = None
    if spec.numeric:
        numeric_items = [item for item in ordered if _is_number(item.value)]
        zero_items = [item for item in numeric_items if float(item.value) == 0.0]
        zeros = ZeroReading(
            zeros=sum(item.count for item in zero_items),
            declared_zeros=sum(
                item.count for item in zero_items if _is_declared(spec, item.value)
            ),
            numbers=sum(item.count for item in numeric_items),
        )

    return FieldSurvey(
        name=spec.name,
        label=spec.label,
        rows=len(rows),
        empty=empty,
        distinct=len(ordered),
        values=ordered if len(ordered) <= listing_bound else None,
        candidates=candidates,
        outside_domain=outside,
        zeros=zeros,
    )


def _value_order(value: str) -> tuple[int, float, str]:
    """Numbers in numeric order, then everything else in code-point order.

    Sorting `"10"` before `"9"` in a listing a person reads to review a numeric field is
    a small thing that makes the listing harder to read than the file. Text values keep
    code-point order, which is stable across machines and locales; `sorted` is called on
    the same key everywhere so the output is byte-identical run to run.
    """
    if _is_number(value):
        return (0, float(value), value)
    return (1, 0.0, value)


def survey_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    specs: Sequence[FieldSpec],
    required: tuple[str, ...],
    source: str,
    listing_bound: int = LISTING_BOUND,
) -> SourceSurvey:
    """Survey every measured column of a source's rows.

    A missing column still refuses. The survey is a review aid for markers, not a way
    around :class:`~perimeter.schema.SchemaDriftError`: a column that vanished upstream
    would otherwise be surveyed as a column every row left blank, which is the reading
    this project exists to refuse. It checks every row, as the parser does, because a
    column that goes missing part way down a file is intact in the first row.
    """
    required_columns = (*required, *(spec.name for spec in specs))
    needed = frozenset(required_columns)
    for index, row in enumerate(rows):
        if not needed <= row.keys():
            require_columns(set(row), required_columns, source=f"{source} row {index}")
    return SourceSurvey(
        source=source,
        rows=len(rows),
        fields=tuple(
            survey_field(rows, spec, listing_bound=listing_bound) for spec in specs
        ),
    )


REGISTRY_BY_SOURCE: dict[str, tuple[tuple[FieldSpec, ...], tuple[str, ...]]] = {
    "perimeters": (FRAP_FIELDS, FRAP_REQUIRED_COLUMNS),
    "dins": (DINS_FIELDS, DINS_REQUIRED_COLUMNS),
}
"""The same two registries the build measures with, keyed by the flag that selects them.

Read from :mod:`perimeter.schema` rather than restated, so a field added to a registry is
surveyed without anyone remembering to add it here.
"""


def survey_file(
    path: Path, *, source: str, listing_bound: int = LISTING_BOUND
) -> SourceSurvey:
    """Read one acquired file and survey it."""
    try:
        specs, required = REGISTRY_BY_SOURCE[source]
    except KeyError:
        raise SchemaDriftError(
            f"no field registry for source {source!r}; this project measures "
            f"{sorted(REGISTRY_BY_SOURCE)}"
        ) from None
    return survey_rows(
        load_rows(path),
        specs=specs,
        required=required,
        source=source,
        listing_bound=listing_bound,
    )


def as_json(surveys: Sequence[SourceSurvey]) -> dict[str, object]:
    """The survey artifact: what was read, and what needs a person."""
    return {
        "listing_bound": LISTING_BOUND,
        "zero_share_reporting_floor_tenths_pct": ZERO_SHARE_REPORTING_FLOOR_TENTHS_PCT,
        # Said in the artifact and not only in this docstring, because the file outlives
        # the terminal it was printed in and its first reader may not be the person who
        # ran it.
        "declares_nothing": (
            "Every candidate below is unreviewed. This file records what a retrieval "
            "holds; it decides nothing, and no part of the build reads it."
        ),
        "sources": [survey.as_json() for survey in surveys],
    }


def markdown(surveys: Sequence[SourceSurvey]) -> str:
    """A draft review section per field with a candidate, in docs/MARKERS.md's shape.

    Every entry is a question, not an entry. The basis line reads ``unreviewed`` and the
    evidence line is the count this survey measured, so the person editing it is adding
    the judgment rather than confirming one the tool already made.
    """
    lines = [
        "# Survey draft: candidate markers awaiting review",
        "",
        "Generated by `python -m perimeter.survey`. Nothing here is declared. Each entry",
        "below is a value that reads like a missing-data marker in a field that has not",
        "reviewed it, or a numeric field whose recorded zeros are common enough to be",
        "worth a look. Editing an entry into `docs/MARKERS.md` and `src/perimeter/",
        "schema.py` is the reviewing step, and it is a person's.",
        "",
    ]
    for survey in surveys:
        lines.append(f"## {survey.source}")
        lines.append("")
        needing = survey.needs_review
        if not needing:
            lines.append(
                f"No candidates. Every value in all {len(survey.fields)} measured "
                f"fields of {survey.rows} rows is either a reviewed marker, a published "
                "recorded absence, or an ordinary value."
            )
            lines.append("")
            continue
        for field in needing:
            lines.append(f"### `{field.name}` ({field.label})")
            lines.append("")
            lines.append("- basis: unreviewed")
            lines.append(f"- rows: {field.rows}; empty: {field.empty}")
            for candidate in field.candidates:
                lines.append(
                    f"- candidate marker: `{candidate.value}` "
                    f"(normalizes to `{candidate.normalized}`), "
                    f"{candidate.count} rows. What does the publisher mean by it in "
                    "this field, and is it a marker or a finding?"
                )
            if field.zeros is not None and field.zeros.worth_reviewing:
                share = field.zeros.undeclared_tenths_pct
                assert share is not None  # noqa: S101 - worth_reviewing implies it
                lines.append(
                    f"- undeclared zeros: {field.zeros.undeclared_zeros} of "
                    f"{field.zeros.numbers} numbers ({share / 10:.1f}%). Is a zero here "
                    "a measurement of zero, or a record carrying no number?"
                )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def console(surveys: Sequence[SourceSurvey]) -> str:
    """What a person at a terminal reads: one line per field that needs review."""
    lines: list[str] = []
    for survey in surveys:
        needing = survey.needs_review
        lines.append(
            f"{survey.source}: {survey.rows} rows, {len(survey.fields)} fields "
            f"measured, {len(needing)} needing review"
        )
        for field in needing:
            for candidate in field.candidates:
                lines.append(
                    f"  {field.name}: candidate marker {candidate.value!r} "
                    f"x{candidate.count} (unreviewed)"
                )
            if field.zeros is not None and field.zeros.worth_reviewing:
                share = field.zeros.undeclared_tenths_pct
                assert share is not None  # noqa: S101 - worth_reviewing implies it
                lines.append(
                    f"  {field.name}: {field.zeros.undeclared_zeros} undeclared zeros "
                    f"of {field.zeros.numbers} numbers ({share / 10:.1f}%) (unreviewed)"
                )
        if not needing:
            lines.append("  no candidates")
    return "\n".join(lines)


def write(surveys: Sequence[SourceSurvey], out_dir: Path) -> list[Path]:
    """Write ``survey.json`` and ``survey.md`` into ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact = out_dir / "survey.json"
    artifact.write_text(
        json.dumps(as_json(surveys), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    draft = out_dir / "survey.md"
    draft.write_text(markdown(surveys), encoding="utf-8")
    return [artifact, draft]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="perimeter.survey",
        description=(
            "Inventory the candidate markers in an acquired file. Declares nothing, "
            "edits no registry, and is read by no part of the build."
        ),
    )
    parser.add_argument(
        "--perimeters", type=Path, help="attribute rows for the FRAP layer"
    )
    parser.add_argument("--dins", type=Path, help="attribute rows for the DINS layer")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("build/survey"),
        help="directory for survey.json and survey.md (default: build/survey)",
    )
    parser.add_argument(
        "--listing-bound",
        type=int,
        default=LISTING_BOUND,
        help=(
            "how many distinct values a field may hold before the full listing is "
            f"withheld (default: {LISTING_BOUND})"
        ),
    )
    args = parser.parse_args(argv)
    requested = [
        (name, path)
        for name, path in (("perimeters", args.perimeters), ("dins", args.dins))
        if path is not None
    ]
    if not requested:
        parser.error("give at least one of --perimeters or --dins")
    surveys = [
        survey_file(path, source=name, listing_bound=args.listing_bound)
        for name, path in requested
    ]
    print(console(surveys))
    for path in write(surveys, args.out):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
