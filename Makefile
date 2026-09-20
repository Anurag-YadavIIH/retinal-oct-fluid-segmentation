.PHONY: install lint format test test-fast pacs-up pacs-down clean

install:
	python -m pip install --upgrade pip
	pip install -e ".[dev]"
	pre-commit install

lint:
	ruff check src tests scripts
	ruff format --check src tests scripts

format:
	ruff format src tests scripts
	ruff check --fix src tests scripts

# Excludes the tests that cannot run without a PACS or the RETOUCH data. A target that
# fails by design teaches people to ignore failures, so `test` means "everything that
# can run here" and matches what CI runs.
test:
	pytest -m "not requires_data and not requires_pacs"

test-fast:
	pytest -m "not slow and not requires_data and not requires_pacs"

# Needs a running Orthanc: `make pacs-up` first. As of 2026-09-20 these tests
# (TC-080..TC-082) have never been executed — see docs/07 section 6.9.
test-pacs:
	pytest -m "requires_pacs"

pacs-up:
	docker compose -f docker/docker-compose.yml up -d orthanc

pacs-down:
	docker compose -f docker/docker-compose.yml down

clean:
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov build dist
	find . -type d -name __pycache__ -exec rm -rf {} +
