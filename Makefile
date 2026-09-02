.PHONY: verify lock-check sync lint format typecheck test audit site site-offline \
        site-check acquire pages node-sync htmlvalidate a11y node-audit determinism \
        browser-sync a11y-browser browser-audit

# CI / `make verify` body: the two MUST stay byte-for-byte identical.
# See CONTRIBUTING.md and .github/workflows/ci.yml.
#
# node-sync and browser-sync run before test, not only as part of pages.
# tests/test_a11y_gate.py runs tools/a11y.mjs and tests/test_a11y_browser_gate.py runs
# the Playwright specs, both against pages that should fail them, which needs both
# toolchains present; without this they would skip, and a skipped gate test reads as a
# passing one. Make builds each target once per invocation, so pages naming them too
# costs nothing.
verify: lock-check sync node-sync browser-sync lint format typecheck test audit pages determinism

# The lockfile-drift gate. `uv sync --frozen` is NOT one: measured 2026-08-15 against a
# pyproject.toml this lockfile does not satisfy, `uv lock --check` exits 1,
# `uv sync --locked` exits 1, and `uv sync --frozen` exits 0 and installs the stale set.
# `--frozen` means "do not resolve", not "the lock is current". Worse, every target below
# runs `uv run`, which silently rewrites uv.lock, so a gate that checked drift with
# `--frozen` would go green and then repair the thing it was meant to be checking.
lock-check:
	uv lock --check

# `--locked`, not `--frozen`, for the same measured reason: `--locked` exits 1 on a lock
# that no longer satisfies pyproject.toml. `lock-check` already runs first in `verify`,
# but `make sync` is also a documented entry point on its own, and on its own `--frozen`
# had no gate in front of it.
sync:
	uv sync --locked

lint:
	uv run ruff check .

format:
	uv run ruff format --check .

typecheck:
	uv run mypy --strict src

test:
	uv run pytest -n auto --cov=src --cov-branch --cov-report=xml --cov-fail-under=90

audit:
	uv run pip-audit

# Build from locally acquired files. data/raw/ is never in git and never in CI.
site:
	uv run python -m perimeter.cli \
		--perimeters data/raw/frap_perimeters.json \
		--dins data/raw/dins_postfire.json \
		--out site

# Is the committed site/ what the current pipeline produces from CAL FIRE's files?
#
# tests/test_published_site_is_current.py decides everything about site/ that can be
# decided without those files: the chrome, the provenance tables, the quoted caveats, the
# three-state key, and the shape of both JSON artifacts. What it cannot decide is every
# count, because the fixtures hold ten records each. This target is the rest of it, and it
# needs data/raw/, so it does not run in CI and is not part of `make verify`. Run it after
# any change to render.py, artifacts.py, coverage.py or the field registry, before
# committing.
#
# It builds into build/site-current and never into site/. A gate that regenerates the
# artifact where the committed copy lives repairs the drift it exists to report and then
# has nothing to report. It refuses outright when the acquired files are absent, rather
# than comparing site/ against a build that could not happen: a check that could not run
# is not a check that passed.
site-check:
	@test -f data/raw/frap_perimeters.json || { \
	  echo "site-check: data/raw/frap_perimeters.json is missing. Acquire it (see PROVENANCE.md) and re-run; not checked is not checked." >&2; exit 2; }
	@test -f data/raw/dins_postfire.json || { \
	  echo "site-check: data/raw/dins_postfire.json is missing. Acquire it (see PROVENANCE.md) and re-run; not checked is not checked." >&2; exit 2; }
	rm -rf build/site-current
	uv run python -m perimeter.cli \
		--perimeters data/raw/frap_perimeters.json \
		--dins data/raw/dins_postfire.json \
		--out build/site-current
	diff -r site build/site-current
	@echo "site-check: site/ is byte-identical to a fresh build from data/raw/"

# The same pipeline over committed fixtures: runs anywhere, output flagged is_fixture.
site-offline:
	uv run python -m perimeter.cli --fixture \
		--perimeters fixtures/frap_perimeters.sample.json \
		--dins fixtures/dins_postfire.sample.json \
		--out build/site-offline

# The WCAG gate. Builds the pages from fixtures, then checks the markup four ways:
# html-validate for HTML conformance and the markup-level accessibility rules, axe-core
# in a headless DOM for the WCAG 2.0/2.1/2.2 A and AA rule sets, the same axe rule sets
# again in Chromium where nothing is undecidable, and WCAG 2.2 SC 1.4.10 Reflow at a
# 320x256 viewport, which no engine decides from a DOM alone. Structure and colour
# contrast are additionally checked in `test`, so `make verify` still has a floor if a
# toolchain is unavailable. What none of this can do is look at the pages; README.md
# names what still needs a person.
pages: site-offline node-sync htmlvalidate a11y node-audit browser-sync a11y-browser \
       browser-audit

node-sync:
	npm ci

htmlvalidate:
	npx html-validate "build/site-offline/*.html"

a11y:
	node tools/a11y.mjs build/site-offline

node-audit:
	npm audit --audit-level=high

# The browser half of the WCAG gate. Chromium reads the built pages off disk as
# file:// URLs: nothing is served, no port is opened, and CI reaches the network only to
# fetch the browser. `--with-deps` is a no-op on macOS and installs the shared libraries
# the browser needs on a Linux runner, so the same line works in both places.
#
# This exists because jsdom cannot decide four of the rules it runs. tools/a11y.mjs
# declares them rather than passing them, which is honest and is still a gap; a real
# engine decides all four, so this run declares nothing undecidable and fails on any
# undecided rule. It found one thing the jsdom run could not: the scroll containers
# holding the wide tables were not keyboard reachable, which is a serious WCAG 2.1.1
# failure that no amount of DOM inspection reveals, because it depends on the container
# actually scrolling.
browser-sync:
	cd tools/a11y_browser && npm ci
	cd tools/a11y_browser && npx playwright install --with-deps chromium

a11y-browser:
	cd tools/a11y_browser && npx playwright test

# The browser harness is a second dependency tree, so it gets the same SCA the first one
# gets. A gate's own toolchain is not exempt from the check the gate exists to apply.
browser-audit:
	cd tools/a11y_browser && npm audit --audit-level=high

# The determinism gate behind the "byte-identical output" claim in README.md. Two builds
# into two directories, compared by tools/determinism.sh, which refuses an empty or
# missing tree instead of calling it a match. tests/test_determinism_gate.py runs the
# script against trees that should fail it, so this gate is known to be able to fail.
determinism:
	rm -rf build/run-one build/run-two
	uv run python -m perimeter.cli --fixture \
		--perimeters fixtures/frap_perimeters.sample.json \
		--dins fixtures/dins_postfire.sample.json \
		--out build/run-one
	uv run python -m perimeter.cli --fixture \
		--perimeters fixtures/frap_perimeters.sample.json \
		--dins fixtures/dins_postfire.sample.json \
		--out build/run-two
	tools/determinism.sh build/run-one build/run-two

# Network. Run by hand, never from a build. See PROVENANCE.md.
acquire:
	uv run python -m perimeter.acquire --out data/raw
