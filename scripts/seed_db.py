"""Seed the SQLite database with initial configuration data.

Usage (from project root, with package installed):
    .venv/bin/python scripts/seed_db.py
"""

from personal_finance.db import create_db_engine, get_db_path, initialize_database, load_config


def main() -> None:
    """Create the database schema and seed configuration data."""
    config = load_config()
    engine = create_db_engine()
    initialize_database(engine, config)
    print(f"Database ready at {get_db_path()}")


if __name__ == "__main__":
    main()
