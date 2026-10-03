from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from src.ETL.extractor import CSVExtractor
from src.ETL.transformer import DataTransformer
from src.database.db_manager import DatabaseConnection


class DataWarehouseLoader(DatabaseConnection):
	"""Load synthesized employee snapshots and SCD2 versions into MySQL."""

	batch_size = 1_000

	def load_synthesized_data(
		self,
		employee_path: str | Path,
		history_path: str | Path,
		review_path: str | Path | None = None,
	) -> None:
		extractor = CSVExtractor()
		employees = extractor.extract(employee_path)
		raw_history = extractor.extract(history_path)
		versions = DataTransformer.build_employee_history(employees, raw_history)
		connection = self.get_connection()
		try:
			self._load_departments(connection, employees["department_name"].unique())
			self._load_oltp_employees(connection, employees)
			if review_path is not None:
				reviews = extractor.extract(review_path)
				self._load_oltp_reviews(connection, reviews)
			self._load_employee_versions(connection, versions)
			connection.commit()
		except Exception:
			connection.rollback()
			raise
		if review_path is not None:
			self.load_review_facts()

	def _load_oltp_reviews(self, connection, reviews: pd.DataFrame) -> None:
		cursor = connection.cursor()
		query = """
			INSERT INTO performance_reviews (review_id, employee_id, review_date, overall_score, rating, comments)
			VALUES (%s, %s, %s, %s, %s, %s)
			ON DUPLICATE KEY UPDATE review_date = VALUES(review_date),
			                        overall_score = VALUES(overall_score),
			                        rating = VALUES(rating), comments = VALUES(comments)
		"""
		for start in range(0, len(reviews), self.batch_size):
			batch = reviews.iloc[start : start + self.batch_size]
			cursor.executemany(query, [
				(
					int(row.review_id), int(row.employee_id), row.review_date.date(),
					float(row.overall_score), row.rating, row.comments,
				)
				for row in batch.itertuples(index=False)
			])
		cursor.close()

	def _load_departments(self, connection, department_names: Iterable[str]) -> None:
		cursor = connection.cursor()
		cursor.executemany(
			"INSERT INTO departments (department_name) VALUES (%s) "
			"ON DUPLICATE KEY UPDATE department_name = VALUES(department_name)",
			[(name,) for name in department_names],
		)
		cursor.execute("SELECT department_id, department_name FROM departments")
		self._department_ids = {name: department_id for department_id, name in cursor.fetchall()}
		cursor.executemany(
			"INSERT INTO dim_department (department_id, department_name) VALUES (%s, %s) "
			"ON DUPLICATE KEY UPDATE department_name = VALUES(department_name)",
			[(department_id, name) for name, department_id in self._department_ids.items()],
		)
		cursor.execute("SELECT department_key, department_id FROM dim_department")
		self._department_keys = {department_id: department_key for department_key, department_id in cursor.fetchall()}
		cursor.close()

	def _load_oltp_employees(self, connection, employees: pd.DataFrame) -> None:
		cursor = connection.cursor()
		query = """
			INSERT INTO employees (
				employee_id, first_name, last_name, email, department_id,
				job_title, hire_date, salary, performance_score, attrition_risk, status
			) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active')
			ON DUPLICATE KEY UPDATE
				first_name = VALUES(first_name), last_name = VALUES(last_name),
				email = VALUES(email), department_id = VALUES(department_id),
				job_title = VALUES(job_title), salary = VALUES(salary),
				performance_score = VALUES(performance_score), attrition_risk = VALUES(attrition_risk)
		"""
		for start in range(0, len(employees), self.batch_size):
			batch = employees.iloc[start : start + self.batch_size]
			cursor.executemany(query, [
				(
					int(row.employee_id), row.first_name, row.last_name, row.email,
					self._department_ids[row.department_name], row.job_title,
					row.hire_date.date(), float(row.salary), int(row.performance_score),
					int(row.attrition_risk),
				)
				for row in batch.itertuples(index=False)
			])
		cursor.close()

	def load_review_facts(self) -> None:
		connection = self.get_connection()
		cursor = connection.cursor()
		try:
			cursor.execute("""
				INSERT INTO dim_date (date_key, full_date, year_num, quarter_num, month_num, day_num)
				SELECT DISTINCT YEAR(review_date) * 10000 + MONTH(review_date) * 100 + DAY(review_date),
				       review_date, YEAR(review_date), QUARTER(review_date),
				       MONTH(review_date), DAY(review_date)
				FROM performance_reviews
				ON DUPLICATE KEY UPDATE full_date = VALUES(full_date)
			""")
			cursor.execute("""
				INSERT INTO dim_project (project_id, project_name, department_key)
				SELECT p.project_id, p.project_name, d.department_key
				FROM projects p
				JOIN departments source_department ON source_department.department_id = p.department_id
				JOIN dim_department d ON d.department_id = source_department.department_id
				ON DUPLICATE KEY UPDATE project_name = VALUES(project_name),
				                        department_key = VALUES(department_key)
			""")
			cursor.execute("""
				INSERT INTO fact_performance_reviews (
					review_id, employee_key, employee_id, department_key, project_key,
					date_key, review_date, overall_score, rating
				)
				WITH ranked_assignments AS (
					SELECT pr.review_id, pa.project_id,
					       ROW_NUMBER() OVER (
					           PARTITION BY pr.review_id ORDER BY pa.assigned_date DESC, pa.assignment_id DESC
					       ) AS assignment_rank
					FROM performance_reviews pr
					LEFT JOIN project_assignments pa
					  ON pa.employee_id = pr.employee_id AND pa.assigned_date <= pr.review_date
				)
				SELECT pr.review_id, e.employee_key, pr.employee_id, e.department_key,
				       dp.project_key,
				       YEAR(pr.review_date) * 10000 + MONTH(pr.review_date) * 100 + DAY(pr.review_date),
				       pr.review_date, pr.overall_score, pr.rating
				FROM performance_reviews pr
				JOIN dim_employee e
				  ON e.employee_id = pr.employee_id
				 AND pr.review_date >= e.start_date
				 AND (e.end_date IS NULL OR pr.review_date < e.end_date)
				LEFT JOIN ranked_assignments ra
				  ON ra.review_id = pr.review_id AND ra.assignment_rank = 1
				LEFT JOIN dim_project dp ON dp.project_id = ra.project_id
				ON DUPLICATE KEY UPDATE employee_key = VALUES(employee_key),
				                        department_key = VALUES(department_key),
				                        project_key = VALUES(project_key),
				                        overall_score = VALUES(overall_score), rating = VALUES(rating)
			""")
			connection.commit()
		except Exception:
			connection.rollback()
			raise
		finally:
			cursor.close()

	def _load_employee_versions(self, connection, versions: pd.DataFrame) -> None:
		cursor = connection.cursor()
		query = """
			INSERT INTO dim_employee (
				employee_id, first_name, last_name, email, department_key,
				job_title, hire_date, salary, performance_score, attrition_risk,
				start_date, end_date, is_current
			) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
			ON DUPLICATE KEY UPDATE
				first_name = VALUES(first_name), last_name = VALUES(last_name),
				department_key = VALUES(department_key), job_title = VALUES(job_title),
				salary = VALUES(salary), performance_score = VALUES(performance_score),
				attrition_risk = VALUES(attrition_risk), end_date = VALUES(end_date),
				is_current = VALUES(is_current)
		"""
		for start in range(0, len(versions), self.batch_size):
			batch = versions.iloc[start : start + self.batch_size]
			cursor.executemany(query, [
				(
					int(row.employee_id), row.first_name, row.last_name, row.email,
					self._department_keys[self._department_ids[row.department_name]], row.job_title,
					row.hire_date.date(), float(row.salary), int(row.performance_score),
					int(row.attrition_risk), row.start_date.date(),
					row.end_date.date() if pd.notna(row.end_date) else None,
					bool(row.is_current),
				)
				for row in batch.itertuples(index=False)
			])
		cursor.close()
