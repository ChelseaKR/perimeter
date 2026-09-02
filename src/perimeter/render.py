"""Render the two measurements as static pages.

Two rules govern everything in this module.

The first is about numbers: a page may only print a count that was counted. Where a share
has no denominator, the page says so in words rather than printing a zero or leaving a
blank cell that a reader will fill in with a zero. The three states are always shown
together, so absence is on the page beside presence rather than implied by its lack.

The second is about tone. CAL FIRE and FRAP publish these limitations themselves, in the
dataset descriptions quoted on each page. This is not a review of an agency's work and it
must never read as one. Every section states what was counted and points at the sentence
in CAL FIRE's own documentation that made the count worth doing.
"""

from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from perimeter.cells import present_tenths_of_percent
from perimeter.coverage import DinsReport, FieldCoverage, PerimeterReport
from perimeter.schema import Basis
from perimeter.sources import DINS, FRAP, Source

# Where these pages are served. The path segment is load-bearing: this is one of six project
# sites on the shared `chelseakr.github.io` origin, published on PATHS rather than on domains
# of their own. `https://chelseakr.github.io/` is not a shorter spelling of this site's root;
# it is a different address, it 404s, and all six sites would claim it. A canonical naming it
# would invite a crawler to fold six unrelated projects into one document.
SITE_URL = "https://chelseakr.github.io/perimeter/"

# Keyed by `active`, the value each page already uses to mark its own nav entry, so a
# canonical and the highlighted tab cannot disagree about which page this is. The index
# canonicalises to the directory form, which is the URL Pages serves it at.
CANONICAL_PATH = {"index": "", "perimeters": "perimeters.html", "dins": "dins.html"}

DISCLAIMER = (
    "Unofficial. Not affiliated with or endorsed by CAL FIRE, FRAP, or any California "
    "state agency."
)

BASIS_NOTE: dict[Basis, str] = {
    Basis.PUBLISHED: (
        "published. Every value this field declares is a code in the layer's own "
        "coded-value domain, or a value the publisher's documentation states"
    ),
    Basis.INFERRED: (
        "inferred. At least one value this field declares is documented nowhere, and "
        "was read off the acquired file by this project. See docs/MARKERS.md"
    ),
}
"""What to print beside a field whose markers rest on one basis or the other.

The whole point of these pages is that the judgment calls are inspectable, and a reader
cannot tell a documented code from an inference by looking at the value. So the page says
which it is, per field, rather than leaving the distinction in the source.
"""

DOMAIN_NOTE = (
    '<p class="measured">There are three things a field can say about a published '
    "coded-value domain, and every row above says exactly one of them. It carries values "
    "the domain does not describe, which are counted and named under the field. It has a "
    "published domain and holds nothing outside it, and carries no note. Or the layer "
    "publishes no domain for that field at all, which the row says in words, because "
    "nothing there was compared against anything and a zero would have read as a finding "
    "that the file and the domain agree.</p>"
)
"""Printed under every three-state field table. What a row's silence means.

Thirty of the fifty-four measured fields are free text with no published domain. Until
this note existed they were reported as zero values outside the domain, which is a
measurement nobody took: there is no domain for a value to be outside of, and the counter
that produced the zero had nothing to count.
"""

STATE_LABELS: tuple[tuple[str, str, str], ...] = (
    (
        "present",
        "Recorded value",
        "A value the agency wrote down, including a recorded zero and including findings "
        "of absence such as No Damage or No Eaves.",
    ),
    (
        "explicit_unknown",
        "Recorded as unknown",
        "A published code or marker meaning the value could not be determined. Somebody "
        "recorded that determination failed.",
    ),
    (
        "not_recorded",
        "Empty cell",
        "Nothing was written in the cell. For DINS, CAL FIRE states that attributes with "
        "null values could not be determined.",
    ),
)

LIGHT: dict[str, str] = {
    "surface": "#fcfcfb",
    "surface-raised": "#ffffff",
    "rule": "#e2e0d9",
    "rule-strong": "#c9c6bc",
    "ink": "#14140f",
    "ink-2": "#52514e",
    "ink-3": "#6f6d66",
    "accent": "#1c5cab",
    "present": "#2a78d6",
    "unknown": "#eb6834",
    "absent": "#189a6b",
    "quote-bg": "#f5f4f0",
}
"""The light palette, as data so a test can measure it.

Contrast is a property of these twelve values, and every pair the pages actually put
together is checked against the WCAG 2.2 thresholds in ``tests/test_pages_html.py``.
Keeping the palette here rather than inside a CSS string is what makes that check
possible without a browser.
"""

DARK: dict[str, str] = {
    "surface": "#1a1a19",
    "surface-raised": "#232321",
    "rule": "#383835",
    "rule-strong": "#4f4e4a",
    "ink": "#f7f6f2",
    "ink-2": "#c3c2b7",
    "ink-3": "#9d9b92",
    "accent": "#86b6ef",
    "present": "#3987e5",
    "unknown": "#d95926",
    "absent": "#199e70",
    "quote-bg": "#232321",
}
"""The dark palette. Same token names, so no rule anywhere needs to know the theme."""


def tokens(palette: Mapping[str, str], *, indent: str = "  ") -> str:
    """One palette as custom-property declarations, in a fixed order."""
    return "".join(f"{indent}--{name}: {value};\n" for name, value in palette.items())


STYLESHEET = (
    f"""\
:root {{
  color-scheme: light;
{tokens(LIGHT)}}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    color-scheme: dark;
{tokens(DARK, indent="    ")}  }}
}}
:root[data-theme="dark"] {{
  color-scheme: dark;
{tokens(DARK)}}}
"""
    + """
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--surface);
  color: var(--ink);
  font: 400 17px/1.62 ui-serif, "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
}
.wrap { max-width: 62rem; margin: 0 auto; padding: 0 1.5rem 5rem; }
a { color: var(--accent); }
.visually-hidden {
  position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0;
  overflow: hidden; clip: rect(0 0 0 0); clip-path: inset(50%); white-space: nowrap;
}
.skip-link {
  position: absolute; left: -9999px; top: 0; z-index: 10;
  background: var(--surface-raised); color: var(--accent);
  padding: .6rem 1rem; border: 1px solid var(--rule-strong);
}
.skip-link:focus { left: .5rem; top: .5rem; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
h1, h2, h3, .tile-value, .num, thead th, .eyebrow, .legend, .badge, nav {
  font-family: ui-sans-serif, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
h1 { font-size: clamp(1.9rem, 1.3rem + 2.4vw, 2.9rem); line-height: 1.14; letter-spacing: -0.02em; margin: 0 0 .6rem; }
h2 { font-size: 1.4rem; letter-spacing: -0.01em; margin: 3.4rem 0 .4rem; padding-top: 1.6rem; border-top: 1px solid var(--rule); }
h3 { font-size: 1.02rem; letter-spacing: .01em; margin: 2rem 0 .5rem; color: var(--ink-2); }
p { margin: 0 0 1rem; max-width: 46rem; }
.eyebrow { font-size: .74rem; letter-spacing: .13em; text-transform: uppercase; color: var(--ink-3); margin: 0 0 .8rem; }
.standfirst { font-size: 1.16rem; color: var(--ink-2); max-width: 44rem; }
.lede { max-width: 44rem; }

nav { border-bottom: 1px solid var(--rule); margin-bottom: 2.6rem; }
nav .wrap { display: flex; flex-wrap: wrap; gap: 1.4rem; align-items: baseline; padding-top: 1rem; padding-bottom: 1rem; }
nav a { font-size: .88rem; text-decoration: none; }
nav a:hover { text-decoration: underline; }
nav .mark { font-weight: 700; letter-spacing: .04em; text-transform: uppercase; font-size: .8rem; color: var(--ink); }

header.page { padding: 2.2rem 0 0; }
.badge {
  display: inline-block; font-size: .72rem; letter-spacing: .07em; text-transform: uppercase;
  border: 1px solid var(--rule-strong); color: var(--ink-3);
  border-radius: 999px; padding: .22rem .7rem; margin-bottom: 1.4rem;
}

.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr)); gap: 1px; background: var(--rule); border: 1px solid var(--rule); margin: 2.2rem 0 1rem; padding: 0; list-style: none; }
.tile { background: var(--surface-raised); padding: 1.1rem 1.2rem 1.2rem; }
.tile-value { font-size: 1.72rem; font-weight: 600; letter-spacing: -0.02em; line-height: 1.1; }
.tile-label { font-size: .82rem; color: var(--ink-2); margin-top: .35rem; line-height: 1.4; }

.scroll { overflow-x: auto; border: 1px solid var(--rule); margin: 1.2rem 0; background: var(--surface-raised); }
.scroll.tall { max-height: 30rem; overflow-y: auto; }
table { border-collapse: collapse; width: 100%; font-size: .87rem; }
thead th {
  position: sticky; top: 0; background: var(--surface-raised);
  text-align: left; font-size: .72rem; letter-spacing: .06em; text-transform: uppercase;
  color: var(--ink-3); font-weight: 600; padding: .7rem .8rem; border-bottom: 1px solid var(--rule-strong);
  white-space: nowrap;
}
tbody td, tbody th { padding: .55rem .8rem; border-bottom: 1px solid var(--rule); vertical-align: middle; }
tbody th { font: inherit; font-weight: 400; text-align: left; }
tbody tr:last-child td, tbody tr:last-child th { border-bottom: 0; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
td.field { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: .78rem; color: var(--ink-3); }
td.name { min-width: 12rem; }
.absent-note { color: var(--ink-3); font-style: italic; }

.legend { display: flex; flex-wrap: wrap; gap: 1.2rem; font-size: .8rem; color: var(--ink-2); margin: 1.4rem 0 .2rem; padding: 0; list-style: none; }
.legend li { display: flex; align-items: center; gap: .45rem; }
.swatch { width: .8rem; height: .8rem; border-radius: 2px; flex: none; }
.sw-present { background: var(--present); }
.sw-unknown { background: var(--unknown); }
.sw-absent { background: var(--absent); }

.bar { display: flex; gap: 2px; height: 11px; min-width: 8rem; width: 100%; }
.bar i { display: block; height: 100%; }
.bar i:first-child { border-radius: 3px 0 0 3px; }
.bar i:last-child { border-radius: 0 3px 3px 0; }
.bar i:only-child { border-radius: 3px; }
.b-present { background: var(--present); }
.b-unknown { background: var(--unknown); }
.b-absent { background: var(--absent); }
td.barcell { width: 34%; min-width: 9rem; }

blockquote {
  margin: 1rem 0 1.4rem; padding: 1rem 1.2rem; background: var(--quote-bg);
  border-left: 3px solid var(--rule-strong); font-size: .95rem; color: var(--ink-2);
}
blockquote p { margin: 0; max-width: none; }
.measured { font-size: .9rem; color: var(--ink-2); max-width: 44rem; }
.measured strong { color: var(--ink); font-weight: 600; }

dl.meta { display: grid; grid-template-columns: max-content 1fr; gap: .45rem 1.4rem; font-size: .87rem; margin: 1.2rem 0; }
dl.meta dt { color: var(--ink-3); }
dl.meta dd { margin: 0; word-break: break-word; }

footer.page { border-top: 1px solid var(--rule); margin-top: 4rem; padding-top: 1.6rem; font-size: .84rem; color: var(--ink-3); }
footer.page p { max-width: 44rem; }
.card-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(17rem, 1fr)); gap: 1.4rem; margin: 2rem 0; }
.card { border: 1px solid var(--rule); background: var(--surface-raised); padding: 1.3rem 1.4rem 1.5rem; }
.card h3 { margin-top: 0; color: var(--ink); font-size: 1.08rem; }
.card p { font-size: .9rem; color: var(--ink-2); margin-bottom: .9rem; }
"""
)


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def num(value: int) -> str:
    return f"{value:,}"


def pct(tenths: int | None) -> str:
    """A share, or words saying there is nothing to take a share of."""
    if tenths is None:
        return '<span class="absent-note">no records</span>'
    return f"{tenths // 10}.{tenths % 10}%"


def _width(part: int, total: int) -> str:
    if total <= 0:
        return "0"
    hundredths = (part * 20000 + total) // (total * 2)
    return f"{hundredths / 100:.2f}"


def state_bar(present: int, unknown: int, absent: int) -> str:
    """A stacked proportion bar for the three states, in fixed order.

    Every bar sits in a row beside the three counts it draws, so identity is never
    carried by colour alone and a reader who cannot separate the hues still has the
    numbers.
    """
    total = present + unknown + absent
    if total <= 0:
        return '<span class="absent-note">no records</span>'
    parts = []
    for value, cls in (
        (present, "b-present"),
        (unknown, "b-unknown"),
        (absent, "b-absent"),
    ):
        if value:
            parts.append(f'<i class="{cls}" style="width:{_width(value, total)}%"></i>')
    return f'<div class="bar" role="presentation">{"".join(parts)}</div>'


def legend() -> str:
    """The three-state key.

    The swatches are hidden from assistive technology because the words beside them say
    the same thing, and every table that uses this key prints all three counts as
    numbers in the same row as the bar they colour.
    """
    items = (
        ("sw-present", "Recorded value"),
        ("sw-unknown", "Recorded as unknown"),
        ("sw-absent", "Empty cell"),
    )
    return (
        '<ul class="legend" role="list">'
        + "".join(
            f'<li><i class="swatch {cls}" aria-hidden="true"></i>{label}</li>'
            for cls, label in items
        )
        + "</ul>"
    )


@dataclass(frozen=True)
class Tile:
    value: str
    label: str


def tiles(items: Sequence[Tile]) -> str:
    cells = "".join(
        f'<li class="tile"><div class="tile-value">{esc(item.value)}</div>'
        f'<div class="tile-label">{esc(item.label)}</div></li>'
        for item in items
    )
    return f'<ul class="tiles" role="list">{cells}</ul>'


def caveat_block(source: Source) -> str:
    parts = [
        '<p class="lede">Every measurement on this page exists because the dataset\'s own '
        "documentation says the limitation is there. The quotes below are "
        f"{esc(source.publisher.split(',')[0])}'s words, taken from the dataset "
        "description on the retrieval date, beside what this project counted in "
        "response.</p>"
    ]
    for caveat in source.caveats:
        parts.append(f"<h3>{esc(caveat.topic)}</h3>")
        parts.append(f"<blockquote><p>{esc(caveat.quote)}</p></blockquote>")
        parts.append(
            f'<p class="measured"><strong>Counted as:</strong> {esc(caveat.measured_as)}</p>'
        )
    return "".join(parts)


def provenance_block(source: Source, *, is_fixture: bool) -> str:
    acquired = (
        "built from committed fixtures, not from an acquired file"
        if is_fixture
        else f"{num(source.record_count)} records, {num(source.raw_bytes)} bytes"
    )
    sha = "not applicable to a fixture build" if is_fixture else source.sha256
    retrieved = "not applicable to a fixture build" if is_fixture else source.retrieved
    version = "not applicable to a fixture build" if is_fixture else source.version
    return (
        '<dl class="meta">'
        f"<dt>Dataset</dt><dd>{esc(source.title)}</dd>"
        f"<dt>Publisher</dt><dd>{esc(source.publisher)}</dd>"
        f'<dt>Landing page</dt><dd><a href="{esc(source.landing_page)}">{esc(source.landing_page)}</a></dd>'
        f"<dt>Layer read</dt><dd>{esc(source.layer)}</dd>"
        f"<dt>Endpoint</dt><dd>{esc(source.endpoint)}</dd>"
        f"<dt>Licence</dt><dd>{esc(source.licence)}</dd>"
        f"<dt>Version</dt><dd>{esc(version)}</dd>"
        f"<dt>Retrieved</dt><dd>{esc(retrieved)}</dd>"
        f"<dt>Acquired</dt><dd>{esc(acquired)}</dd>"
        f"<dt>SHA-256</dt><dd>{esc(sha)}</dd>"
        "</dl>"
    )


def scroll_region(caption_id: str, *, tall: bool = False) -> str:
    """Open a horizontally scrollable table container a keyboard can actually reach.

    These pages carry tables wider than a narrow viewport, and each sits inside a
    container with ``overflow-x: auto``. That is the conforming answer to WCAG 2.2 SC
    1.4.10 Reflow, because the page itself does not scroll. On its own it is also a WCAG
    2.1.1 Keyboard failure: a container that scrolls and cannot be focused scrolls for a
    mouse and a trackpad and not for a keyboard, so a sighted keyboard user cannot reach
    the columns past the right edge at all. axe reports it as
    ``scrollable-region-focusable`` and rates it serious. jsdom does no layout, so
    nothing in the jsdom run ever knew the container scrolls; running the same rule set
    in a browser is what found it.

    ``tabindex="0"`` is the fix. The element is a named ``<section>`` rather than a
    ``div``, which is what keeps the fix from costing something else: a bare focusable
    ``div`` is a tab stop a screen reader announces as nothing at all, while a named
    section is a region landmark natively, with no ARIA attribute to go stale. The name
    comes from the table's own caption, which every table here already carries.
    html-validate refuses the ARIA spelling of this in favour of the element.
    """
    classes = "scroll tall" if tall else "scroll"
    return f'<section class="{classes}" tabindex="0" aria-labelledby="{caption_id}">'


def field_table(
    fields: Sequence[FieldCoverage], *, caption_id: str, caption: str
) -> str:
    rows = []
    for field in fields:
        marker_note = ""
        if field.markers:
            listed = ", ".join(
                f"{esc(marker)} ({num(count)})"
                for marker, count in sorted(field.markers.items())
            )
            basis = BASIS_NOTE.get(field.basis)
            suffix = f". Basis: {esc(basis)}" if basis else ""
            marker_note = f'<div class="absent-note">markers: {listed}{suffix}</div>'
        elif field.basis is not Basis.NONE:
            # A field can declare a finding of absence without any marker ever firing.
            # The basis still belongs on the page, because the finding is a judgment.
            marker_note = (
                f'<div class="absent-note">Basis: {esc(BASIS_NOTE[field.basis])}</div>'
            )
        count, distinct = field.outside_domain, field.outside_domain_distinct
        outside = ""
        if count is None or distinct is None:
            # Not "0 values outside the published domain". No domain is published for
            # this field, so nothing was compared against one and nothing was counted.
            # Leaving the row silent would read exactly like a field whose domain is
            # published and holds every value it carries, and those are different facts.
            outside = (
                '<div class="absent-note">The layer publishes no coded-value domain for '
                "this field, so no value here is counted as outside one</div>"
            )
        elif count:
            outside = (
                f'<div class="absent-note">{num(count)} value'
                f"{'' if count == 1 else 's'} outside the published "
                f"domain across {num(distinct)} distinct "
                f"spelling{'' if distinct == 1 else 's'}</div>"
            )
        rows.append(
            "<tr>"
            f'<th scope="row" class="name">{esc(field.label)}{marker_note}{outside}'
            f'<div class="field">{esc(field.name)}</div></th>'
            f'<td class="num">{num(field.present)}</td>'
            f'<td class="num">{num(field.explicit_unknown)}</td>'
            f'<td class="num">{num(field.not_recorded)}</td>'
            f'<td class="num">{pct(field.present_tenths_pct)}</td>'
            f'<td class="barcell">'
            f"{state_bar(field.present, field.explicit_unknown, field.not_recorded)}</td>"
            "</tr>"
        )
    caption_ref = f"{caption_id}-caption"
    return (
        f"{legend()}{scroll_region(caption_ref, tall=True)}"
        f'<table id="{caption_id}">'
        f'<caption class="visually-hidden" id="{caption_id}-caption">'
        f"{esc(caption)}</caption><thead><tr>"
        '<th scope="col">Field</th>'
        '<th scope="col" class="num">Recorded value</th>'
        '<th scope="col" class="num">Recorded as unknown</th>'
        '<th scope="col" class="num">Empty cell</th>'
        '<th scope="col" class="num">Value present</th>'
        '<th scope="col">Split</th>'
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></section>"
        f"{DOMAIN_NOTE}"
    )


def page(
    *,
    title: str,
    description: str,
    body: str,
    active: str,
    is_fixture: bool,
) -> str:
    fixture_banner = (
        '<p class="badge">Fixture build. These numbers describe the committed test '
        "fixtures, not CAL FIRE's published files.</p>"
        if is_fixture
        else ""
    )
    nav_items = [
        ("index.html", "Overview", "index"),
        ("perimeters.html", "Fire perimeters", "perimeters"),
        ("dins.html", "Damage inspections", "dins"),
    ]
    links = "".join(
        f'<a href="{href}"{current}>{label}</a>'
        for href, label, key in nav_items
        for current in [' aria-current="page"' if key == active else ""]
    )
    canonical = SITE_URL + CANONICAL_PATH[active]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Perimeter">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:locale" content="en_US">
<meta name="twitter:card" content="summary">
<style>{STYLESHEET}</style>
</head>
<body>
<a class="skip-link" href="#content">Skip to the measurement</a>
<nav aria-label="Pages"><div class="wrap"><span class="mark">Perimeter</span>{links}</div></nav>
<div class="wrap">
<main id="content">
{fixture_banner}
{body}
</main>
<footer class="page">
<p>{esc(DISCLAIMER)}</p>
<p>Source data is published by the California Department of Forestry and Fire Protection
under a Creative Commons Attribution licence and is reproduced here only as counts.
This project holds no view on how any agency collects or manages its data. It counts what
the published files contain, in the terms the publishers use to describe them.</p>
</footer>
</div>
</body>
</html>
"""


def perimeters_page(report: PerimeterReport, *, is_fixture: bool) -> str:
    span = (
        f"{report.earliest_year} to {report.latest_year}"
        if report.earliest_year is not None and report.latest_year is not None
        else "no year recorded on any record"
    )
    irwin_share = pct(present_tenths_of_percent(report.irwin_present, report.records))

    decade_rows = []
    for decade in report.thresholds:
        decade_label = (
            "No year recorded" if decade.decade is None else f"{decade.decade}s"
        )
        below = decade.below
        decade_rows.append(
            "<tr>"
            f'<th scope="row">{esc(decade_label)}</th>'
            f'<td class="num">{num(decade.records)}</td>'
            f'<td class="num">{num(decade.acres_recorded)}</td>'
            + "".join(
                f'<td class="num">{num(below[threshold])}</td>'
                for threshold in sorted(below)
            )
            + "</tr>"
        )

    year_rows = []
    for cohort in report.years:
        year_label = "No year recorded" if cohort.year is None else str(cohort.year)
        share = pct(present_tenths_of_percent(cohort.irwin_present, cohort.records))
        bar = state_bar(
            cohort.irwin_present,
            cohort.irwin_explicit_unknown,
            cohort.irwin_not_recorded,
        )
        year_rows.append(
            "<tr>"
            f'<th scope="row">{esc(year_label)}</th>'
            f'<td class="num">{num(cohort.records)}</td>'
            f'<td class="num">{num(cohort.irwin_present)}</td>'
            f'<td class="num">{num(cohort.irwin_not_recorded)}</td>'
            f'<td class="num">{share}</td>'
            f'<td class="barcell">{bar}</td>'
            "</tr>"
        )

    duplicate_rows = "".join(
        "<tr>"
        f'<th scope="row" class="name">{esc(signal.key)}'
        f'<div class="absent-note">{esc(signal.description)}</div></th>'
        f'<td class="num">{num(signal.keyed_records)}</td>'
        f'<td class="num">{num(signal.distinct_keys)}</td>'
        f'<td class="num">{num(signal.reused_keys)}</td>'
        f'<td class="num">{num(signal.records_sharing_a_key)}</td>'
        "</tr>"
        for signal in report.duplicates
    )

    # Read the threshold list off the first cohort so the header matches the body
    # exactly. An empty report has no cohorts and therefore no threshold columns.
    threshold_headers = "".join(
        f'<th scope="col" class="num">Under {threshold} acres</th>'
        for threshold in (
            sorted(report.thresholds[0].below) if report.thresholds else ()
        )
    )

    body = f"""
<header class="page">
<p class="eyebrow">Measurement one of two</p>
<h1>How complete is California's historical fire perimeter record?</h1>
<p class="standfirst">FRAP publishes the answer in prose: the dataset is the most complete
digital record of fire perimeters in California, and it is still incomplete. This page
turns that sentence into counts, per year and per field, so anyone building on the data
can see the shape of what is there before they rely on it.</p>
</header>

{
        tiles(
            [
                Tile(num(report.records), "Perimeter records in the layer"),
                Tile(span, "Fire years represented"),
                Tile(num(report.records_without_year), "Records carrying no fire year"),
                Tile(
                    f"{num(report.irwin_present)} ({irwin_share})",
                    "Records carrying an IRWIN ID",
                ),
            ]
        )
    }

<h2>Three states, field by field</h2>
<p>A cell can hold a value, hold a published code or marker meaning the value could not be
determined, or hold nothing. Counting only the third of those would make several fields
here look complete when they are not. Cause is the clearest case: no cause cell is empty,
and a large share of them carry the published code for
<em>Unknown / Unidentified</em>. Collection method behaves the same way, which is what
FRAP's release note about editing null collection methods to Unknown describes.</p>
{
        field_table(
            report.fields,
            caption_id="frap-fields",
            caption="Perimeter fields, each counted in three states",
        )
    }
<p class="measured">Markers listed under a field name are the exact text this project
reviewed for that field before counting it as a marker rather than as a value. A field
number of all zeros, for instance, is counted apart from recorded numbers, because reading
it as an identifier would make thousands of unrelated fires appear to share one incident.</p>
<p class="measured">Each field also carries the <strong>basis</strong> its markers rest
on. A published basis means the value is a code in the layer's own domain, which anyone
can re-read at the endpoint listed under Provenance below. An inferred basis means the
publisher documents no such code and this project read the value off the file. Both are
counted the same way; they are not worth the same confidence, so the page says which is
which rather than leaving a reader to assume. The full audit, with the evidence and the
effect of each call on the numbers above, is in <code>docs/MARKERS.md</code>.</p>

<h2>Records per year, and IRWIN linkage inside each year</h2>
<p>IRWIN is the federal incident identifier that links a perimeter to a federal incident
record. FRAP's own release notes describe the newly added Global ID as covering records
"pre-dating IRWIN IDs", so its absence on older records is expected rather than
surprising. What the dataset does not publish alongside itself is where the identifier
starts appearing and how much of each recent year carries one. Years no record names are absent from this table
rather than shown as years with zero fires, because the data cannot tell the difference
between a year with no fires and a year whose fires are missing.</p>
<section class="scroll tall" tabindex="0" aria-labelledby="cap-years"><table>
<caption class="visually-hidden" id="cap-years">Perimeter records per fire year, with IRWIN ID coverage inside each year</caption>
<thead><tr>
<th scope="col">Fire year</th>
<th scope="col" class="num">Records</th>
<th scope="col" class="num">IRWIN ID present</th>
<th scope="col" class="num">IRWIN ID absent</th>
<th scope="col" class="num">Present</th>
<th scope="col">Split</th>
</tr></thead><tbody>{"".join(year_rows)}</tbody></table></section>

<h2>Surviving records against the published collection criteria</h2>
<p>FRAP names the acreages agencies submit against, and separately records that some fires
are missing for having been "too small for the minimum cutoffs". These are counts of
records that are present and sit below each named acreage. A record below a threshold is
not an error and is not evidence of one: the criteria quoted are the current ones, earlier
eras used different cutoffs that this project has not established, and a fire may be
submitted for reasons other than size. The counts are here so that a reader can see how
much of each decade sits near the numbers FRAP names.</p>
<section class="scroll" tabindex="0" aria-labelledby="cap-thresholds"><table>
<caption class="visually-hidden" id="cap-thresholds">Surviving perimeter records per decade against each published collection acreage</caption>
<thead><tr>
<th scope="col">Decade</th>
<th scope="col" class="num">Records</th>
<th scope="col" class="num">Acreage recorded</th>
{threshold_headers}
</tr></thead><tbody>{"".join(decade_rows)}</tbody></table></section>

<h2>Records sharing an identifier</h2>
<p>FRAP states that known errors "include duplicate fires". These are counts of records
that share an identifier or an identifying combination. They are candidates and nothing
more. Deciding that two records describe one fire is a judgment about geometry and
history, and this project downloads no geometry and makes no such judgment. Each row keys
only the records carrying every part of that key, so a low count is never produced by
missing values quietly padding the total.</p>
<p class="measured">The year, unit and incident-number row depends on one judgment call
worth stating plainly. The all-zeros local incident number is counted as a placeholder
rather than as a number, so records carrying it are not keyed. Reading it as a number
instead would key {num(report.placeholder_counterfactual.keyed_records)} records and
report {num(report.placeholder_counterfactual.records_sharing_a_key)} of them as sharing
a key, nearly all of that produced by unrelated fires in one unit and one year sharing a
value that stands in for no number. That counterfactual is counted rather than asserted:
it is in the JSON artifact beside this page under
<code>marker_counterfactuals</code>. Nothing FRAP publishes documents the all-zeros
value, so the call is an inference from the file, and <code>docs/MARKERS.md</code> sets
out the evidence behind it.</p>
<section class="scroll" tabindex="0" aria-labelledby="cap-duplicates"><table>
<caption class="visually-hidden" id="cap-duplicates">Perimeter records sharing an identifier or an identifying combination</caption>
<thead><tr>
<th scope="col">Key</th>
<th scope="col" class="num">Records carrying the whole key</th>
<th scope="col" class="num">Distinct keys</th>
<th scope="col" class="num">Keys used more than once</th>
<th scope="col" class="num">Records sharing a key</th>
</tr></thead><tbody>{duplicate_rows}</tbody></table></section>

<h2>Methodology and the caveats this page operationalizes</h2>
{caveat_block(FRAP)}

<h3>Provenance</h3>
{provenance_block(FRAP, is_fixture=is_fixture)}
<p class="measured">Attributes were read without geometry, so nothing on this page
describes the shape, extent or accuracy of any polygon. Over-generalization, which FRAP
lists among the known issues, is a property of the geometry and is therefore outside what
this page measures.</p>
"""
    return page(
        title="Historical fire perimeter completeness | Perimeter",
        description=(
            "How complete California's historical fire perimeter record is, counted "
            "per fire year and per field. Unofficial."
        ),
        body=body,
        active="perimeters",
        is_fixture=is_fixture,
    )


def dins_page(report: DinsReport, *, is_fixture: bool) -> str:
    damage_rows = []
    for value, count in sorted(report.damage.items(), key=lambda kv: (-kv[1], kv[0])):
        if value == "not_recorded":
            label = "Empty cell"
            meaning = "No damage value was recorded for this structure."
        elif value == "explicit_unknown":
            label = "Recorded as unknown"
            meaning = "A marker was recorded in place of a damage value."
        elif value == "Inaccessible":
            label = value
            meaning = (
                "CAL FIRE's published value for a structure the inspection identified "
                "but could not reach. It is a recorded value, not a blank."
            )
        elif value == "No Damage":
            label = value
            meaning = (
                "An inspection finding: the structure was looked at and found undamaged. "
                "This is not a null and it is not a zero."
            )
        else:
            label = value
            meaning = "A recorded damage band."
        share = pct(present_tenths_of_percent(count, report.records))
        damage_rows.append(
            "<tr>"
            f'<th scope="row" class="name">{esc(label)}'
            f'<div class="absent-note">{esc(meaning)}</div></th>'
            f'<td class="num">{num(count)}</td>'
            f'<td class="num">{share}</td>'
            "</tr>"
        )

    access_rows = "".join(
        "<tr>"
        f'<th scope="row" class="name">{esc(row.label)}'
        f'<div class="field">{esc(row.name)}</div></th>'
        f'<td class="num">{num(row.assessed_present)}</td>'
        f'<td class="num">{pct(row.assessed_tenths_pct)}</td>'
        f'<td class="num">{num(row.inaccessible_present)}</td>'
        f'<td class="num">{pct(row.inaccessible_tenths_pct)}</td>'
        "</tr>"
        for row in report.by_access
    )

    # What the two columns are counted over, and what they are not counted over. The
    # denominators are two populations of a three-way split, so a record whose damage
    # field says nothing about access is in neither, and the page says how many rather
    # than leaving a reader to add the columns up and find the file is short. There are
    # none in the acquired file today, which is a fact worth printing and not a reason
    # to leave the sentence out.
    undetermined = report.by_access[0].undetermined_total if report.by_access else 0
    if undetermined:
        access_note = (
            f"<p>The two columns are counted over {num(report.access.assessed)} "
            f"assessed records and {num(report.access.inaccessible)} recorded as "
            f"Inaccessible. {num(undetermined)} are in neither, because their damage "
            "field records nothing and so says nothing about whether the structure was "
            "reached. Their completeness is not in this table; it is published per "
            "field, in the JSON artifact beside this page, as "
            "<code>undetermined_present</code> and <code>undetermined_total</code>.</p>"
        )
    else:
        access_note = (
            f"<p>The two columns are counted over {num(report.access.assessed)} "
            f"assessed records and {num(report.access.inaccessible)} recorded as "
            "Inaccessible, which between them is every record in this file. A record "
            "whose damage field recorded nothing would be in neither column, since "
            "that field is what says whether a structure was reached. There are none "
            "here. The count is published per field in the JSON artifact beside this "
            "page, so a later retrieval carrying some cannot pass unremarked.</p>"
        )

    incident_fields = (
        "STRUCTURETYPE",
        "ROOFCONSTRUCTION",
        "EAVES",
        "VENTSCREEN",
        "APN",
    )
    incident_rows = []
    for incident in report.incident_rows:
        by_name = {field.name: field for field in incident.fields}
        cells = "".join(
            f'<td class="num">{pct(by_name[name].present_tenths_pct)}</td>'
            for name in incident_fields
            if name in by_name
        )
        name = incident.key.name or "Not recorded"
        number = incident.key.number or "Not recorded"
        year = (
            "Not recorded"
            if incident.key.start_year is None
            else str(incident.key.start_year)
        )
        incident_rows.append(
            "<tr>"
            f'<th scope="row" class="name">{esc(name)}'
            f'<div class="absent-note">{esc(number)}</div></th>'
            f"<td>{esc(year)}</td>"
            f'<td class="num">{num(incident.records)}</td>'
            f'<td class="num">{num(incident.access.assessed)}</td>'
            f'<td class="num">{num(incident.access.inaccessible)}</td>'
            f"{cells}"
            "</tr>"
        )
    incident_headers = "".join(
        f'<th scope="col" class="num">{esc(label)}</th>'
        for label in ("Structure type", "Roof", "Eaves", "Vent screen", "APN")
    )

    body = f"""
<header class="page">
<p class="eyebrow">Measurement two of two</p>
<h1>What the damage inspection record contains, per field and per incident</h1>
<p class="standfirst">CAL FIRE states the rule for reading a blank in this dataset:
"Attributes with null values could not be determined." A blank is therefore a fact about
the inspection, not a fact about the structure. This page counts every measured field in
three states and reports each incident separately, so the difference between an
undetermined attribute and an undamaged building is on the page rather than left to the
reader.</p>
</header>

{
        tiles(
            [
                Tile(num(report.records), "Structure records"),
                Tile(num(report.incidents), "Incidents these records name"),
                Tile(num(report.access.assessed), "Records with a damage assessment"),
                Tile(
                    num(report.access.inaccessible), "Records recorded as Inaccessible"
                ),
            ]
        )
    }

<h2>What the damage field records</h2>
<p>Damage is the field that says what the inspection concluded, and the vocabulary CAL
FIRE publishes for it draws two lines that matter more than any other for reading a null
here. <em>No Damage</em> is a finding: an inspector looked at the structure and recorded
that it was undamaged. <em>Inaccessible</em> is a different finding: the structure was
identified but could not be reached. Neither is an empty cell, and neither is a zero.</p>
<section class="scroll" tabindex="0" aria-labelledby="cap-damage"><table>
<caption class="visually-hidden" id="cap-damage">Structure records per recorded damage value</caption>
<thead><tr>
<th scope="col">Recorded value</th>
<th scope="col" class="num">Records</th>
<th scope="col" class="num">Share</th>
</tr></thead><tbody>{"".join(damage_rows)}</tbody></table></section>

<h2>Three states, field by field</h2>
<p>Each measured field counted across every record. A recorded value includes findings of
absence such as <em>No Eaves</em> or <em>No Fence</em>, which are observations rather than
missing data. A recorded unknown is a published code or a marker word standing where a
value would go. An empty cell is what CAL FIRE describes as an attribute that could not be
determined.</p>
{
        field_table(
            report.fields,
            caption_id="dins-fields",
            caption="Damage inspection fields, each counted in three states",
        )
    }
<p class="measured">Each field carries the <strong>basis</strong> its markers rest on. A
published basis means the value appears in the layer's own coded-value domain, which
anyone can re-read at the endpoint listed under Provenance below. An inferred basis means
CAL FIRE documents no such code for that field and this project read the value off the
file. Two calls on this page move enough records to name here. The distance to a utility
or miscellaneous structure is published with Not Applicable spelled <code>NA</code>, and
the file also carries <code>N/A</code>; the two never appear in the same incident and
they fall on opposite sides of the 2020 incidents, so both are counted as the published
finding rather than one being read as missing data. And the site address carries two
whole placeholder strings rather than marker words, which are counted apart from recorded
addresses. Both calls, their evidence and their effect on these counts are set out in
<code>docs/MARKERS.md</code>.</p>

<h2>Assessed structures against structures that could not be reached</h2>
<p>This is the split that separates "not inspected" from "inspected, field blank". CAL
FIRE names fire damage and poor access as the major limiting factors for inspectors, and
the schema records the outcome directly in the damage field. A construction attribute
missing on a structure recorded as Inaccessible is a different fact from the same
attribute missing on a structure that was assessed, and reporting one completeness number
across both would hide that.</p>
<section class="scroll tall" tabindex="0" aria-labelledby="cap-access"><table>
<caption class="visually-hidden" id="cap-access">Field completeness on assessed records against records recorded as Inaccessible</caption>
<thead><tr>
<th scope="col">Field</th>
<th scope="col" class="num">Present, assessed</th>
<th scope="col" class="num">Share of assessed</th>
<th scope="col" class="num">Present, inaccessible</th>
<th scope="col" class="num">Share of inaccessible</th>
</tr></thead><tbody>{access_rows}</tbody></table></section>
{access_note}

<h2>Coverage per incident</h2>
<p>Completeness is not evenly distributed across incidents, and an average across the
whole file describes no incident in particular. Each row is one incident as the records
name it, by incident name, incident number and start year. Records that differ in whether
an incident number was recorded are kept apart rather than merged, because merging them
would mean assuming they are the same incident. The full per-field counts for every
incident are in the JSON artifact beside this page.</p>
<section class="scroll tall" tabindex="0" aria-labelledby="cap-incidents"><table>
<caption class="visually-hidden" id="cap-incidents">Records, access split and field completeness for every incident these records name</caption>
<thead><tr>
<th scope="col">Incident</th>
<th scope="col">Start year</th>
<th scope="col" class="num">Records</th>
<th scope="col" class="num">Assessed</th>
<th scope="col" class="num">Inaccessible</th>
{incident_headers}
</tr></thead><tbody>{"".join(incident_rows)}</tbody></table></section>
<p class="measured">The five columns after the record counts are the share of that
incident's records carrying a recorded value in that field. Structure type, roof, eaves
and vent screen are recorded by the inspector on site. APN is added afterwards by a
spatial join, so its coverage measures the join rather than the inspection.</p>

<h2>Methodology and the caveats this page operationalizes</h2>
{caveat_block(DINS)}

<h3>Provenance</h3>
{provenance_block(DINS, is_fixture=is_fixture)}
<p class="measured">No damage or loss totals are derived here, and no structure, parcel or
address is republished. Every number on this page is a count of records in a state.</p>
"""
    return page(
        title="DINS damage inspection coverage | Perimeter",
        description=(
            "What California's post-fire damage inspection records contain, counted "
            "per field and per incident. Unofficial."
        ),
        body=body,
        active="dins",
        is_fixture=is_fixture,
    )


def index_page(
    perimeters: PerimeterReport, dins: DinsReport, *, is_fixture: bool
) -> str:
    body = f"""
<header class="page">
<p class="eyebrow">Coverage measurement</p>
<h1>Perimeter</h1>
<p class="standfirst">Two coverage measurements over California's public wildfire
datasets, published as counts. CAL FIRE and FRAP document the limits of these datasets in
their own metadata. This project counts those limits, per year and per incident, so the
people building on the data can reason about them.</p>
</header>

<p class="lede">Both datasets carry careful descriptions of what they do and do not
contain. What is not published alongside them is the arithmetic: how many records per year, how
many carry a federal identifier, how many cells in each field hold a value, how many hold
a code meaning the value could not be determined, and how many hold nothing at all. Those
are the numbers here. Nothing on these pages models fire risk, tracks an incident, or
estimates a loss.</p>

<h2>The two measurements</h2>
<div class="card-grid">
<div class="card">
<h3>Historical fire perimeter completeness</h3>
<p>{num(perimeters.records)} perimeter records, counted per fire year, with IRWIN
identifier coverage inside each year, surviving records measured against the published
collection acreages, and counts of records sharing an identifier.</p>
<p><a href="perimeters.html">Read the measurement</a></p>
</div>
<div class="card">
<h3>Damage inspection coverage</h3>
<p>{num(dins.records)} structure records across {num(dins.incidents)} incidents, with
per-field and per-incident completeness, and the difference between a structure that could
not be reached and a structure inspected and found undamaged kept visible throughout.</p>
<p><a href="dins.html">Read the measurement</a></p>
</div>
</div>

<h2>How absence is handled</h2>
<p>Every measured cell is counted in one of three states, and the three are never
collapsed into each other:</p>
<section class="scroll" tabindex="0" aria-labelledby="cap-states"><table>
<caption class="visually-hidden" id="cap-states">The three states every measured cell is counted in</caption>
<thead><tr>
<th scope="col">State</th><th scope="col">What it means</th>
</tr></thead><tbody>
{
        "".join(
            f'<tr><th scope="row" class="name">{esc(label)}</th>'
            f"<td>{esc(meaning)}</td></tr>"
            for _key, label, meaning in STATE_LABELS
        )
    }
</tbody></table></section>
<p>A null is not a zero. A structure not inspected is not a structure without damage. A
field a dataset never collected is not a field full of zeroes. Where a share would have no
denominator, these pages print words saying so rather than a number. Where a value that
reads like a missing-data marker turns up in a field this project has not reviewed for
that marker, the build stops rather than guessing what it meant.</p>

<h2>Which judgment calls rest on what</h2>
<p>Deciding that a cell holds a marker rather than a value is a judgment, and the two
measurement pages label every field with the basis its markers rest on. Twelve of the
twenty-eight fields that declare any marker or finding are <strong>published</strong>:
the value is a code in the layer's own coded-value domain, or a sentence in the
publisher's documentation, and it can be re-read at the endpoints listed under Sources
below. The other sixteen are <strong>inferred</strong>: the field is free text, or the
value is one the published domain does not carry, and this project read it off the
acquired file. Both sets are counted the same way and neither is a defect in either
dataset; both publishers document the domains they constrain and say which fields are
free text. The difference is in how much weight a reader should put on the call, so the
pages print it rather than leaving it to be assumed. Every entry, with its evidence, the
URL it can be checked against, its effect on the published figures and a confidence, is
in <code>docs/MARKERS.md</code>.</p>

<h2>Sources</h2>
<p>Both datasets are published by the California Department of Forestry and Fire
Protection under a Creative Commons Attribution licence, and both were read from the
GeoServices endpoint listed among the dataset's own published resources. Geometry was not
requested, because no measurement here needs it. Full detail, including byte counts and
file hashes, is in <code>PROVENANCE.md</code> and repeated on each page.</p>
{provenance_block(FRAP, is_fixture=is_fixture)}
{provenance_block(DINS, is_fixture=is_fixture)}
"""
    return page(
        title="Perimeter | Coverage measures for California wildfire datasets",
        description=(
            "Two coverage measurements over California's public wildfire datasets, "
            "published as counts. Unofficial."
        ),
        body=body,
        active="index",
        is_fixture=is_fixture,
    )
