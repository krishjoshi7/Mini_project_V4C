from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker


DEPARTMENTS = (
	"Engineering",
	"Sales",
	"Human Resources",
	"Finance",
	"Marketing",
	"Operations",
	"Supply Chain",
	"Customer Success",
)

ROLES = {
	"Engineering": ("Software Engineer", "Data Engineer", "Engineering Manager"),
	"Sales": ("Account Executive", "Sales Manager", "Business Development Rep"),
	"Human Resources": ("HR Generalist", "HR Manager", "Talent Partner"),
	"Finance": ("Financial Analyst", "Finance Manager", "Controller"),
	"Marketing": ("Marketing Analyst", "Brand Manager", "Growth Manager"),
	"Operations": ("Operations Analyst", "Operations Manager", "Project Coordinator"),
	"Supply Chain": ("Supply Planner", "Logistics Manager", "Procurement Analyst"),
	"Customer Success": ("Customer Success Manager", "Support Engineer", "Account Manager"),
}

SALARY_BANDS = {
	"Engineering": 96_000,
	"Sales": 82_000,
	"Human Resources": 74_000,
	"Finance": 88_000,
	"Marketing": 79_000,
	"Operations": 73_000,
	"Supply Chain": 76_000,
	"Customer Success": 77_000,
}


class DataSynthesizer:
	"""Create reproducible employee snapshots and SCD Type 2 versions."""

	def __init__(
		self,
		rows: int = 100_000,
		historical_fraction: float = 0.30,
		seed: int = 42,
	) -> None:
		if rows < 1:
			raise ValueError("rows must be greater than zero")
		if not 0 <= historical_fraction <= 1:
			raise ValueError("historical_fraction must be between 0 and 1")
		self.rows = rows
		self.historical_fraction = historical_fraction
		self.seed = seed

	def generate_base_employee_data(self) -> pd.DataFrame:
		rng = np.random.default_rng(self.seed)
		fake = Faker()
		fake.seed_instance(self.seed)
		today = pd.Timestamp.today().normalize()
		departments = rng.choice(DEPARTMENTS, size=self.rows)
		hire_dates = today - pd.to_timedelta(rng.integers(180, 3650, self.rows), unit="D")
		employees = pd.DataFrame(
			{
				"employee_id": np.arange(1, self.rows + 1, dtype=np.int64),
				"first_name": [fake.first_name() for _ in range(self.rows)],
				"last_name": [fake.last_name() for _ in range(self.rows)],
				"email": [f"employee{employee_id}@example.com" for employee_id in range(1, self.rows + 1)],
				"department_name": departments,
				"job_title": [rng.choice(ROLES[department]) for department in departments],
				"hire_date": hire_dates,
				"salary": [
					round(SALARY_BANDS[department] + int(rng.integers(-15_000, 25_001)), 2)
					for department in departments
				],
				"performance_score": rng.integers(55, 100, self.rows),
				"attrition_risk": rng.integers(0, 100, self.rows),
			}
		)
		employees["manager_id"] = rng.integers(1, max(2, self.rows // 50), self.rows)
		return employees

	def generate_scd_type_2_history(self, employees: pd.DataFrame) -> pd.DataFrame:
		rng = np.random.default_rng(self.seed + 1)
		today = pd.Timestamp.today().normalize()
		historical_count = int(len(employees) * self.historical_fraction)
		changed_ids = set(
			rng.choice(employees["employee_id"].to_numpy(), size=historical_count, replace=False).tolist()
		)
		history = employees[
			[
				"employee_id", "department_name", "job_title", "salary", "hire_date",
				"performance_score", "attrition_risk",
			]
		].copy()
		history["start_date"] = history["hire_date"]
		history["end_date"] = pd.NaT
		history["is_current"] = True

		if changed_ids:
			changed = history[history["employee_id"].isin(changed_ids)].copy()
			earliest_changes = np.maximum(
				changed["hire_date"].to_numpy(dtype="datetime64[ns]")
				+ np.timedelta64(30, "D"),
				(today - pd.Timedelta(days=730)).to_datetime64(),
			)
			latest_change = (today - pd.Timedelta(days=30)).to_datetime64()
			available_days = (latest_change - earliest_changes).astype("timedelta64[D]").astype(int)
			change_dates = pd.to_datetime(
				earliest_changes
				+ rng.integers(0, available_days + 1, len(changed)).astype("timedelta64[D]")
			)
			changed["end_date"] = change_dates
			changed["is_current"] = False
			changed["salary"] = (changed["salary"] * rng.uniform(0.84, 0.96, len(changed))).round(2)
			changed["department_name"] = [
				rng.choice([department for department in DEPARTMENTS if department != current])
				for current in changed["department_name"]
			]
			changed["job_title"] = [rng.choice(ROLES[department]) for department in changed["department_name"]]

			current_mask = history["employee_id"].isin(changed_ids)
			history.loc[current_mask, "start_date"] = change_dates.to_numpy()
			history = pd.concat([history, changed], ignore_index=True)

		history = history.drop(columns="hire_date")
		return history.sort_values(["employee_id", "start_date"]).reset_index(drop=True)

	def generate_performance_reviews(self, employees: pd.DataFrame) -> pd.DataFrame:
		rng = np.random.default_rng(self.seed + 2)
		today = pd.Timestamp.today().normalize()
		earliest_dates = np.maximum(
			employees["hire_date"].to_numpy(dtype="datetime64[ns]"),
			(today - pd.DateOffset(years=3)).to_datetime64(),
		)
		available_days = (today.to_datetime64() - earliest_dates).astype("timedelta64[D]").astype(int)
		review_dates = pd.to_datetime(
			earliest_dates + rng.integers(0, available_days + 1).astype("timedelta64[D]")
		)
		scores = np.clip(
			employees["performance_score"].to_numpy() + rng.normal(0, 8, len(employees)),
			45,
			100,
		).round(2)
		ratings = np.select(
			[scores >= 90, scores >= 80, scores >= 70],
			["Exceeds Expectations", "Strong", "Meets Expectations"],
			default="Needs Improvement",
		)
		return pd.DataFrame(
			{
				"review_id": np.arange(1, len(employees) + 1, dtype=np.int64),
				"employee_id": employees["employee_id"].to_numpy(),
				"review_date": review_dates,
				"overall_score": scores,
				"rating": ratings,
				"comments": "Synthetic annual performance review",
			}
		)

	def export_to_csv(self, output_dir: str | Path | None = None) -> dict[str, Path]:
		destination = Path(output_dir) if output_dir else Path(__file__).resolve().parents[1] / "data"
		destination.mkdir(parents=True, exist_ok=True)
		employees = self.generate_base_employee_data()
		history = self.generate_scd_type_2_history(employees)
		reviews = self.generate_performance_reviews(employees)
		employee_path = destination / "synthetic_employees.csv"
		history_path = destination / "employee_scd2_history.csv"
		review_path = destination / "synthetic_performance_reviews.csv"
		employees.to_csv(employee_path, index=False, date_format="%Y-%m-%d")
		history.to_csv(history_path, index=False, date_format="%Y-%m-%d")
		reviews.to_csv(review_path, index=False, date_format="%Y-%m-%d")
		return {"employees": employee_path, "history": history_path, "reviews": review_path}


def main() -> None:
	parser = argparse.ArgumentParser(description="Generate employee snapshot and SCD2 history CSV files")
	parser.add_argument("--rows", type=int, default=100_000)
	parser.add_argument("--historical-fraction", type=float, default=0.30)
	parser.add_argument("--seed", type=int, default=42)
	parser.add_argument("--output-dir", type=Path, default=None)
	args = parser.parse_args()
	paths = DataSynthesizer(args.rows, args.historical_fraction, args.seed).export_to_csv(args.output_dir)
	for label, path in paths.items():
		print(f"{label}: {path}")


if __name__ == "__main__":
	main()
