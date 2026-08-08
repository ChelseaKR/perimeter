.PHONY: verify sync lint format typecheck test audit site site-offline acquire \
        pages node-sync htmlvalidate a11y node-audit

# CI / `make verify` body: the two MUST stay byte-for-byte identical.
# See CONTRIBUTING.md and .github/workflows/ci.yml.
verify: sync lint format typecheck test audit pages

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

# Network. Run by hand, never from a build. See PROVENANCE.md.
acquire:
	uv run python -m perimeter.acquire --out data/raw
