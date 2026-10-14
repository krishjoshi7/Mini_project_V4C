from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.validators import (
    validate_comment,
    validate_email,
    validate_job_title,
    validate_name,
    validate_rating,
    validate_salary,
    validate_score,
    validate_project_name,
    validate_project_status,
)


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
        self.first_name = validate_name(self.first_name, "First name")
        self.last_name  = validate_name(self.last_name,  "Last name")
        self.email      = validate_email(self.email)
        self.job_title  = validate_job_title(self.job_title)
        self.salary     = validate_salary(self.salary)
        if self.department_id < 1:
            raise ValueError("Department must be a valid positive ID.")


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
        self.project_name = validate_project_name(self.project_name)
        self.status       = validate_project_status(self.status)
        if self.department_id < 1:
            raise ValueError("Department must be a valid positive ID.")
        if self.budget < 0:
            raise ValueError("Budget cannot be negative.")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("End date cannot be before start date.")


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
            raise ValueError("Employee ID must be a positive integer.")
        self.overall_score = validate_score(self.overall_score)
        self.rating        = validate_rating(self.rating)
        self.comments      = validate_comment(self.comments)
