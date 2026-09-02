"""What can be checked about the pages without a browser, checked.

Three things are gated here, all of them without a renderer:

* **Structure.** The pages are parsed and the document facts a screen reader depends on
  are asserted: one ``h1``, no skipped heading level, every table header scoped, every
  table named, no repeated id, one main landmark, a language on the root element.
  ``html-validate`` and ``axe-core`` cover the same ground more thoroughly in
  ``make pages``; these run inside ``make verify`` so the floor holds with no toolchain
  beyond Python.
* **Contrast.** WCAG 2.2 contrast is arithmetic over two palettes, and both palettes are
  data in :mod:`perimeter.render`. Every pair the pages actually put together is
  measured here, in both themes. This is the one WCAG criterion a headless check can
  settle completely, and axe cannot: jsdom paints nothing.
* **Numbers.** Every number a page prints in a table or a tile must be a number the
  pipeline computed, and every number in prose must either be one of those, appear in a
  quote from the publisher, or be on a reviewed list with a reason. A page that can
  print a figure nothing counted is the failure this project exists to avoid.

What is deliberately not claimed: none of this sees the pages. Layout, reflow at small
widths, focus visibility in practice, and print rendering need a person. README.md names
them.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import replace
from html.parser import HTMLParser
from pathlib import Path

import pytest

from perimeter.cells import present_tenths_of_percent
from perimeter.cli import build_site
from perimeter.coverage import dins_report
from perimeter.dins import load_inspections
from perimeter.render import (
    DARK,
    DOMAIN_NOTE,
    INCIDENT_FIELD_COLUMNS,
    LIGHT,
    NOT_COUNTED,
    SITE_URL,
    dins_page,
)
from perimeter.schema import DINS_FIELDS, FRAP_FIELDS, FieldSpec
from perimeter.sources import SOURCES

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
PAGES = ("index.html", "perimeters.html", "dins.html")
HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("pages")
    build_site(
        perimeters_source=FIXTURES / "frap_perimeters.sample.json",
        dins_source=FIXTURES / "dins_postfire.sample.json",
        out_dir=out,
        is_fixture=True,
    )
    return out


# --------------------------------------------------------------------------------------
# A parser that records the document facts these checks are about
# --------------------------------------------------------------------------------------


class Document(HTMLParser):
    """Structural facts, gathered in one pass over the markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.headings: list[tuple[str, str]] = []
        self.ids: list[str] = []
        self.landmarks: Counter[str] = Counter()
        self.tables: list[dict[str, object]] = []
        self.th_scopes: list[str | None] = []
        self.hrefs: list[str] = []
        self.lang: str | None = None
        self.title: str = ""
        self.metas: dict[str, str] = {}
        # Open Graph uses `property=`, not `name=`, so the meta collector above cannot see
        # it, and `<link rel="canonical">` is not a meta tag at all. Both are head facts a
        # structural check should be able to reach.
        self.properties: dict[str, str] = {}
        self.links: dict[str, str] = {}
        self.prose: list[str] = []
        self.cells: list[str] = []
        self._heading: str | None = None
        self._text: list[str] = []

    PROSE_TAGS = frozenset({"p", "blockquote", "caption", *HEADINGS})
    CELL_TAGS = frozenset({"td"})
    TILE = "tile-value"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: (value or "") for key, value in attrs}
        self.stack.append(tag)
        if "id" in attr:
            self.ids.append(attr["id"])
        if tag in HEADINGS:
            self._heading = tag
            self._text = []
        elif tag in ("nav", "main", "footer", "header"):
            self.landmarks[tag] += 1
        self._note_head(tag, attr)
        self._note_table(tag, attr)
        if tag == "a" and "href" in attr:
            self.hrefs.append(attr["href"])

    def _note_head(self, tag: str, attr: dict[str, str]) -> None:
        if tag == "html":
            self.lang = attr.get("lang")
        elif tag == "meta":
            key = attr.get("name") or ("charset" if "charset" in attr else "")
            if key:
                self.metas[key] = attr.get("content", attr.get("charset", ""))
            if "property" in attr:
                self.properties[attr["property"]] = attr.get("content", "")
        elif tag == "link" and "rel" in attr:
            self.links[attr["rel"]] = attr.get("href", "")

    def _note_table(self, tag: str, attr: dict[str, str]) -> None:
        if tag == "table":
            self.tables.append({"caption": False, "th": 0, "scoped": 0})
        elif tag == "th" and self.tables:
            table = self.tables[-1]
            table["th"] = int(table["th"]) + 1
            scope = attr.get("scope")
            self.th_scopes.append(scope)
            if scope in ("row", "col", "rowgroup", "colgroup"):
                table["scoped"] = int(table["scoped"]) + 1
        elif tag == "caption" and self.tables:
            self.tables[-1]["caption"] = True

    def handle_endtag(self, tag: str) -> None:
        if tag in HEADINGS and self._heading == tag:
            self.headings.append((tag, "".join(self._text).strip()))
            self._heading = None
        while self.stack:
            if self.stack.pop() == tag:
                break

    def handle_data(self, data: str) -> None:
        if self._heading is not None:
            self._text.append(data)
        if "style" in self.stack or "title" in self.stack:
            if "title" in self.stack:
                self.title += data
            return
        if self.stack and self.stack[-1] in self.CELL_TAGS:
            self.cells.append(data)
        if any(tag in self.PROSE_TAGS for tag in self.stack):
            self.prose.append(data)


def parse(path: Path) -> Document:
    doc = Document()
    doc.feed(path.read_text(encoding="utf-8"))
    return doc


# --------------------------------------------------------------------------------------
# Structure
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", PAGES)
def test_the_page_declares_a_language(built: Path, name: str) -> None:
    assert parse(built / name).lang == "en"


@pytest.mark.parametrize("name", PAGES)
def test_the_page_declares_a_character_set_and_a_viewport(
    built: Path, name: str
) -> None:
    metas = parse(built / name).metas
    assert metas.get("charset") == "utf-8"
    assert "width=device-width" in metas.get("viewport", "")


@pytest.mark.parametrize("name", PAGES)
def test_the_page_has_a_title_and_a_description(built: Path, name: str) -> None:
    doc = parse(built / name)
    assert doc.title.strip()
    assert doc.metas.get("description", "").strip()


def test_each_page_describes_itself_rather_than_the_other_two(built: Path) -> None:
    """One description shared by three pages describes none of them.

    All three pages carried the same sentence, so a search result for the DINS page and a
    search result for the perimeters page were indistinguishable, and neither said what
    its own page counts. The renderer now takes the description per page.

    The descriptions state no count on purpose. The committed ``site/`` is built from
    ``data/raw/`` and this test builds from the fixtures, so a figure hardcoded in
    ``render.py`` would be true of one build and false of the other, and CONTRIBUTING's
    rule is that a number is counted or it is not published. The counts also belong to
    CAL FIRE's files, which change underneath us.
    """
    descriptions = {
        name: parse(built / name).metas.get("description", "").strip() for name in PAGES
    }
    assert all(descriptions.values()), descriptions
    assert len(set(descriptions.values())) == len(PAGES), descriptions


@pytest.mark.parametrize("name", PAGES)
def test_the_page_names_itself_and_not_the_shared_origin(
    built: Path, name: str
) -> None:
    """The canonical carries this project's path segment, not the bare origin.

    These pages are one of six project sites on ``chelseakr.github.io``, served from
    PATHS rather than from domains of their own. That makes the single-domain habit
    actively wrong here rather than merely untidy: a canonical of "/" resolves to
    ``https://chelseakr.github.io/``, which is not this site's root but a different
    address that 404s, and all six sites would claim the identical canonical. A crawler
    that believes them folds six unrelated projects into one document.

    So this asserts the path segment is PRESENT, not merely that a canonical exists: an
    empty or origin-rooted canonical satisfies "is there a canonical" and is the bug.
    """
    doc = parse(built / name)

    canonical = doc.links.get("canonical", "")
    assert canonical, f"{name} has no canonical URL"
    assert canonical.startswith(SITE_URL), f"{name} canonicalises to {canonical!r}"
    assert canonical.rstrip("/") != "https://chelseakr.github.io", (
        f"{name} points at the shared origin, which is a different site"
    )
    assert "/perimeter/" in canonical, f"{name}: {canonical!r} omits the project path"

    # The social card repeats the page rather than describing it a second time, so the two
    # cannot drift into disagreeing about what this page is.
    assert doc.properties.get("og:url") == canonical, f"{name} og:url disagrees"
    assert doc.properties.get("og:title") == doc.title.strip(), (
        f"{name} og:title disagrees"
    )
    assert doc.properties.get("og:description") == doc.metas.get("description"), name
    assert doc.properties.get("og:type") == "website", name

    # No image is published in this repository, so the card must not promise one. If a
    # social image is ever committed, this fails until og:image is added with it.
    card = doc.metas.get("twitter:card")
    assert card in ("summary", "summary_large_image"), (
        f"{name} twitter:card is {card!r}"
    )
    if card == "summary_large_image":
        assert doc.properties.get("og:image"), (
            f"{name} promises an image it has none of"
        )


def test_the_three_pages_do_not_share_one_canonical(built: Path) -> None:
    """Three pages, three canonicals. A shared one asks a crawler to drop two of them."""
    canonicals = {
        name: parse(built / name).links.get("canonical", "") for name in PAGES
    }
    assert len(set(canonicals.values())) == len(PAGES), canonicals


@pytest.mark.parametrize("name", PAGES)
def test_there_is_exactly_one_first_level_heading(built: Path, name: str) -> None:
    levels = [tag for tag, _ in parse(built / name).headings]
    assert levels.count("h1") == 1, levels


@pytest.mark.parametrize("name", PAGES)
def test_no_heading_level_is_skipped(built: Path, name: str) -> None:
    """A jump from h1 to h3 tells a screen-reader user a section is missing."""
    previous = 0
    for tag, text in parse(built / name).headings:
        level = int(tag[1])
        assert level <= previous + 1, f"{name}: {tag} {text!r} follows h{previous}"
        previous = level


@pytest.mark.parametrize("name", PAGES)
def test_every_heading_has_text(built: Path, name: str) -> None:
    for tag, text in parse(built / name).headings:
        assert text, f"{name}: empty {tag}"


@pytest.mark.parametrize("name", PAGES)
def test_no_id_is_used_twice(built: Path, name: str) -> None:
    ids = parse(built / name).ids
    repeated = [value for value, count in Counter(ids).items() if count > 1]
    assert not repeated, f"{name}: {repeated}"


@pytest.mark.parametrize("name", PAGES)
def test_the_page_has_the_landmarks_a_reader_navigates_by(
    built: Path, name: str
) -> None:
    landmarks = parse(built / name).landmarks
    assert landmarks["main"] == 1, "exactly one main landmark"
    assert landmarks["nav"] == 1
    assert landmarks["footer"] >= 1


@pytest.mark.parametrize("name", PAGES)
def test_the_skip_link_points_at_something_on_the_page(built: Path, name: str) -> None:
    doc = parse(built / name)
    internal = [href[1:] for href in doc.hrefs if href.startswith("#")]
    assert internal, f"{name}: no skip link"
    for target in internal:
        assert target in doc.ids, f"{name}: #{target} has no target"


@pytest.mark.parametrize("name", PAGES)
def test_every_table_header_is_scoped(built: Path, name: str) -> None:
    """Without scope, a cell read on its own does not carry what it is about."""
    doc = parse(built / name)
    assert doc.tables, f"{name}: no tables to check"
    for index, table in enumerate(doc.tables):
        assert table["th"], f"{name}: table {index} has no header cells"
        assert table["scoped"] == table["th"], f"{name}: table {index} has bare <th>"
    assert all(scope in ("row", "col") for scope in doc.th_scopes)


@pytest.mark.parametrize("name", PAGES)
def test_every_table_is_named(built: Path, name: str) -> None:
    """A caption is how a table announces what it is before it is read out."""
    for index, table in enumerate(parse(built / name).tables):
        assert table["caption"], f"{name}: table {index} has no caption"


@pytest.mark.parametrize("name", PAGES)
def test_every_row_is_headed_by_the_thing_the_row_is_about(
    built: Path, name: str
) -> None:
    """Column headers alone leave a cell unidentified in one of its two directions."""
    scopes = Counter(parse(built / name).th_scopes)
    assert scopes["row"] > 0
    assert scopes["col"] > 0


@pytest.mark.parametrize("name", PAGES)
def test_the_page_says_it_is_not_affiliated_with_cal_fire(
    built: Path, name: str
) -> None:
    text = (built / name).read_text(encoding="utf-8")
    assert "Not affiliated with or endorsed by CAL FIRE" in text


@pytest.mark.parametrize("name", PAGES)
def test_the_page_carries_no_em_dashes(built: Path, name: str) -> None:
    assert "—" not in (built / name).read_text(encoding="utf-8")


# --------------------------------------------------------------------------------------
# Contrast. WCAG 2.2: 1.4.3 for text, 1.4.11 for the graphics that carry information.
# --------------------------------------------------------------------------------------


def relative_luminance(colour: str) -> float:
    """WCAG relative luminance of an sRGB hex colour."""
    raw = colour.lstrip("#")
    channels = [int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    red, green, blue = linear
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(first: str, second: str) -> float:
    """WCAG contrast ratio, always at least 1.0 whichever way round the pair is given."""
    lighter, darker = sorted(
        (relative_luminance(first), relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


TEXT_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("ink", "surface", "body copy on the page background"),
    ("ink", "surface-raised", "body copy inside a table, tile or card"),
    ("ink-2", "surface", "standfirst and .measured notes"),
    ("ink-2", "surface-raised", "tile labels and card copy"),
    ("ink-2", "quote-bg", "the publisher's quoted sentences"),
    ("ink-3", "surface", "eyebrow, footer and the badge"),
    ("ink-3", "surface-raised", "column headers, marker notes and field names"),
    ("accent", "surface", "links in body copy and navigation"),
    ("accent", "surface-raised", "links inside a card"),
)
"""Every foreground and background the stylesheet actually puts together, with the rule
that creates the pair. All of this text is under 24px and none of it is bold at 19px or
more, so 4.5:1 is the applicable threshold for all of it."""

GRAPHIC_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("present", "surface-raised", "the recorded-value bar segment and its swatch"),
    ("unknown", "surface-raised", "the recorded-as-unknown segment and its swatch"),
    ("absent", "surface-raised", "the empty-cell segment and its swatch"),
    ("present", "surface", "the same swatch in the legend above a table"),
    ("unknown", "surface", "the same swatch in the legend above a table"),
    ("absent", "surface", "the same swatch in the legend above a table"),
)
"""The three state colours against both surfaces. Every bar sits in a row beside the
three counts it draws and the legend names each colour in words, so no information
depends on telling them apart. They are held to 1.4.11's 3:1 anyway."""

TEXT_MINIMUM = 4.5
GRAPHIC_MINIMUM = 3.0
PALETTES = {"light": LIGHT, "dark": DARK}


@pytest.mark.parametrize("theme", sorted(PALETTES))
@pytest.mark.parametrize("pair", TEXT_PAIRS, ids=lambda p: f"{p[0]}-on-{p[1]}")
def test_text_meets_wcag_contrast(theme: str, pair: tuple[str, str, str]) -> None:
    foreground, background, where = pair
    palette = PALETTES[theme]
    ratio = contrast(palette[foreground], palette[background])
    assert ratio >= TEXT_MINIMUM, (
        f"{theme}: {where} is {ratio:.2f}:1, below {TEXT_MINIMUM}:1"
    )


@pytest.mark.parametrize("theme", sorted(PALETTES))
@pytest.mark.parametrize("pair", GRAPHIC_PAIRS, ids=lambda p: f"{p[0]}-on-{p[1]}")
def test_graphics_meet_wcag_non_text_contrast(
    theme: str, pair: tuple[str, str, str]
) -> None:
    foreground, background, where = pair
    palette = PALETTES[theme]
    ratio = contrast(palette[foreground], palette[background])
    assert ratio >= GRAPHIC_MINIMUM, (
        f"{theme}: {where} is {ratio:.2f}:1, below {GRAPHIC_MINIMUM}:1"
    )


def test_both_palettes_define_exactly_the_same_tokens() -> None:
    """A token defined in one theme only would leave a colour inherited from the host."""
    assert set(LIGHT) == set(DARK)


def test_a_known_contrast_is_computed_correctly() -> None:
    """Anchor the arithmetic: black on white is 21:1, and a colour on itself is 1:1."""
    assert round(contrast("#000000", "#ffffff"), 2) == 21.0
    assert round(contrast("#1c5cab", "#1c5cab"), 2) == 1.0


# --------------------------------------------------------------------------------------
# Numbers: counted, never asserted
# --------------------------------------------------------------------------------------

NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?%?")

REVIEWED_PROSE_NUMBERS: dict[str, str] = {
    "2020": (
        "The incident start year that separates the two spellings of Not Applicable in "
        "UTILITYMISCSTRUCTUREDISTANCE. Established in docs/MARKERS.md and reproducible "
        "from the acquired file: no incident uses both spellings, and the split falls "
        "on this year."
    ),
}
"""Numbers a page states in prose that are neither computed by this build nor quoted.

Every entry needs a reason a reader can check. The list is meant to stay near empty:
anything that can be counted should be counted and rendered from the count instead.
"""


def numbers_in(text: str) -> set[str]:
    return set(NUMBER.findall(text))


def _shapes_of(value: int) -> set[str]:
    """One integer as a page may print it: bare, grouped, or as tenths of a percent."""
    return {str(value), f"{value:,}", f"{value // 10}.{value % 10}%"}


def _triple_share(node: list[object]) -> set[str]:
    """The share of a compact per-incident field triple, or nothing.

    ``field_state_order`` in the artifact documents the triple as present,
    explicit-unknown, not-recorded, so this is the project's own published share function
    applied to published counts, not a number invented for the test.
    """
    if len(node) != 3 or not all(
        isinstance(item, int) and not isinstance(item, bool) for item in node
    ):
        return set()
    counts = [int(item) for item in node]  # type: ignore[arg-type]
    tenths = present_tenths_of_percent(counts[0], sum(counts))
    return set() if tenths is None else {f"{tenths // 10}.{tenths % 10}%"}


def _walk(node: object, found: set[str]) -> None:
    if isinstance(node, bool):
        return
    if isinstance(node, int):
        found |= _shapes_of(node)
    elif isinstance(node, dict):
        found |= {str(key) for key in node}
        for value in node.values():
            _walk(value, found)
    elif isinstance(node, list):
        found |= _triple_share(node)
        for value in node:
            _walk(value, found)
    elif isinstance(node, str):
        found |= numbers_in(node)


def computed_numbers(payload: object) -> set[str]:
    """Every integer the pipeline produced, in the shapes a page may print it.

    Two derivations are allowed on top of the literal values and only two: a share
    published in tenths of a percent, and the share of the compact per-incident triple.
    Anything else a page prints has to be in the artifact outright.
    """
    found: set[str] = set()
    _walk(payload, found)
    return found


@pytest.fixture(scope="module")
def allowed(built: Path) -> set[str]:
    """Numbers the build computed, plus numbers the publishers wrote."""
    values: set[str] = set()
    for artifact in sorted((built / "data").glob("*.json")):
        values |= computed_numbers(json.loads(artifact.read_text(encoding="utf-8")))
    for source in SOURCES:
        for caveat in source.caveats:
            values |= numbers_in(caveat.quote)
    return values | set(REVIEWED_PROSE_NUMBERS)


@pytest.mark.parametrize("name", PAGES)
def test_every_number_in_a_table_cell_was_computed_by_the_build(
    built: Path, name: str, allowed: set[str]
) -> None:
    for chunk in parse(built / name).cells:
        for token in numbers_in(chunk):
            assert token in allowed, f"{name}: table cell prints uncounted {token!r}"


@pytest.mark.parametrize("name", PAGES)
def test_every_number_in_prose_is_counted_quoted_or_reviewed(
    built: Path, name: str, allowed: set[str]
) -> None:
    for chunk in parse(built / name).prose:
        for token in numbers_in(chunk):
            assert token in allowed, (
                f"{name}: prose states {token!r}, which the build did not compute, no "
                "publisher quote contains, and REVIEWED_PROSE_NUMBERS does not justify"
            )


@pytest.mark.parametrize("name", ("perimeters.html", "dins.html"))
def test_a_measurement_page_states_when_its_source_was_retrieved(
    built: Path, name: str
) -> None:
    """No figure without its date. A fixture build says so instead of naming one."""
    text = (built / name).read_text(encoding="utf-8")
    assert "Retrieved" in text
    assert "not applicable to a fixture build" in text


def test_a_real_build_prints_the_reviewed_retrieval_date(tmp_path: Path) -> None:
    build_site(
        perimeters_source=FIXTURES / "frap_perimeters.sample.json",
        dins_source=FIXTURES / "dins_postfire.sample.json",
        out_dir=tmp_path,
        is_fixture=False,
    )
    for name in ("perimeters.html", "dins.html"):
        assert SOURCES[0].retrieved in (tmp_path / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", PAGES)
def test_no_share_is_printed_without_the_counts_it_came_from(
    built: Path, name: str
) -> None:
    """Every percentage on a page sits in a row that also prints its numerator."""
    doc = parse(built / name)
    shares = [chunk for chunk in doc.cells if "%" in chunk]
    if not shares:
        return
    counts = [chunk for chunk in doc.cells if NUMBER.fullmatch(chunk.strip() or "x")]
    assert len(counts) >= len(shares), name


# --------------------------------------------------------------------------------------
# The published domain: counted, absent, or nothing to count against
# --------------------------------------------------------------------------------------

NO_DOMAIN_NOTE = (
    "The layer publishes no coded-value domain for this field, so no value here is "
    "counted as outside one"
)


@pytest.mark.parametrize(
    ("name", "specs"),
    (("perimeters.html", FRAP_FIELDS), ("dins.html", DINS_FIELDS)),
)
def test_a_field_with_no_published_domain_says_so_rather_than_counting_zero(
    built: Path, name: str, specs: tuple[FieldSpec, ...]
) -> None:
    """A free-text field has no domain, and the row says that instead of staying silent.

    Silence on such a row reads exactly like silence on a field whose domain is published
    and holds every value it carries. Those are different facts, and the artifact beside
    this page publishes null for one and zero for the other.
    """
    expected = sum(1 for spec in specs if spec.domain_values is None)
    assert expected, f"{name} must carry at least one free-text field"
    text = (built / name).read_text(encoding="utf-8")
    assert text.count(NO_DOMAIN_NOTE) == expected


@pytest.mark.parametrize("name", ("perimeters.html", "dins.html"))
def test_the_field_table_says_what_a_row_with_no_domain_note_means(
    built: Path, name: str
) -> None:
    assert DOMAIN_NOTE in (built / name).read_text(encoding="utf-8")


def test_the_overview_carries_no_field_table_and_so_no_domain_note(built: Path) -> None:
    """The other direction, so the two tests above are not passing over every page."""
    text = (built / "index.html").read_text(encoding="utf-8")
    assert NO_DOMAIN_NOTE not in text
    assert DOMAIN_NOTE not in text


# --------------------------------------------------------------------------------------
# Table geometry: a row may not be narrower than the header it is read under
# --------------------------------------------------------------------------------------


class Rows(HTMLParser):
    """Cells per row, per table, counting ``colspan``.

    A row with fewer cells than its header does not render a gap. Every cell after the
    missing one moves left, under the previous column's heading, so a correctly counted
    number is published as a measurement of a different field. Nothing else here sees
    that: ``html-validate`` does not compare row widths and neither does axe, and the page
    looks entirely ordinary.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[int]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self.tables[-1].append(0)
        elif tag in ("td", "th") and self.tables and self.tables[-1]:
            span = dict(attrs).get("colspan") or "1"
            self.tables[-1][-1] += int(span) if span.isdigit() else 1


def row_width_problems(markup: str) -> list[str]:
    """Every table row whose width is not its table's header width.

    Raises nothing and returns a list, so the check can be run against markup that should
    fail it. A table with no rows is reported rather than skipped: a geometry check that
    found nothing to measure has not passed.
    """
    parser = Rows()
    parser.feed(markup)
    found: list[str] = []
    if not parser.tables:
        return [
            "no table found; a row-width check with nothing to measure has not passed"
        ]
    for index, widths in enumerate(parser.tables):
        rows = [width for width in widths if width]
        if not rows:
            found.append(f"table {index} has no cells in any row")
            continue
        header = rows[0]
        found.extend(
            f"table {index}: row {position} is {width} cells wide, the header is {header}"
            for position, width in enumerate(rows)
            if width != header
        )
    return found


@pytest.mark.parametrize("name", PAGES)
def test_no_table_row_is_narrower_than_its_header(built: Path, name: str) -> None:
    assert row_width_problems((built / name).read_text(encoding="utf-8")) == []


class TestTheRowWidthGateCanFail:
    """ADR 0004: run the check against markup that must not pass it."""

    def test_a_row_missing_a_cell_is_caught(self) -> None:
        markup = (
            "<table><tr><th>a</th><th>b</th><th>c</th></tr>"
            "<tr><td>1</td><td>2</td></tr></table>"
        )
        assert row_width_problems(markup) == [
            "table 0: row 1 is 2 cells wide, the header is 3"
        ]

    def test_a_well_formed_table_is_not_reported(self) -> None:
        markup = (
            "<table><tr><th>a</th><th>b</th></tr><tr><td>1</td><td>2</td></tr></table>"
        )
        assert row_width_problems(markup) == []

    def test_markup_with_no_table_is_a_failure_not_a_pass(self) -> None:
        assert row_width_problems("<p>nothing here</p>") != []

    def test_a_colspan_is_counted_as_the_columns_it_covers(self) -> None:
        markup = (
            "<table><tr><th>a</th><th>b</th></tr>"
            '<tr><td colspan="2">both</td></tr></table>'
        )
        assert row_width_problems(markup) == []


def test_the_per_incident_table_writes_a_cell_for_a_field_it_cannot_count() -> None:
    """A column the report does not carry per incident is written, not dropped.

    Reachable only if a field leaves ``DINS_FIELDS`` while the column list still names
    it. That is one edit, and the failure it produces is silent: five headers over four
    cells publishes the vent-screen share under Eaves.
    """
    report = dins_report(load_inspections(FIXTURES / "dins_postfire.sample.json"))
    dropped = INCIDENT_FIELD_COLUMNS[2][0]
    thinned = replace(
        report,
        incident_rows=[
            replace(
                incident,
                fields=[f for f in incident.fields if f.name != dropped],
            )
            for incident in report.incident_rows
        ],
    )
    markup = dins_page(thinned, is_fixture=True)
    assert row_width_problems(markup) == []
    assert markup.count(NOT_COUNTED) == len(thinned.incident_rows)
