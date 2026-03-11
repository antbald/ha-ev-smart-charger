.PHONY: test

PYTHON ?= ./.venv/bin/python

test:
	@test -x "$(PYTHON)" || (echo "Missing $(PYTHON). Create .venv and install requirements_test.txt first." >&2; exit 1)
	$(PYTHON) -m pytest -q
