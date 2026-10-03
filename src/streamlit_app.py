from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from src.managers import AnalyticsManager, EmployeeManager, ProjectManager, ReviewManager
from src.models import Employee, Project, Review


st.set_page_config(page_title="Employee Analytics", page_icon="📊", layout="wide")
st.title("Enterprise Employee Analytics")
st.caption("People, performance, and project allocation")

DATA_DIR = Path(__file__).resolve().parent / "data"


@st.cache_data

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


def local_analytics(department_basis: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
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
        return trend, top, risk

    if department_basis == "review":
        department_versions = history[
            ["employee_id", "department_name", "start_date", "end_date"]
        ]
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
    trend = (
        review_rows.assign(review_year=review_rows["review_date"].dt.year)
        .groupby("review_year", as_index=False)["overall_score"]
        .mean()
        .rename(columns={"overall_score": "avg_score"})
    )
    top = (
        review_rows.groupby(
            ["employee_id", "first_name", "last_name", "department_name"],
            as_index=False,
        )["overall_score"]
        .mean()
    )
    top["department_rank"] = top.groupby("department_name")["overall_score"].rank(
        method="dense", ascending=False
    )
    top = top[top["department_rank"] <= 5].sort_values(["department_name", "department_rank"])

    current_history = history[history["is_current"].astype(bool)]
    risk = (
        current_history.groupby("department_name", as_index=False)
        .agg(
            employees=("employee_id", "count"),
            avg_performance=("performance_score", "mean"),
            avg_attrition_risk=("attrition_risk", "mean"),
        )
        .sort_values("avg_attrition_risk", ascending=False)
    )
    return trend, top, risk


def get_department_choices() -> list[dict]:
    try:
        return EmployeeManager().list_departments()
    except Exception:
        return []


page = st.sidebar.radio(
    "Workspace",
    ["Overview", "Employee Onboarding", "Project Management", "Performance Reviews", "Analytics Dashboard"],
)

if page == "Overview":
    employees, _, _ = load_local_data()
    st.subheader("Workforce overview")
    metric_columns = st.columns(3)
    metric_columns[0].metric("Synthetic employees", f"{len(employees):,}" if not employees.empty else "100,000")
    metric_columns[1].metric("Departments", "8")
    metric_columns[2].metric("Warehouse", "Connected" if get_department_choices() else "Local preview")
    if not employees.empty:
        department_counts = employees.groupby("department_name", as_index=False).size()
        st.plotly_chart(
            px.bar(department_counts, x="department_name", y="size", title="Employees by department"),
            width="stretch",
        )
    else:
        st.info("Generate the included sample data with `python -m src.ETL.synthesizer` to preview workforce metrics.")

elif page == "Employee Onboarding":
    st.subheader("Onboard employee")
    departments = get_department_choices()
    with st.form("employee_form"):
        first_name = st.text_input("First name")
        last_name = st.text_input("Last name")
        email = st.text_input("Work email")
        if departments:
            department_names = {row["department_name"]: row["department_id"] for row in departments}
            department_name = st.selectbox("Department", list(department_names))
            department_id = department_names[department_name]
        else:
            department_id = st.number_input("Department ID", min_value=1, step=1)
        job_title = st.text_input("Job title")
        salary = st.number_input("Annual salary", min_value=1_000.0, step=1_000.0)
        submitted = st.form_submit_button("Add employee", type="primary")
    if submitted:
        employee = Employee(
            first_name=first_name,
            last_name=last_name,
            email=email,
            department_id=int(department_id),
            job_title=job_title,
            salary=float(salary),
        )
        try:
            employee_id = EmployeeManager().create_employee(employee)
            st.success(f"Employee {employee_id} added. The current warehouse version was created.")
        except Exception as exc:
            st.error(f"Employee could not be added: {exc}")

elif page == "Project Management":
    st.subheader("Projects and allocations")
    departments = get_department_choices()
    create_tab, assign_tab = st.tabs(["Create project", "Assign employee"])
    with create_tab, st.form("project_form"):
        if departments:
            department_names = {row["department_name"]: row["department_id"] for row in departments}
            department_name = st.selectbox("Department", list(department_names))
            department_id = department_names[department_name]
        else:
            department_id = st.number_input("Department ID", min_value=1, step=1, key="project_department")
        project_name = st.text_input("Project name")
        budget = st.number_input("Budget", min_value=0.0, step=5_000.0)
        create_project = st.form_submit_button("Create project", type="primary")
    if create_project:
        try:
            project_id = ProjectManager().create_project(
                Project(project_name=project_name, department_id=int(department_id), budget=float(budget))
            )
            st.success(f"Project {project_id} created.")
        except Exception as exc:
            st.error(f"Project could not be created: {exc}")
    with assign_tab, st.form("assignment_form"):
        employee_id = st.number_input("Employee ID", min_value=1, step=1)
        project_id = st.number_input("Project ID", min_value=1, step=1)
        allocation = st.slider("Allocation", min_value=5, max_value=100, value=100, step=5)
        assign = st.form_submit_button("Assign employee")
    if assign:
        try:
            ProjectManager().assign_employee(int(employee_id), int(project_id), float(allocation))
            st.success("Project allocation saved.")
        except Exception as exc:
            st.error(f"Allocation could not be saved: {exc}")

elif page == "Performance Reviews":
    st.subheader("Submit performance review")
    with st.form("review_form"):
        employee_id = st.number_input("Employee ID", min_value=1, step=1)
        review_date = st.date_input("Review date")
        score = st.slider("Overall score", min_value=0.0, max_value=100.0, value=80.0, step=0.5)
        rating = st.selectbox(
            "Rating",
            ["Exceeds Expectations", "Strong", "Meets Expectations", "Needs Improvement"],
        )
        comments = st.text_area("Manager comments")
        submit_review = st.form_submit_button("Save review", type="primary")
    if submit_review:
        try:
            review_id = ReviewManager().create_review(
                Review(
                    employee_id=int(employee_id),
                    review_date=review_date,
                    overall_score=float(score),
                    rating=rating,
                    comments=comments,
                )
            )
            st.success(f"Review {review_id} saved. Run the warehouse ETL to refresh analytics.")
        except Exception as exc:
            st.error(f"Review could not be saved: {exc}")

else:
    st.subheader("Performance analytics")
    department_label = st.radio(
        "Attribute reviews to",
        ["Department at time of review", "Current department"],
        horizontal=True,
        help="Historical attribution uses the employee dimension version effective on the review date.",
    )
    department_basis = "review" if department_label == "Department at time of review" else "current"
    analytics = AnalyticsManager()
    try:
        trend = pd.DataFrame(analytics.get_performance_trends())
    except Exception:
        trend = pd.DataFrame()
    try:
        top = pd.DataFrame(analytics.get_top_performers(department_basis))
    except Exception:
        top = pd.DataFrame()
    try:
        risk = pd.DataFrame(analytics.get_attrition_risk())
    except Exception:
        risk = pd.DataFrame()
    if trend.empty or top.empty or risk.empty:
        local_trend, local_top, local_risk = local_analytics(department_basis)
        trend = trend if not trend.empty else local_trend
        top = top if not top.empty else local_top
        risk = risk if not risk.empty else local_risk
        st.caption("Showing local synthetic analytics for any view not available from MySQL.")

    chart_columns = st.columns(2)
    if not trend.empty:
        chart_columns[0].plotly_chart(
            px.line(trend, x="review_year", y="avg_score", markers=True, title="Year-over-year review score"),
            width="stretch",
        )
    if not top.empty:
        top["employee_name"] = top["first_name"] + " " + top["last_name"]
        chart_columns[1].plotly_chart(
            px.bar(
                top,
                x="overall_score",
                y="employee_name",
                color="department_name",
                orientation="h",
                hover_data=["department_rank"],
                title="Top performers by attributed department",
            ),
            width="stretch",
        )
        st.dataframe(
            top[["employee_id", "first_name", "last_name", "department_name", "overall_score", "department_rank"]],
            hide_index=True,
            width="stretch",
        )
    if not risk.empty:
        risk_chart = px.bar(
            risk,
            x="department_name",
            y="avg_attrition_risk",
            color="avg_performance",
            title="Current attrition risk by department",
            labels={"avg_attrition_risk": "Average risk", "avg_performance": "Average performance"},
        )
        st.plotly_chart(risk_chart, width="stretch")
