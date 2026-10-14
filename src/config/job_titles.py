"""
job_titles.py
─────────────
Department-specific job title catalog and department-level page rules.

Used by:
  - streamlit_app.py  → dynamic job title dropdown
  - rbac.py           → dept-aware page filtering for Department Managers
  - validators.py     → whitelist validation of submitted job titles
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Job title catalog — ordered senior → junior within each department
# ---------------------------------------------------------------------------
DEPT_JOB_TITLES: dict[str, list[str]] = {
    "Engineering": [
        "Engineering Director",
        "Software Engineer",
        "QA Engineer",
        "Junior Software Engineer",
    ],
    "Research & Development": [
        "R&D Director",
        "Research Scientist",
        "Research Analyst",
        "Lab Technician",
    ],
    "Sales": [
        "Sales Director",
        "Sales Manager",
        "Sales Executive",
        "Sales Development Representative",
    ],
    "Operations": [
        "Operations Director",
        "Operations Analyst",
        "Project Coordinator",
        "Logistics Coordinator",
    ],
    "Finance": [
        "Finance Director",
        "Financial Analyst",
        "Accountant",
        "Junior Financial Analyst",
    ],
    "Human Resources": [
        "HR Director",
        "HR Manager",
        "HR Business Partner",
        "HR Coordinator",
    ],
}

# Flat set of every valid job title (used for whitelist validation)
ALL_JOB_TITLES: frozenset[str] = frozenset(
    title for titles in DEPT_JOB_TITLES.values() for title in titles
)

# ---------------------------------------------------------------------------
# Department-level page access rules for the "Department Manager" role
# ---------------------------------------------------------------------------

# Operations and Finance Department Managers can access Project Management.
# Finance Manager: full edit (create/assign/budget). Finance Analyst: view only.
# Engineering and R&D managers do not get this page.
PROJECT_MGMT_DEPTS: frozenset[str] = frozenset({
    "Operations",
    "Finance",
})

# Only HR and Finance Department Managers can access Employee Management.
EMPLOYEE_MGMT_DEPTS: frozenset[str] = frozenset({
    "Human Resources",
    "Finance",
})
