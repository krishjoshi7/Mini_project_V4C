"""Role-Based Access Control — role resolution and permission registry."""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Role hierarchy (ordered from most to least privileged)
# ---------------------------------------------------------------------------
ALL_ROLES: list[str] = [
    "Super Admin",
    "HR Admin",
    "Department Manager",
    "Analyst",
    "Employee",
]

# ---------------------------------------------------------------------------
# Page visibility per role
# ---------------------------------------------------------------------------
# For "Department Manager", allowed_pages() applies a second dept-level filter
# (see _dept_pages_for_manager below). The entry here acts as the ceiling —
# a dept manager can never see MORE than what this list allows.
PAGE_PERMISSIONS: dict[str, list[str]] = {
    "Overview":             ["Super Admin", "HR Admin", "Department Manager", "Analyst", "Employee"],
    "Employee Management":  ["Super Admin", "HR Admin", "Department Manager"],
    "Project Management":   ["Super Admin", "Department Manager", "Analyst"],
    "Performance Reviews":  ["Super Admin", "HR Admin", "Department Manager", "Employee"],
    "Analytics Dashboard":  ["Super Admin", "HR Admin", "Department Manager", "Analyst"],
}

# ---------------------------------------------------------------------------
# Action-level permissions
# ---------------------------------------------------------------------------
# Fine-grained capabilities checked inside individual render functions.
ACTION_PERMISSIONS: dict[str, list[str]] = {
    # Employee Management
    "employee.create":       ["Super Admin", "HR Admin", "Department Manager"],
    "employee.deactivate":   ["Super Admin", "HR Admin"],
    "employee.update":       ["Super Admin", "HR Admin", "Department Manager"],
    # Project Management
    "project.create":        ["Super Admin", "Department Manager"],
    "project.delete":        ["Super Admin"],
    "project.assign":        ["Super Admin", "Department Manager"],
    # Reviews
    "review.create":         ["Super Admin", "HR Admin", "Department Manager"],
    "review.delete":         ["Super Admin", "HR Admin"],
    "review.update":         ["Super Admin", "HR Admin", "Department Manager"],
    # Analytics
    "analytics.view_salary": ["Super Admin", "HR Admin"],
    "analytics.all_depts":   ["Super Admin", "HR Admin", "Analyst"],
}


# ---------------------------------------------------------------------------
# Department-level page filter for Department Managers
# ---------------------------------------------------------------------------

def _dept_pages_for_manager(department_name: str | None) -> set[str]:
    """
    Return the set of page names a Department Manager may access based on
    their specific department.

    Always granted:
        Overview, Performance Reviews, Analytics Dashboard

    Conditional:
        Employee Management  — HR and Finance only
        Project Management   — Operations and Finance only
    """
    from src.config.job_titles import EMPLOYEE_MGMT_DEPTS, PROJECT_MGMT_DEPTS

    pages: set[str] = {"Overview", "Performance Reviews", "Analytics Dashboard"}

    if department_name in EMPLOYEE_MGMT_DEPTS:
        pages.add("Employee Management")

    if department_name in PROJECT_MGMT_DEPTS:
        pages.add("Project Management")

    return pages


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def can(role: str, action: str) -> bool:
    """Return True if *role* is permitted to perform *action*."""
    return role in ACTION_PERMISSIONS.get(action, [])


def can_manage_projects(auth: dict) -> bool:
    """
    Return True if the logged-in user may create, edit, or assign projects.

    Rules:
        Super Admin            → always yes
        Department Manager     → only if their department is in PROJECT_MGMT_DEPTS
                                 (currently: Operations + Finance)
        Analyst (Finance dept) → view-only — this function returns False so the
                                 UI shows a read-only view; page access is granted
                                 separately via PAGE_PERMISSIONS.
        All other roles        → no
    """
    from src.config.job_titles import PROJECT_MGMT_DEPTS
    role = auth.get("role")
    if role == "Super Admin":
        return True
    if role == "Department Manager":
        return auth.get("department_name") in PROJECT_MGMT_DEPTS
    return False


def can_edit_salary(auth: dict) -> bool:
    """
    Return True if the user may update an employee's salary.

    Rules:
        Super Admin          → yes
        HR Admin             → yes
        Finance Dept Manager → yes (salary is their domain)
        All others           → no
    """
    role = auth.get("role")
    if role in ("Super Admin", "HR Admin"):
        return True
    if role == "Department Manager" and auth.get("department_name") == "Finance":
        return True
    return False


def can_edit_dept_and_role(auth: dict) -> bool:
    """
    Return True if the user may change an employee's department or job title.

    Rules:
        Super Admin → yes
        HR Admin    → yes  (HR owns org structure changes)
        All others  → no
    """
    return auth.get("role") in ("Super Admin", "HR Admin")


def allowed_pages(role: str, department_name: str | None = None) -> list[str]:
    """
    Return the ordered list of page names visible to *role*.

    For 'Department Manager', a second dept-level filter is applied so that,
    for example, Finance managers don't see Employee Management, and Sales
    managers don't see Project Management.
    """
    if role == "Department Manager":
        permitted = _dept_pages_for_manager(department_name)
        # Preserve canonical page order from PAGE_PERMISSIONS
        return [p for p in PAGE_PERMISSIONS if p in permitted]

    return [page for page, roles in PAGE_PERMISSIONS.items() if role in roles]


def scoped_department_id(auth: dict) -> int | None:
    """
    Return the department_id that should be used to filter queries.

    - Super Admin, HR Admin, Analyst  → None  (no filter, see everything)
    - Department Manager, Employee    → their own department_id
    """
    if auth.get("role") in ("Super Admin", "HR Admin", "Analyst"):
        return None
    return auth.get("department_id")


def review_editable_by(auth: dict, review_employee_dept_id: int | None) -> bool:
    """
    Return True if the logged-in user may create/edit a review for an employee
    who belongs to *review_employee_dept_id*.

    Rules:
        Super Admin  → always yes
        HR Admin     → always yes (cross-dept)
        Dept Manager → only if the employee is in their own department
        Others       → no
    """
    role = auth.get("role")
    if role in ("Super Admin", "HR Admin"):
        return True
    if role == "Department Manager":
        return auth.get("department_id") == review_employee_dept_id
    return False
