.PHONY: install test lint fmt demo serve

install:
	python3 -m pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check src tests
	ruff format --check src tests
	mypy

fmt:
	ruff check --fix src tests
	ruff format src tests

demo:
	python -m hcd demo --out docs/img/demo_glint.png --report docs/img/synthetic_metrics.json

serve:
	python -m hcd serve --host 127.0.0.1 --port 8080
