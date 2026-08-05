#!/usr/bin/env bash
# Charter compliance check — see specs/canonical/technical-charter.md.
#
# Runs the same four gates required before a vertical slice can be marked
# closed: format, lint, strict type-checking, and tests with coverage.
# Used by githooks/pre-commit and safe to run manually at any time:
#   ./scripts/check.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "== ruff format --check =="
.venv/bin/ruff format --check src tests

echo "== ruff check =="
.venv/bin/ruff check src tests

echo "== mypy --strict =="
.venv/bin/mypy src

echo "== pytest (with coverage) =="
.venv/bin/pytest -q

echo "All charter checks passed."
