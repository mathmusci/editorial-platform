install:
	pip install -e ".[dev]"

lint:
	ruff check .

format:
	ruff format .

test:
	pytest

check: lint test

precommit:
	pre-commit run --all-files
