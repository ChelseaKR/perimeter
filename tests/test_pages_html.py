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
from html.parser import HTMLParser
from pathlib import Path

import pytest

from perimeter.cells import present_tenths_of_percent
from perimeter.cli import build_site
from perimeter.render import DARK, LIGHT
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
