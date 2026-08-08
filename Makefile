.PHONY: verify sync lint format typecheck test audit site site-offline acquire

# CI / `make verify` body: the two MUST stay byte-for-byte identical.
# See CONTRIBUTING.md and .github/workflows/ci.yml.
verify: sync lint format typecheck test audit

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

# Network. Run by hand, never from a build. See PROVENANCE.md.
acquire:
	uv run python -m perimeter.acquire --out data/raw
