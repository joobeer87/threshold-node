.PHONY: install test check console-install console-check check-all run

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

console-install:
	cd console && npm ci --no-audit --no-fund

console-check:
	cd console && npm test
	cd console && npm run build

check-all: check console-check

run:
	$(PYTHON) -m threshold
