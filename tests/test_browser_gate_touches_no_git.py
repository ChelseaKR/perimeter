"""The browser gate must not write to this repository's git directory.

`tools/a11y_browser` reads static pages off disk as `file://` URLs. It has no reason to
touch git at all. Playwright disagrees by default: its git-info plugin, when it detects a
GitHub Actions pull-request run, calls `gitDiff`, and `gitDiff` begins with

    git fetch origin <pr base sha> --depth=1 --no-auto-maintenance --no-auto-gc \
        --no-tags --no-recurse-submodules

(`node_modules/playwright/lib/runner/index.js`). The harness's working directory is
inside this work tree, so `--depth=1` writes `.git/shallow` at the repository root.

Measured on a runner, 2026-09-06, on a `pull_request` event:

    after actions/checkout .............. no .git/shallow
    after `make browser-sync` ........... no .git/shallow
    after tests/test_a11y_browser_gate.py .git/shallow holds main's own tip

`tests/test_release_claims.py` then refuses to read the tag list, which is right -- a
shallow checkout cannot tell an untagged repository from an unfetched one, and this
project has no tags, so reading "none found" as "none exist" would be the vacuous pass
that file exists to prevent. The consequence was that `make verify` failed on pull
requests whose diffs had nothing to do with tags, releases, or accessibility, and failed
*intermittently*, because whether the browser gate ran before the release-claims tests
was down to how pytest-xdist happened to distribute the suite.

Two controls, and neither of them needs a browser, a runner, or a pull request:

* the harness config declares the capture off, in both halves;
* the Python that invokes the harness removes the environment names Playwright reads to
  decide it is in CI.

Either alone would have prevented this. Both are here because the config is the durable
fix (it holds for `npm test` and for a hand-run) and the environment scrub is the one
that cannot be undone by a Playwright default changing under a version bump.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "tools" / "a11y_browser" / "playwright.config.ts"
GATE = Path(__file__).with_name("test_a11y_browser_gate.py")


def _gate_module() -> ModuleType:
    """Load the gate's test module by path.

    ``tests/`` is not a package and pytest imports it under ``importlib`` mode, so a
    plain ``from tests.test_a11y_browser_gate import ...`` does not resolve. Loading by
    path keeps the two controls reading the same code the gate actually runs, rather than
    a copy of it that could drift into agreeing with itself.
    """
    name = "perimeter_tests_a11y_browser_gate"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, GATE)
    assert spec is not None and spec.loader is not None, f"cannot load {GATE}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_CI_NAMES_PLAYWRIGHT_READS: tuple[str, ...] = _gate_module()._CI_NAMES_PLAYWRIGHT_READS
harness_env = _gate_module().harness_env

#: `captureGitInfo: { commit: false, diff: false }`, tolerant of formatting but not of a
#: value. Playwright treats *undefined* as "on when this looks like CI", so a key that is
#: absent, commented out, or set to anything but `false` leaves the fetch enabled.
_CAPTURE = re.compile(r"^\s*captureGitInfo:\s*\{(?P<body>[^}]*)\}", re.MULTILINE)


def _capture_git_info_settings() -> dict[str, str]:
    """The two `captureGitInfo` fields as the config file declares them."""
    found = _CAPTURE.search(CONFIG.read_text(encoding="utf-8"))
    assert found is not None, (
        "tools/a11y_browser/playwright.config.ts declares no captureGitInfo. Playwright "
        "reads an absent setting as 'capture when this looks like CI', so the harness "
        "would run `git fetch --depth=1` in this work tree on every pull request."
    )
    body = found.group("body")
    return {
        key.strip(): value.strip()
        for key, value in (
            pair.split(":", 1) for pair in body.split(",") if ":" in pair
        )
    }


@pytest.mark.parametrize("half", ["commit", "diff"])
def test_the_harness_captures_no_git_info(half: str) -> None:
    """`diff` is the half that fetches; `commit` is off too, because neither is used."""
    settings = _capture_git_info_settings()
    assert half in settings, (
        f"captureGitInfo does not declare {half}. Playwright reads an undeclared half as "
        "'on when this looks like CI'."
    )
    assert settings[half] == "false", (
        f"captureGitInfo.{half} is {settings[half]!r}, not false. The diff half runs "
        "`git fetch origin <pr base sha> --depth=1` in this work tree, which writes "
        ".git/shallow and makes tests/test_release_claims.py refuse to read the tags."
    )


@pytest.mark.parametrize("name", _CI_NAMES_PLAYWRIGHT_READS)
def test_the_harness_is_not_told_it_is_running_in_ci(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Set the variable, then check the harness's environment does not carry it.

    Setting it first matters: asserting a name is absent from an environment that never
    had it is an assertion that cannot fail, and this repository has an ADR about gates
    that cannot fail.
    """
    monkeypatch.setenv(name, "definitely-set")
    env = harness_env(tmp_path)
    assert name not in env, (
        f"{name} reaches the browser harness. Playwright's git-info plugin keys off "
        "these names, not off CI, which is why setting CI to the empty string did not "
        "disable it."
    )


def test_the_harness_environment_still_carries_what_the_specs_need(
    tmp_path: Path,
) -> None:
    """The scrub must not take the pages with it."""
    build = tmp_path / "pages"
    env = harness_env(build)
    assert env["PERIMETER_SITE_DIR"] == str(build)
    assert env["CI"] == ""
    assert "PATH" in env, "the scrub removed the inherited environment wholesale"
