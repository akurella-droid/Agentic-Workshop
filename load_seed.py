"""Load seed data from CSV files into app.db."""

import csv
import sqlite3
from pathlib import Path


def load_seed():
    """Load customers and tickets from seed CSVs into app.db."""
    db_path = Path(__file__).resolve().parent / "app.db"
    seed_dir = Path(__file__).resolve().parent / "seed"

    # Create database connection
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create customers table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            plan TEXT NOT NULL,
            open_tickets INTEGER NOT NULL
        )
    """)

    # Create tickets table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            text TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        )
    """)

    # Load customers
    customers_path = seed_dir / "customers.csv"
    if customers_path.exists():
        try:
            with open(customers_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row_num, row in enumerate(reader, start=2):  # start=2 because row 1 is header
                    try:
                        required_cols = {"customer_id", "name", "plan", "open_tickets"}
                        missing = required_cols - set(row.keys())
                        if missing:
                            raise ValueError(f"Missing columns in customers.csv: {', '.join(missing)}")
                        cursor.execute(
                            """
                            INSERT OR REPLACE INTO customers
                            (customer_id, name, plan, open_tickets)
                            VALUES (?, ?, ?, ?)
                            """,
                            (row["customer_id"], row["name"], row["plan"], int(row["open_tickets"]))
                        )
                    except ValueError as e:
                        print(f"Error loading row {row_num} from customers.csv: {e}", file=__import__('sys').stderr)
                        raise
        except FileNotFoundError:
            print(f"Warning: {customers_path} not found", file=__import__('sys').stderr)
    else:
        print(f"Warning: {customers_path} not found", file=__import__('sys').stderr)

    # Load tickets
    tickets_path = seed_dir / "tickets.csv"
    if tickets_path.exists():
        try:
            with open(tickets_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row_num, row in enumerate(reader, start=2):  # start=2 because row 1 is header
                    try:
                        required_cols = {"ticket_id", "customer_id", "created_at", "text"}
                        missing = required_cols - set(row.keys())
                        if missing:
                            raise ValueError(f"Missing columns in tickets.csv: {', '.join(missing)}")
                        cursor.execute(
                            """
                            INSERT OR REPLACE INTO tickets
                            (ticket_id, customer_id, created_at, text)
                            VALUES (?, ?, ?, ?)
                            """,
                            (row["ticket_id"], row["customer_id"], row["created_at"], row["text"])
                        )
                    except ValueError as e:
                        print(f"Error loading row {row_num} from tickets.csv: {e}", file=__import__('sys').stderr)
                        raise
        except FileNotFoundError:
            print(f"Warning: {tickets_path} not found", file=__import__('sys').stderr)
    else:
        print(f"Warning: {tickets_path} not found", file=__import__('sys').stderr)

    conn.commit()
    conn.close()
    print(f"Seed data loaded into {db_path}")


if __name__ == "__main__":
    load_seed()
