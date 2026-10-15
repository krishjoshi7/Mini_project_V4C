from __future__ import annotations

import sys
from pathlib import Path

# Add the project root to sys.path so 'src.*' imports work on Streamlit Cloud
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pandas as pd
import plotly.express as px
import streamlit as st

from src.exceptions import user_facing_error
from src.managers import AnalyticsManager, EmployeeManager, ProjectManager, ReviewManager
from src.models import Employee, Project, Review
from src.config.job_titles import DEPT_JOB_TITLES
from src.ui.theme import (
    COLORS,
    COLOURWAY,
    apply_theme,
    info_pill,
    kpi_card,
    page_header,
    score_band,
    section_title,
    status_badge,
    style_fig,
)
from src.auth.authenticator import require_auth, logout
from src.auth import rbac
from src.validators import (
    validate_employee_form,
    validate_employee_salary_update,
    validate_project_form,
    validate_project_update_form,
    validate_review_form,
)


apply_theme()

# ── Authentication gate ──────────────────────────────────────────────────────
# require_auth() renders the login page and calls st.stop() if not logged in.
# Once authenticated it returns the session auth dict.
_user = require_auth()

DATA_DIR = Path(__file__).resolve().parent / "data"
ALL_PAGES   = ["Overview", "Employee Management", "Project Management", "Performance Reviews", "Analytics Dashboard"]
PAGE_ICONS  = {"Overview": " ", "Employee Management": " ", "Project Management": " ", "Performance Reviews": " ", "Analytics Dashboard": " "}
# Filter pages down to what the current role can access
PAGES = rbac.allowed_pages(_user["role"], _user.get("department_name"))

# @st.cache_data
def load_local_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    employees_path = DATA_DIR / "synthetic_employees.csv"
    history_path = DATA_DIR / "employee_scd2_history.csv"
    reviews_path = DATA_DIR / "synthetic_performance_reviews.csv"
    if not all(path.exists() for path in (employees_path, history_path, reviews_path)):
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    employees = pd.read_csv(employees_path, parse_dates=["hire_date"])
    history = pd.read_csv(history_path, parse_dates=["start_date", "end_date"])
    reviews = pd.read_csv(reviews_path, parse_dates=["review_date"])
    return employees, history, reviews


def local_analytics(department_basis: str, department_name: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    employees, history, reviews = load_local_data()
    if employees.empty:
        trend = pd.DataFrame({"review_year": [2023, 2024, 2025], "avg_score": [82.4, 85.1, 87.6]})
        top = pd.DataFrame(
            {
                "employee_id": [101, 203, 156, 287],
                "first_name": ["Alicia", "Daniel", "Priya", "Morgan"],
                "last_name": ["Stone", "Nguyen", "Rao", "West"],
                "department_name": ["Engineering", "Sales", "Finance", "Operations"],
                "overall_score": [96, 94, 92, 91],
                "department_rank": [1, 1, 1, 1],
            }
        )
        risk = pd.DataFrame(
            {
                "department_name": ["Engineering", "Sales", "Finance", "Operations"],
                "employees": [1200, 980, 720, 640],
                "avg_performance": [88, 80, 86, 82],
                "avg_attrition_risk": [24, 38, 29, 34],
            }
        )
        bottlenecks = pd.DataFrame(
            {
                "project_id": [1, 2],
                "project_name": ["Project Alpha", "Project Beta"],
                "department_name": ["Engineering", "Sales"],
                "budget": [100000, 50000],
                "assigned_employees": [1, 2],
                "total_allocation_pct": [50, 150],
            }
        )
        if department_name and department_name != "All departments":
            top = top[top["department_name"] == department_name]
            risk = risk[risk["department_name"] == department_name]
            bottlenecks = bottlenecks[bottlenecks["department_name"] == department_name]
        return trend, top, risk, bottlenecks

    if department_basis == "review":
        department_versions = history[["employee_id", "department_name", "start_date", "end_date"]]
        review_rows = reviews.merge(department_versions, on="employee_id", how="inner")
        review_rows = review_rows[
            (review_rows["review_date"] >= review_rows["start_date"])
            & (review_rows["end_date"].isna() | (review_rows["review_date"] < review_rows["end_date"]))
        ]
    else:
        current = history.loc[history["is_current"].astype(bool), ["employee_id", "department_name"]]
        review_rows = reviews.merge(current, on="employee_id", how="inner")

    identity = employees[["employee_id", "first_name", "last_name"]]
    review_rows = review_rows.merge(identity, on="employee_id", how="left", validate="many_to_one")
    
    if department_name and department_name != "All departments":
        review_rows = review_rows[review_rows["department_name"] == department_name]
    trend = (
        review_rows.assign(review_year=review_rows["review_date"].dt.year)
        .groupby("review_year", as_index=False)["overall_score"]
        .mean()
        .rename(columns={"overall_score": "avg_score"})
    )
    top = (
        review_rows.groupby(["employee_id", "first_name", "last_name", "department_name"], as_index=False)["overall_score"]
        .mean()
    )
    top["department_rank"] = top.groupby("department_name")["overall_score"].rank(method="dense", ascending=False)
    top = top[top["department_rank"] <= 5].sort_values(["department_name", "department_rank"])

    current_history = history[history["is_current"].astype(bool)]
    if department_name and department_name != "All departments":
        current_history = current_history[current_history["department_name"] == department_name]
        
    risk = (
        current_history.groupby("department_name", as_index=False)
        .agg(
            employees=("employee_id", "count"),
            avg_performance=("performance_score", "mean"),
            avg_attrition_risk=("attrition_risk", "mean"),
        )
        .sort_values("avg_attrition_risk", ascending=False)
    )
    bottlenecks = pd.DataFrame() # Local CSVs don't have projects yet
    return trend, top, risk, bottlenecks


def get_department_choices() -> list[dict]:
    try:
        return EmployeeManager().list_departments()
    except Exception:
        return []


def render_form_message(message: str, success: bool) -> None:
    if success:
        st.success(message)
    else:
        st.error(message)

def render_department_field(departments: list[dict], key: str = "department") -> int:
    if departments:
        choices = {row["department_name"]: row["department_id"] for row in departments}
        selected = st.selectbox("Department", list(choices), key=key)
        return int(choices[selected])
    st.caption("Use the department ID when the warehouse is unavailable.")
    return int(st.number_input("Department ID", min_value=1, step=1, key=f"{key}_id"))


def render_overview() -> None:
    page_header("Enterprise Employee <span class='gradient-text'>Analytics</span>", "People, performance, and project allocation")
    section_title("Workforce overview")
    
    warehouse_connected = bool(get_department_choices())
    
    # Try fetching from MySQL first
    if warehouse_connected:
        try:
            metrics = AnalyticsManager().get_overview_metrics()
            total_employees = metrics["total_employees"]
            departments = metrics["total_departments"]
            average_score = f"{metrics['average_score']:.1f}"
            counts = pd.DataFrame(metrics["distribution"])
        except Exception:
            warehouse_connected = False

    # Fallback to CSV if MySQL is unreachable or failed
    if not warehouse_connected:
        employees, _, reviews = load_local_data()
        departments = int(employees["department_name"].nunique()) if not employees.empty else 8
        average_score = f"{reviews['overall_score'].mean():.1f}" if not reviews.empty else "--"
        total_employees = len(employees) if not employees.empty else 100_000
        counts = employees.groupby("department_name", as_index=False).size().sort_values("size", ascending=True) if not employees.empty else pd.DataFrame()
        info_pill("Showing local synthetic data for the overview page (MySQL connection failed)")

    kpis = st.columns(4)
    with kpis[0]:
        kpi_card("Total employees", f"{total_employees:,}", icon="♙")
    with kpis[1]:
        kpi_card("Departments", departments, icon="⌘")
    with kpis[2]:
        kpi_card("Data source", "MySQL" if warehouse_connected else "Local preview", icon="◉")
    with kpis[3]:
        kpi_card("Average review score", average_score, icon="✦")
        
    st.markdown("<div style='height:.9rem'></div>", unsafe_allow_html=True)
    status_badge("Connected to MySQL" if warehouse_connected else "Local preview", "success" if warehouse_connected else "warning")
    
    if not counts.empty:
        fig = px.bar(
            counts,
            x="size",
            y="department_name",
            orientation="h",
            text="size",
            color="size",
            color_continuous_scale=[[0, COLORS["bg_purple"]], [.55, COLORS["magenta"]], [1, COLORS["pink"]]],
            labels={"size": "Employees", "department_name": "Department"},
            title="Employees by department",
        )
        fig.update_traces(texttemplate="%{text:,}", textposition="outside", hovertemplate="%{y}: %{x:,}<extra></extra>")
        fig.update_layout(coloraxis_showscale=False, xaxis_title="Employees", yaxis_title="Department")
        with st.container(border=True):
            section_title("Workforce distribution")
            st.plotly_chart(style_fig(fig, 410), use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("Generate the included sample data with `python -m src.ETL.synthesizer` to preview workforce metrics.")


def render_employees() -> None:
    page_header("Employee <span class='gradient-text'>management</span>", "Create and manage workforce records")
    departments = get_department_choices()

    # Department Managers only see their own department in the dropdown
    dept_scope = rbac.scoped_department_id(_user)
    if dept_scope is not None:
        departments = [d for d in departments if d["department_id"] == dept_scope]

    create_tab, manage_tab = st.tabs(["Onboard employee", "Manage employee"])
    
    with create_tab:
        with st.container(border=True):
            section_title("New employee profile")
            # ── Department picker (OUTSIDE form so job titles update reactively) ──
            dept_choices = {row["department_name"]: row["department_id"] for row in departments}
            selected_dept_name = st.selectbox(
                "Department",
                list(dept_choices.keys()) if dept_choices else ["-- No departments available --"],
                key="onboard_dept_select",
            )
            dept_titles = DEPT_JOB_TITLES.get(selected_dept_name, [])

            with st.form("employee_form"):
                first_col, last_col = st.columns(2)
                with first_col:
                    first_name = st.text_input("First name")
                    email = st.text_input("Work email")
                with last_col:
                    last_name = st.text_input("Last name")
                    if dept_titles:
                        job_title = st.selectbox("Job title", dept_titles)
                    else:
                        job_title = st.text_input("Job title", placeholder="Enter job title")
                department_id = int(dept_choices[selected_dept_name]) if dept_choices else 0
                salary_col, _ = st.columns([1, 1])
                with salary_col:
                    salary = st.number_input("Annual salary", min_value=1_000.0, step=1_000.0, format="%.2f")
                st.markdown("<div style='height:.4rem'></div>", unsafe_allow_html=True)
                pwd_col1, pwd_col2 = st.columns(2)
                with pwd_col1:
                    initial_password = st.text_input(
                        "Initial login password",
                        type="password",
                        placeholder="Min 8 characters",
                        help="HR sets this. The employee can change it after first login.",
                    )
                with pwd_col2:
                    confirm_password = st.text_input(
                        "Confirm password",
                        type="password",
                        placeholder="Repeat password",
                    )
                st.caption("Employee details are validated before they are written to OLTP and the current warehouse dimension.")
                submitted = st.form_submit_button("Add employee", type="primary", use_container_width=True)
        if submitted:
            errors = validate_employee_form(
                first_name, last_name, email, job_title,
                float(salary), department_id,
                initial_password, confirm_password,
            )
            if errors:
                for err in errors:
                    st.error(err)
            else:
                employee = Employee(first_name=first_name, last_name=last_name, email=email, department_id=department_id, job_title=job_title, salary=float(salary))
                try:
                    employee_id = EmployeeManager().create_employee(employee)
                    # Auto-create login account with the password HR entered
                    from src.auth.authenticator import create_account
                    create_account(employee_id, initial_password)
                    st.success(
                        f"✅ Employee **{first_name} {last_name}** (ID: {employee_id}) onboarded.  \n\n"
                        f"**Login email:** `{email}`  \n"
                        f"**Temporary password:** `{initial_password}`  \n\n"
                        "Share these credentials with the employee — ask them to change the password on first login."
                    )
                except Exception as exc:
                    render_form_message(f"Employee could not be added: {exc}", False)
                
    with manage_tab:
        with st.container(border=True):
            section_title("Find employee")
            search_col, _ = st.columns([1, 2])
            with search_col:
                search_id = st.number_input("Employee ID", min_value=1, step=1, key="search_emp_id")
                search_btn = st.button("Search")
        
        if search_btn:
            try:
                emp = EmployeeManager().get_employee(search_id)
                if emp:
                    st.session_state["selected_employee"] = emp
                else:
                    st.session_state.pop("selected_employee", None)
                    st.error("Employee not found.")
            except Exception as exc:
                 st.error(f"Error fetching employee: {user_facing_error(exc)}")
                 
        if "selected_employee" in st.session_state:
            emp = st.session_state["selected_employee"]

            # Dept Managers can only look up employees from their own department
            if _user["role"] == "Department Manager" and emp["department_id"] != _user["department_id"]:
                st.error(
                    f"Access denied — you can only view employees in your department ({_user['department_name']})."
                )
                st.session_state.pop("selected_employee", None)
            else:
                if emp.get("status") == "inactive":
                    st.warning("This employee record is marked as inactive.")

                # ── Determine edit capabilities ───────────────────────────────
                _can_sal      = rbac.can_edit_salary(_user)
                _can_dept_rol = rbac.can_edit_dept_and_role(_user)

                # Resolve dept name for job title list
                all_depts_full = get_department_choices()
                emp_dept_name = next(
                    (d["department_name"] for d in all_depts_full if d["department_id"] == emp["department_id"]),
                    None,
                )

                with st.container(border=True):
                    section_title(f"{emp['first_name']} {emp['last_name']}")

                    # Always-visible read-only summary
                    info_col1, info_col2 = st.columns(2)
                    with info_col1:
                        st.write(f"**Employee ID:** {emp['employee_id']}")
                        st.write(f"**Email:** {emp['email']}")
                        st.write(f"**Department:** {emp_dept_name or emp['department_id']}")
                    with info_col2:
                        st.write(f"**Job Title:** {emp['job_title']}")
                        st.write(f"**Salary:** ${float(emp['salary']):,.2f}")
                        st.write(f"**Status:** {emp['status']}")

                    if not _can_sal and not _can_dept_rol:
                        st.info("ℹ️ You have view-only access to this employee's record.")

                # ── HR section: Department + Job Title ────────────────────────
                if _can_dept_rol:
                    with st.container(border=True):
                        section_title("Update department & role")
                        with st.form("update_dept_role_form"):
                            dept_names_full = [d["department_name"] for d in all_depts_full]
                            dept_ids_full   = [d["department_id"]   for d in all_depts_full]
                            try:
                                dept_idx = dept_ids_full.index(emp["department_id"])
                            except ValueError:
                                dept_idx = 0
                            new_dept_name = st.selectbox("Department", dept_names_full, index=dept_idx, key="hr_upd_dept")
                            new_dept_id   = dept_ids_full[dept_names_full.index(new_dept_name)]

                            titles_for_new_dept = DEPT_JOB_TITLES.get(new_dept_name, [])
                            if titles_for_new_dept:
                                cur_title = emp["job_title"]
                                t_idx = titles_for_new_dept.index(cur_title) if cur_title in titles_for_new_dept else 0
                                new_job_title = st.selectbox("Job title", titles_for_new_dept, index=t_idx, key="hr_upd_title")
                            else:
                                new_job_title = st.text_input("Job title", value=emp["job_title"], key="hr_upd_title_txt")

                            st.caption("Changing department or job title triggers an SCD2 warehouse update.")
                            hr_upd_btn = st.form_submit_button("Save department & role", type="primary", use_container_width=True)

                        if hr_upd_btn:
                            try:
                                mgr = EmployeeManager()
                                changed = False
                                if int(new_dept_id) != int(emp["department_id"]):
                                    mgr.update_department(emp["employee_id"], int(new_dept_id))
                                    changed = True
                                if new_job_title != emp["job_title"]:
                                    mgr.update_job_title(emp["employee_id"], new_job_title)
                                    changed = True
                                if changed:
                                    st.success("Department / role updated. (SCD2 applied)")
                                    st.session_state["selected_employee"] = mgr.get_employee(emp["employee_id"])
                                    st.rerun()
                                else:
                                    st.info("No changes to save.")
                            except Exception as exc:
                                st.error(f"Failed to update: {exc}")

                # ── Finance / HR section: Salary ──────────────────────────────
                if _can_sal:
                    with st.container(border=True):
                        section_title("Update salary")
                        with st.form("update_salary_form"):
                            new_salary = st.number_input(
                                "Annual salary",
                                min_value=1_000.0,
                                value=float(emp["salary"]),
                                step=1_000.0,
                                format="%.2f",
                                key="fin_upd_sal",
                            )
                            st.caption("Max 2× hike enforced. Changes trigger an SCD2 warehouse update.")
                            sal_upd_btn = st.form_submit_button("Save salary", type="primary", use_container_width=True)

                        if sal_upd_btn:
                            errors: list[str] = validate_employee_salary_update(float(emp["salary"]), float(new_salary))
                            if errors:
                                for err in errors:
                                    st.error(err)
                            elif float(new_salary) == float(emp["salary"]):
                                st.info("No change to salary.")
                            else:
                                try:
                                    EmployeeManager().update_salary(emp["employee_id"], float(new_salary))
                                    st.success("Salary updated. (SCD2 applied)")
                                    st.session_state["selected_employee"] = EmployeeManager().get_employee(emp["employee_id"])
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Failed to update salary: {exc}")

                # ── Deactivate (Super Admin + HR Admin only) ──────────────────
                if rbac.can(_user["role"], "employee.deactivate"):
                    with st.container(border=True):
                        section_title("Deactivate employee")
                        st.warning(
                            "This marks the employee as inactive. It does not permanently delete "
                            "the employee, performance reviews, project assignments, or historical versions."
                        )
                        confirm_deactivation = st.checkbox(
                            f"I confirm that I want to deactivate {emp['first_name']} "
                            f"{emp['last_name']} (ID: {emp['employee_id']}).",
                            key=f"confirm_deactivate_{emp['employee_id']}",
                        )
                        if st.button(
                            "Deactivate employee",
                            type="primary",
                            key=f"deactivate_employee_{emp['employee_id']}",
                            disabled=not confirm_deactivation,
                            use_container_width=True,
                        ):
                            try:
                                EmployeeManager().delete_employee(emp["employee_id"])
                                st.success(
                                    f"{emp['first_name']} {emp['last_name']} has been deactivated. "
                                    "Historical records have been preserved."
                                )
                                st.session_state.pop("selected_employee", None)
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Failed to deactivate employee: {exc}")

            


def render_projects() -> None:
    page_header("Project <span class='gradient-text'>management</span>", "Create initiatives and balance employee allocations")
    departments = get_department_choices()

    # Scope departments for Department Managers
    dept_scope = rbac.scoped_department_id(_user)
    if dept_scope is not None:
        departments = [d for d in departments if d["department_id"] == dept_scope]

    # Analysts get a read-only view; only certain Dept Managers + Super Admin can edit
    _can_edit_proj = rbac.can_manage_projects(_user)

    if not _can_edit_proj:
        # Read-only project view for Finance Analyst / other Analyst roles
        with st.container(border=True):
            section_title("Project list (read-only)")
            st.info("📄 You have read-only access to project information.")
            search_col, _ = st.columns([1, 2])
            with search_col:
                search_pid_ro = st.number_input("Project ID", min_value=1, step=1, key="ro_proj_id")
                if st.button("View Project", key="ro_view_proj"):
                    try:
                        proj = ProjectManager().get_project(search_pid_ro)
                        if proj:
                            st.json({
                                "Project ID":   proj["project_id"],
                                "Name":         proj["project_name"],
                                "Status":       proj["status"],
                                "Budget":       f"${float(proj['budget']):,.2f}",
                            })
                        else:
                            st.error("Project not found.")
                    except Exception as exc:
                        st.error(f"Error: {exc}")
        return

    create_tab, assign_tab, manage_tab = st.tabs(["Create project", "Assign employee", "Manage projects"])
    with create_tab:
        with st.container(border=True):
            section_title("Project brief")
            with st.form("project_form"):
                project_name = st.text_input("Project name")
                department_col, budget_col = st.columns(2)
                with department_col:
                    department_id = render_department_field(departments, "project_department")
                with budget_col:
                    budget = st.number_input("Budget", min_value=0.0, step=5_000.0, format="%.2f")
                create_project = st.form_submit_button("Create project", type="primary", use_container_width=True)
        if create_project:
            errors = validate_project_form(project_name, department_id, float(budget))
            if errors:
                for err in errors:
                    st.error(err)
            else:
                try:
                    project_id = ProjectManager().create_project(Project(project_name=project_name, department_id=department_id, budget=float(budget)))
                    render_form_message(f"Project {project_id} created.", True)
                except Exception as exc:
                    render_form_message(f"Project could not be created: {exc}", False)
    with assign_tab:
        with st.container(border=True):
            section_title("Allocation details")
            with st.form("assignment_form"):
                employee_col, project_col = st.columns(2)
                with employee_col:
                    assign_emp_id = st.number_input("Employee ID", min_value=1, step=1, key="assign_emp_id")
                with project_col:
                    assign_proj_id = st.number_input("Project ID", min_value=1, step=1, key="assign_proj_id")
                allocation = st.slider("Allocation", min_value=5, max_value=100, value=100, step=5, format="%d%%")
                if dept_scope is not None:
                    st.caption(
                        f"🔒 You can only assign employees from **{_user['department_name']}** to projects."
                    )
                assign = st.form_submit_button("Assign employee", type="primary", use_container_width=True)
        if assign:
            # Dept Managers may only assign employees from their own department
            if dept_scope is not None:
                try:
                    target_emp = EmployeeManager().get_employee(int(assign_emp_id))
                    if target_emp is None:
                        st.error("Employee not found.")
                        st.stop()
                    if target_emp["department_id"] != dept_scope:
                        st.error(
                            f"Access denied — you can only assign employees from your own department "
                            f"({_user['department_name']}). Employee {int(assign_emp_id)} belongs to a different department."
                        )
                        st.stop()
                except Exception as exc:
                    st.error(f"Could not verify employee: {exc}")
                    st.stop()
            try:
                ProjectManager().assign_employee(int(assign_emp_id), int(assign_proj_id), float(allocation))
                render_form_message("Project allocation saved.", True)
            except Exception as exc:
                render_form_message(f"Allocation could not be saved: {user_facing_error(exc)}", False)

    with manage_tab:
        with st.container(border=True):
            section_title("Find project")
            search_col, _ = st.columns([1, 2])
            with search_col:
                search_pid = st.number_input("Project ID", min_value=1, step=1, key="search_proj_id")
                search_pbtn = st.button("Search Project")
                
        if search_pbtn:
            try:
                proj = ProjectManager().get_project(search_pid)
                if proj:
                    st.session_state["selected_project"] = proj
                else:
                    st.session_state.pop("selected_project", None)
                    st.error("Project not found.")
            except Exception as exc:
                st.error(f"Error fetching project: {user_facing_error(exc)}")
                
        if "selected_project" in st.session_state:
            proj = st.session_state["selected_project"]
            with st.container(border=True):
                section_title(f"Update Project: {proj['project_name']}")
                with st.form("update_proj_form"):
                    new_name = st.text_input("Project Name", value=proj["project_name"])
                    new_budget = st.number_input("Budget", min_value=0.0, value=float(proj["budget"]), step=5000.0)
                    
                    statuses = ["planned", "active", "completed", "on_hold"]
                    current_status = proj["status"]
                    idx = statuses.index(current_status) if current_status in statuses else 0
                    new_status = st.selectbox("Status", statuses, index=idx)
                    
                    st.caption("Project budget updates cannot increase or decrease by more than 2x.")
                    update_btn = st.form_submit_button("Save changes", type="primary", use_container_width=True)
                    
            if update_btn:
                try:
                    ProjectManager().update_project(proj["project_id"], new_name, float(new_budget), new_status)
                    st.success("Project updated successfully!")
                    st.session_state["selected_project"] = ProjectManager().get_project(proj["project_id"])
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed to update project: {user_facing_error(exc)}")
                    
            with st.container(border=True):
                section_title("Danger zone")
                if st.button("Delete project", type="primary", key="del_proj"):
                    try:
                        ProjectManager().update_project(proj["project_id"], new_name, float(new_budget), new_status)
                        st.success("Project updated successfully!")
                        st.session_state["selected_project"] = ProjectManager().get_project(proj["project_id"])
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Failed to delete project: {user_facing_error(exc)}")

def render_reviews() -> None:
    page_header("Performance <span class='gradient-text'>reviews</span>", "Capture a clear, consistent view of employee performance")
    create_tab, manage_tab = st.tabs(["Create review", "Manage reviews"])
    
    with create_tab:
        with st.container(border=True):
            section_title("Review details")
            with st.form("review_form"):
                identity_col, date_col = st.columns(2)
                with identity_col:
                    employee_id = st.number_input("Employee ID", min_value=1, step=1)
                with date_col:
                    review_date = st.date_input("Review date")
                score = st.slider("Overall score", min_value=0.0, max_value=100.0, value=80.0, step=0.5)
                band, band_color = score_band(score)
                st.markdown(f'<span class="score-band" style="color:{band_color}; border-color:{band_color}55">●&nbsp; {band} · {score:.1f}/100</span>', unsafe_allow_html=True)
                rating = st.selectbox("Rating", ["Exceeds Expectations", "Strong", "Meets Expectations", "Needs Improvement"])
                comments = st.text_area("Manager comments", height=130)
                submit_review = st.form_submit_button("Save review", type="primary", use_container_width=True)
        if submit_review:
            errors = validate_review_form(int(employee_id), float(score), rating, comments)
            if errors:
                for err in errors:
                    st.error(err)
            else:
                try:
                    review_id = ReviewManager().create_review(Review(employee_id=int(employee_id), review_date=review_date, overall_score=float(score), rating=rating, comments=comments))
                    render_form_message(f"Review {review_id} saved. Run the warehouse ETL to refresh analytics.", True)
                except Exception as exc:
                    render_form_message(f"Review could not be saved: {exc}", False)

    with manage_tab:
        with st.container(border=True):
            section_title("Find review")
            search_col, _ = st.columns([1, 2])
            with search_col:
                search_rid = st.number_input("Review ID", min_value=1, step=1, key="search_rev_id")
                search_rbtn = st.button("Search Review")
                
        if search_rbtn:
            try:
                rev = ReviewManager().get_review(search_rid)
                if rev:
                    # Dept Manager guard: verify the reviewed employee is in their dept
                    if _user["role"] == "Department Manager":
                        rev_emp = EmployeeManager().get_employee(rev["employee_id"])
                        if rev_emp and not rbac.review_editable_by(_user, rev_emp["department_id"]):
                            st.error(
                                "Access denied — you can only view or edit reviews for employees "
                                f"in your department ({_user['department_name']})."
                            )
                            st.session_state.pop("selected_review", None)
                        else:
                            st.session_state["selected_review"] = rev
                    else:
                        st.session_state["selected_review"] = rev
                else:
                    st.session_state.pop("selected_review", None)
                    st.error("Review not found.")
            except Exception as exc:
                st.error(f"Error fetching review: {user_facing_error(exc)}")
                
        if "selected_review" in st.session_state:
            rev = st.session_state["selected_review"]
            with st.container(border=True):
                section_title(f"Update Review {rev['review_id']} (Emp: {rev['employee_id']})")
                with st.form("update_rev_form"):
                    new_score = st.slider("Overall score", min_value=0.0, max_value=100.0, value=float(rev["overall_score"]), step=0.5, key="upd_rev_score")
                    ratings = ["Exceeds Expectations", "Strong", "Meets Expectations", "Needs Improvement"]
                    current_rating = rev["rating"]
                    idx = ratings.index(current_rating) if current_rating in ratings else 0
                    new_rating = st.selectbox("Rating", ratings, index=idx, key="upd_rev_rating")
                    
                    new_comments = st.text_area("Comments", value=rev.get("comments", ""), key="upd_rev_comments")
                    update_btn = st.form_submit_button("Save changes", type="primary", use_container_width=True)
                    
            if update_btn:
                try:
                    ReviewManager().update_review(rev["review_id"], float(new_score), new_rating, new_comments)
                    st.success("Review updated successfully!")
                    st.session_state["selected_review"] = ReviewManager().get_review(rev["review_id"])
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed to update review: {user_facing_error(exc)}")
                    
            # Only Super Admin and HR Admin can delete reviews
            if rbac.can(_user["role"], "review.delete"):
                with st.container(border=True):
                    section_title("Danger zone")
                    if st.button("Delete review", type="primary", key="del_rev"):
                        try:
                            ReviewManager().delete_review(rev["review_id"])
                            st.success("Review deleted.")
                            st.session_state.pop("selected_review", None)
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Failed to delete review: {exc}")

def render_analytics() -> None:
    page_header("Performance <span class='gradient-text'>analytics</span>", "Read workforce momentum, high performers, and risk at a glance")

    department_basis = "review"

    departments_list = get_department_choices()

    # Department Managers are locked to their own department — no selector shown
    dept_scope = rbac.scoped_department_id(_user)
    if dept_scope is not None:
        selected_department = _user["department_name"]
        st.info(f"Showing analytics for: **{selected_department}**")
    else:
        dept_names = ["All departments"] + sorted([d["department_name"] for d in departments_list])
        selected_department = st.selectbox("Filter dashboard by department", dept_names)
        
    analytics = AnalyticsManager()
    try:
        trend = pd.DataFrame(analytics.get_performance_trends(department_basis, selected_department))
    except Exception as e:
        st.error(f"Trend error: {user_facing_error(e)}")
        trend = pd.DataFrame()
    try:
        top = pd.DataFrame(analytics.get_top_performers(department_basis, selected_department))
    except Exception as e:
        st.error(f"Top error: {user_facing_error(e)}")
        top = pd.DataFrame()
    try:
        risk = pd.DataFrame(analytics.get_attrition_risk(selected_department))
    except Exception as e:
        st.error(f"Risk error: {user_facing_error(e)}")
        risk = pd.DataFrame()
    try:
        bottlenecks = pd.DataFrame(analytics.get_project_bottlenecks(selected_department))
    except Exception as e:
        st.error(f"Bottlenecks error: {user_facing_error(e)}")
        bottlenecks = pd.DataFrame()
        
    # Show info pill if any query threw an exception (causing the df to be explicitly empty in our except blocks)
    # but don't fallback to local CSV data just because a department has no records in a specific table.
    local_fallback = trend.empty and top.empty and risk.empty and bottlenecks.empty
    if local_fallback:
        info_pill("Showing synthetic analytics for any view not available from MySQL")

    latest_score = float(trend.iloc[-1]["avg_score"]) if not trend.empty else 0
    year_change = float(trend.iloc[-1]["avg_score"] - trend.iloc[-2]["avg_score"]) if len(trend) > 1 else 0
    reviewed_count = int(top["employee_id"].nunique()) if not top.empty else 0
    high_risk_count = int((risk["avg_attrition_risk"] >= 60).sum()) if not risk.empty else 0
    kpis = st.columns(4)
    with kpis[0]:
        kpi_card("Latest average score", f"{latest_score:.1f}", icon="✦")
    with kpis[1]:
        kpi_card("Year-over-year change", f"{year_change:+.1f}", "score points", icon="↗")
    with kpis[2]:
        kpi_card("Employees reviewed", f"{reviewed_count:,}", icon="♙")
    with kpis[3]:
        kpi_card("High-risk departments", high_risk_count, "average risk ≥ 60", icon="◌")

    chart_columns = st.columns(2)
    if not trend.empty:
        with chart_columns[0].container(border=True):
            section_title("Year-over-year review score")
            fig = px.line(trend, x="review_year", y="avg_score", markers=True, labels={"review_year": "Year", "avg_score": "Average review score"})
            fig.update_traces(line={"color": COLORS["pink"], "width": 3}, marker={"color": COLORS["soft_pink"], "size": 9}, fill="tozeroy", fillcolor="rgba(185,58,150,.16)", hovertemplate="Year %{x}<br>Average review score %{y:.1f}<extra></extra>")
            padding = max(1, (float(trend["avg_score"].max()) - float(trend["avg_score"].min())) * 0.35)
            y_min = float(trend["avg_score"].min()) - padding
            y_max = float(trend["avg_score"].max()) + padding
            fig.update_layout(xaxis={"dtick": 1, "tickformat": "d", "title": "Year"}, yaxis={"range": [y_min, y_max], "title": "Average review score"})
            st.plotly_chart(style_fig(fig, 365), use_container_width=True, config={"displayModeBar": False})
            st.caption(f"Review scores moved {year_change:+.1f} points in the latest year.")
    if not top.empty:
        filtered_top = top.copy()
        filtered_top = filtered_top.sort_values("overall_score", ascending=True).tail(10)
        filtered_top["employee_name"] = filtered_top["first_name"] + " " + filtered_top["last_name"]
        with chart_columns[1].container(border=True):
            section_title("Top performers")
            fig = px.bar(filtered_top, x="overall_score", y="employee_name", orientation="h", color="department_name", text="overall_score", color_discrete_sequence=COLOURWAY, labels={"overall_score": "Average score", "employee_name": "Employee", "department_name": "Department"})
            fig.update_traces(texttemplate="%{text:.1f}", textposition="outside", hovertemplate="%{y}<br>Average score %{x:.1f}<extra></extra>")
            fig.update_layout(showlegend=False, xaxis_title="Average score", yaxis_title="Employee")
            st.plotly_chart(style_fig(fig, 365), use_container_width=True, config={"displayModeBar": False})
            st.caption("The strongest average performers across the selected department view.")

    if not risk.empty:
        with st.container(border=True):
            section_title("Attrition risk by department")
            risk_display = risk.sort_values("avg_attrition_risk", ascending=True)
            fig = px.bar(risk_display, x="avg_attrition_risk", y="department_name", orientation="h", text="avg_attrition_risk", color="avg_attrition_risk", color_continuous_scale=[[0, COLORS["soft_pink"]], [.5, COLORS["magenta"]], [1, COLORS["bg_indigo"]]], labels={"avg_attrition_risk": "Average attrition risk", "department_name": "Department"})
            fig.update_traces(texttemplate="%{text:.1f}", textposition="outside", hovertemplate="%{y}<br>Average attrition risk %{x:.1f}<extra></extra>")
            fig.update_layout(coloraxis_showscale=False, xaxis_title="Average attrition risk", yaxis_title="Department")
            st.plotly_chart(style_fig(fig, 390), use_container_width=True, config={"displayModeBar": False})
            st.caption("Higher values indicate departments that may benefit from a closer retention review.")

    if not top.empty:
        display_top = top[["employee_id", "first_name", "last_name", "department_name", "overall_score", "department_rank"]].copy()
        display_top.columns = ["Employee ID", "First name", "Last name", "Department", "Average score", "Department rank"]
        with st.container(border=True):
            section_title("Performance roster")
            st.dataframe(display_top.sort_values("Average score", ascending=False), hide_index=True, use_container_width=True)
            
    if not bottlenecks.empty:
        with st.container(border=True):
            section_title("Project bottlenecks")
            
            # Interactive Chart for Bottlenecks
            bottlenecks["budget"] = pd.to_numeric(bottlenecks["budget"], errors="coerce").fillna(0)
            fig = px.scatter(
                bottlenecks, 
                x="assigned_employees", 
                y="total_allocation_pct", 
                color="department_name",
                size="budget",
                hover_name="project_name",
                hover_data={"project_id": True, "department_name": False, "budget": ":$,.0f", "assigned_employees": True, "total_allocation_pct": True},
                labels={
                    "assigned_employees": "Assigned Employees", 
                    "total_allocation_pct": "Total Allocation %", 
                    "department_name": "Department",
                    "budget": "Budget"
                },
                color_discrete_sequence=COLOURWAY,
                title="Resource Allocation by Project"
            )
            fig.update_layout(xaxis_title="Assigned Employees", yaxis_title="Total Allocation % (across all employees)", showlegend=True)
            st.plotly_chart(style_fig(fig, 390), use_container_width=True, config={"displayModeBar": False})
            st.caption("Active projects with low total allocation or headcount indicate potential resource bottlenecks. Bubble size corresponds to project budget.")

            display_bottlenecks = bottlenecks.copy()
            display_bottlenecks.columns = ["Project ID", "Project Name", "Department", "Budget", "Assigned Employees", "Total Allocation %"]
            st.dataframe(display_bottlenecks, hide_index=True, use_container_width=True)


# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.markdown('<div class="brand-mark"><span>V4C</span>.ai</div>', unsafe_allow_html=True)

# User identity pill
st.sidebar.markdown(
    f"""
    <div style="margin: 0 0 1.4rem .6rem; padding: .55rem .8rem;
                background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.12);
                border-radius: 12px; font-size: .78rem; line-height: 1.5;">
        <div style="color: white; font-weight: 600; font-size: .85rem;">{_user['name']}</div>
        <div style="color: #CFC3E6;">{_user['role']}</div>
        <div style="color: #9B89C4; font-size: .72rem;">{_user['department_name']}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

page = st.sidebar.radio("Workspace", [f"{PAGE_ICONS[item]}  {item}" for item in PAGES], label_visibility="collapsed")
page = page.split("  ", 1)[1].strip()

# ── Change password expander in sidebar ─────────────────────────────────────
with st.sidebar.expander("🔑  Change password", expanded=False):
    with st.form("change_pwd_form"):
        current_pwd  = st.text_input("Current password",  type="password", key="chg_current")
        new_pwd      = st.text_input("New password",      type="password", key="chg_new",
                                     help="Minimum 8 characters")
        confirm_pwd  = st.text_input("Confirm new password", type="password", key="chg_confirm")
        change_btn   = st.form_submit_button("Update password", use_container_width=True)

    if change_btn:
        if not current_pwd or not new_pwd or not confirm_pwd:
            st.error("All fields are required.")
        elif len(new_pwd) < 8:
            st.error("New password must be at least 8 characters.")
        elif new_pwd != confirm_pwd:
            st.error("New passwords do not match.")
        else:
            # Verify current password before allowing the change
            from src.auth.authenticator import verify_password, change_password
            from src.database.db_manager import DatabaseConnection
            class _PwdDB(DatabaseConnection): pass
            row = _PwdDB().fetch_one(
                "SELECT password_hash FROM user_accounts WHERE employee_id = %s",
                (_user["employee_id"],)
            )
            if row and verify_password(current_pwd, row["password_hash"]):
                change_password(_user["employee_id"], new_pwd)
                st.success("Password updated successfully.")
            else:
                st.error("Current password is incorrect.")

# Logout button
st.sidebar.markdown("<div style='margin-top:.5rem'></div>", unsafe_allow_html=True)
if st.sidebar.button("Sign out", key="logout_btn", use_container_width=True):
    logout()

if page == "Overview":
    render_overview()
elif page == "Employee Management":
    render_employees()
elif page == "Project Management":
    render_projects()
elif page == "Performance Reviews":
    render_reviews()
else:
    render_analytics()

#comme
