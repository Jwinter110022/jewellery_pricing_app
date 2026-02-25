"""
Initialises the local SQLite database and ensures default settings exist.
Run this once before first use, or anytime to repair missing tables.
"""

from src.db import get_connection, init_db


def main() -> None:
    conn = get_connection()
    init_db(conn)
    print("Database initialised successfully.")


if __name__ == "__main__":
    main()
