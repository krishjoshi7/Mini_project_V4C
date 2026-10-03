from __future__ import annotations

import argparse
from pathlib import Path

from src.ETL.loader import DataWarehouseLoader


DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"


def main() -> None:
    parser = argparse.ArgumentParser(description="Load employee and review CSVs into MySQL OLTP and warehouse schemas")
    parser.add_argument("--employees", type=Path, default=DEFAULT_DATA_DIR / "synthetic_employees.csv")
    parser.add_argument("--history", type=Path, default=DEFAULT_DATA_DIR / "employee_scd2_history.csv")
    parser.add_argument("--reviews", type=Path, default=DEFAULT_DATA_DIR / "synthetic_performance_reviews.csv")
    args = parser.parse_args()
    loader = DataWarehouseLoader()
    try:
        loader.load_synthesized_data(args.employees, args.history, args.reviews)
        print("Employee versions and performance review facts loaded successfully.")
    finally:
        loader.close()


if __name__ == "__main__":
    main()
