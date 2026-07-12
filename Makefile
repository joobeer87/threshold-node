.PHONY: install test check run

BOOTSTRAP_PYTHON ?= python3
PYTHON ?= .venv/bin/python

install:
	$(BOOTSTRAP_PYTHON) -m venv .venv
	.venv/bin/python -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest tests/ -q

check:
	$(PYTHON) -m compileall -q src scripts tests
	PYTHONPATH=src $(PYTHON) -m pytest tests/ -q
	$(PYTHON) scripts/public_release_check.py .

run:
	$(PYTHON) -m threshold
