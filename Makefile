PYTHON ?= python3.12
VENV ?= .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
CLI := $(VENV)/bin/latency-budget-analyzer

.PHONY: install test examples clean

install:
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PIP) install -e ".[dev]"

test:
	$(PY) -m pytest

examples:
	$(CLI) analyze examples/sequential.yaml > docs/results/sequential.txt
	$(CLI) analyze examples/parallel.yaml > docs/results/parallel.txt
	$(CLI) analyze examples/parallelization-opportunity.yaml > docs/results/parallelization-opportunity.txt || true

clean:
	rm -rf .pytest_cache src/*.egg-info *.egg-info
	find . -name '__pycache__' -type d -exec rm -rf {} +
