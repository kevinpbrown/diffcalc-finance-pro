#!/bin/sh

rm -f ~/.local/share/diffcalc-finance-pro/personal_finance.db

# seed_sample_data.py runs initialize_database itself, so it covers seed_db.py too.
.venv/bin/python scripts/seed_sample_data.py
