from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.exceptions import ValidationError


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
        from src.validators import validate_email, validate_job_title, validate_name, validate_salary

        try:
            self.first_name = validate_name(self.first_name, "First name")
            self.last_name = validate_name(self.last_name, "Last name")
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        try:
            self.email = validate_email(self.email)
            self.job_title = validate_job_title(self.job_title)
            self.salary = validate_salary(float(self.salary))
        except (TypeError, ValueError) as exc:
            raise ValidationError(str(exc)) from exc
        if not isinstance(self.department_id, int) or isinstance(self.department_id, bool) or self.department_id < 1:
            raise ValidationError("Department and salary must be valid positive values.")


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
        from src.validators import validate_project_name, validate_project_status, validate_project_budget_change

        try:
            self.project_name = validate_project_name(self.project_name)
            validate_project_status(self.status)
            validate_project_budget_change(0, float(self.budget))
        except (TypeError, ValueError) as exc:
            raise ValidationError(str(exc)) from exc
        if not isinstance(self.department_id, int) or isinstance(self.department_id, bool) or self.department_id < 1:
            raise ValidationError("Department must be positive and budget cannot be negative.")


@dataclass
class Review:
    employee_id: int
    review_date: date
    overall_score: float
    rating: str
    comments: str = ""
    manager_id: int | None = None

    def validate(self) -> None:
        from src.validators import validate_comment, validate_rating, validate_score

        if not isinstance(self.employee_id, int) or isinstance(self.employee_id, bool) or self.employee_id < 1:
            raise ValidationError("Employee ID is required.")
        try:
            validate_score(float(self.overall_score))
            validate_rating(self.rating)
            validate_comment(self.comments)
        except (TypeError, ValueError) as exc:
            raise ValidationError(str(exc)) from exc

