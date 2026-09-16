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

test:
	pytest

test-fast:
	pytest -m "not slow and not requires_data and not requires_pacs"

pacs-up:
	docker compose -f docker/docker-compose.yml up -d orthanc

pacs-down:
	docker compose -f docker/docker-compose.yml down

clean:
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov build dist
	find . -type d -name __pycache__ -exec rm -rf {} +
