from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class Employee:
    first_name: str
    last_name: str
    email: str
    department_id: int
    job_title: str
    salary: float
    hire_date: date | None = None
    employee_id: int | None = None
    manager_id: int | None = None
    status: str = "active"

    def validate(self) -> None:
        if not self.first_name.strip() or not self.last_name.strip():
            raise ValueError("Employee name is required.")
        if "@" not in self.email:
            raise ValueError("Enter a valid email address.")
        if self.department_id < 1 or self.salary <= 0:
            raise ValueError("Department and salary must be valid positive values.")


@dataclass
class Project:
    project_name: str
    department_id: int
    budget: float
    start_date: date | None = None
    end_date: date | None = None
    project_id: int | None = None
    status: str = "active"

    def validate(self) -> None:
        if not self.project_name.strip():
            raise ValueError("Project name is required.")
        if self.department_id < 1 or self.budget < 0:
            raise ValueError("Department must be positive and budget cannot be negative.")


@dataclass
class Review:
    employee_id: int
    review_date: date
    overall_score: float
    rating: str
    comments: str = ""
    manager_id: int | None = None

    def validate(self) -> None:
        if self.employee_id < 1:
            raise ValueError("Employee ID is required.")
        if not 0 <= self.overall_score <= 100:
            raise ValueError("Review score must be between 0 and 100.")
