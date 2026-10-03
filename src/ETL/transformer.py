from __future__ import annotations

import pandas as pd


class DataTransformer:
	"""Validate source history and attach employee attributes to SCD rows."""

	@staticmethod
	def build_employee_history(employees: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
		identity_columns = [
			"employee_id", "first_name", "last_name", "email", "hire_date",
			"performance_score", "attrition_risk",
		]
		versions = history.merge(
			employees[identity_columns],
			on="employee_id",
			how="left",
			validate="many_to_one",
		)
		if versions["first_name"].isna().any():
			raise ValueError("SCD history contains employee IDs missing from the employee snapshot")
		versions["is_current"] = versions["is_current"].astype(bool)
		if versions.groupby("employee_id")["is_current"].sum().ne(1).any():
			raise ValueError("Each employee must have exactly one current SCD2 version")
		if (versions["end_date"].notna() & (versions["end_date"] <= versions["start_date"])).any():
			raise ValueError("SCD2 end_date must be later than start_date")
		return versions
