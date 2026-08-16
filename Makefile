.PHONY: verify lock-check sync lint format typecheck test audit site site-offline \
        acquire pages node-sync htmlvalidate a11y node-audit determinism

# CI / `make verify` body: the two MUST stay byte-for-byte identical.
# See CONTRIBUTING.md and .github/workflows/ci.yml.
verify: lock-check sync lint format typecheck test audit pages determinism

# The lockfile-drift gate. `uv sync --frozen` is NOT one: measured 2026-08-15 against a
# pyproject.toml this lockfile does not satisfy, `uv lock --check` exits 1,
# `uv sync --locked` exits 1, and `uv sync --frozen` exits 0 and installs the stale set.
# `--frozen` means "do not resolve", not "the lock is current". Worse, every target below
# runs `uv run`, which silently rewrites uv.lock, so a gate that checked drift with
# `--frozen` would go green and then repair the thing it was meant to be checking.
lock-check:
	uv lock --check

sync:
	uv sync --frozen

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

# The same pipeline over committed fixtures: runs anywhere, output flagged is_fixture.
site-offline:
	uv run python -m perimeter.cli --fixture \
		--perimeters fixtures/frap_perimeters.sample.json \
		--dins fixtures/dins_postfire.sample.json \
		--out build/site-offline

# The WCAG gate. Builds the pages from fixtures, then checks the markup two ways:
# html-validate for HTML conformance and the markup-level accessibility rules, and
# axe-core in a headless DOM for the WCAG 2.0/2.1/2.2 A and AA rule sets. Structure and
# colour contrast are additionally checked in `test`, so `make verify` still has a floor
# if the node toolchain is unavailable. What none of this can do is look at the pages;
# README.md names what still needs a person.
pages: site-offline node-sync htmlvalidate a11y node-audit

node-sync:
	npm ci

htmlvalidate:
	npx html-validate "build/site-offline/*.html"

a11y:
	node tools/a11y.mjs build/site-offline

node-audit:
	npm audit --audit-level=high

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
