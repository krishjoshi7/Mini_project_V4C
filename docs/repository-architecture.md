# Current Repository Architecture

## 1. PROJECT SUMMARY

This is a Python employee analytics application with reproducible Faker-generated CSV data, a MySQL database, SCD Type 2 employee history, and a Streamlit frontend. It uses pandas, NumPy, Faker, mysql-connector-python, Plotly, and Streamlit. It is run with `python -m src.ETL.synthesizer`, `python -m src.run_etl`, and `streamlit run src/streamlit_app.py`; Streamlit Cloud deployment is described in the README but has no repository deployment configuration.

## 2. LAYER-BY-LAYER INVENTORY

### a) Data sources

- `src/data/synthetic_employees.csv`: generated employee snapshot; 100,000 employee rows in the committed dataset.
- `src/data/employee_scd2_history.csv`: generated employee department/job/salary versions with `start_date`, `end_date`, and `is_current`.
- `src/data/synthetic_performance_reviews.csv`: generated review ID, employee ID, review date, score, rating, and comments.
- `.env` or shell environment variables: external database configuration loaded by `src/config/settings.py`.
- MySQL server: external runtime database configured through `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME`.

### b) Data synthesis / generation

- `src/ETL/synthesizer.py`: `DataSynthesizer` uses Faker, NumPy, and pandas.
- Default configuration: 100,000 employees, 30% historical fraction, seed `42`.
- Methods: `generate_base_employee_data()`, `generate_scd_type_2_history()`, `generate_performance_reviews()`, and `export_to_csv()`.
- Outputs: `synthetic_employees.csv`, `employee_scd2_history.csv`, and `synthetic_performance_reviews.csv` under `src/data/`.
- `src/ETL/extractor.py`: `CSVExtractor.extract()` reads CSVs and parses recognized date columns.
- `src/ETL/transformer.py`: `DataTransformer.build_employee_history()` merges identity fields and validates employee IDs, one current version per employee, and date intervals.

### c) Ingestion / staging load

- `src/run_etl.py`: command-line entry point for `DataWarehouseLoader`.
- `src/ETL/loader.py`: `DataWarehouseLoader`, inheriting from `DatabaseConnection`, reads CSVs directly and loads MySQL in batches of 1,000.
- Load order: extract employee/history data; validate SCD2 data; upsert departments; upsert employees; upsert reviews; upsert employee versions; populate date, project, and performance fact tables.
- No physical staging/Bronze database or staging tables exist. CSV files are the pre-load layer.

### d) OLTP database

- Database: `employee_analytics`, defined in `src/database/schema.sql`.

- `departments`: PK `department_id`; unique `department_name`.
- `employees`: PK `employee_id`; FKs `department_id -> departments.department_id`, `manager_id -> employees.employee_id`; names, email, job title, hire date, salary, performance score, attrition risk, status.
- `projects`: PK `project_id`; FK `department_id -> departments.department_id`; project name, budget, dates, status.
- `project_assignments`: PK `assignment_id`; FKs `employee_id -> employees.employee_id`, `project_id -> projects.project_id`; unique `(employee_id, project_id)`; allocation percentage and assigned date.
- `performance_reviews`: PK `review_id`; FKs `employee_id -> employees.employee_id`, `manager_id -> employees.employee_id`; review date, score, rating, comments.

### e) ETL

- Orchestration: `src/run_etl.py` and `src/ETL/loader.py`.
- Stored procedure in `src/database/schema.sql`: `sp_close_employee_scd2_version(p_employee_id, p_effective_date)`, which closes the current `dim_employee` row. It exists but is not called by the Python loader.
- Date load in `DataWarehouseLoader.load_review_facts()`: source `performance_reviews`, target `dim_date`, integer `YYYYMMDD` keys.
- Project load: source `projects`, `departments`, and `dim_department`; target `dim_project`.
- Fact load: source `performance_reviews`, `project_assignments`, `dim_employee`, and `dim_project`; target `fact_performance_reviews`.
- `ranked_assignments` CTE in `src/ETL/loader.py` uses `ROW_NUMBER() OVER (PARTITION BY pr.review_id ORDER BY pa.assigned_date DESC, pa.assignment_id DESC)` to select the latest eligible assignment.
- Fact loading resolves the employee SCD2 version with `review_date >= start_date` and `end_date IS NULL OR review_date < end_date`.
- `src/managers.py`: `AnalyticsManager.get_top_performers()` uses an `employee_scores` CTE and `DENSE_RANK() OVER (PARTITION BY department_name ORDER BY overall_score DESC)`.
- No database views are implemented.
- `EmployeeManager._apply_scd2_change()` directly closes the current dimension row, updates OLTP employee data, inserts a new current dimension row, and commits the transaction.

### f) OLAP data warehouse

The warehouse tables are in the same `employee_analytics` schema; no separate warehouse schema exists.

- `dim_department`: surrogate PK `department_key`; business key `department_id`; department name.
- `dim_employee`: surrogate PK `employee_key`; business key `employee_id`; FK `department_key`; SCD2 columns `start_date`, `end_date`, `is_current`; employee attributes, salary, performance score, and attrition risk.
- `dim_project`: surrogate PK `project_key`; business key `project_id`; FK `department_key`; project name.
- `dim_date`: PK `date_key`; unique `full_date`; year, quarter, month, and day attributes.
- `fact_performance_reviews`: surrogate PK `fact_review_key`; unique `review_id`; FKs `employee_key`, `department_key`, `project_key`, and `date_key`; measures/descriptors `overall_score`, `rating`, `review_date`, and `employee_id`.
- Diagram representation: `src/database/dimensional_model.mmd`.

### g) Backend application code

- `src/database/db_manager.py`: `DatabaseConnection` is a per-class singleton registry using `_instances`; it manages `mysql.connector` connections, execution, fetches, rollback, and close operations.
- `src/models.py`: dataclasses `Employee`, `Project`, and `Review` with validation methods.
- `src/managers.py`: all manager classes inherit from `DatabaseConnection`.
- `EmployeeManager`: `list_departments()`, `create_employee()`, `update_department()`, `update_salary()`, `_apply_scd2_change()`, and `list_employees()`; touches OLTP departments/employees and warehouse department/employee dimensions.
- `ProjectManager`: `create_project()` and `assign_employee()`; touches `projects` and `project_assignments`.
- `ReviewManager`: `create_review()`; touches `performance_reviews`.
- `AnalyticsManager`: `get_performance_trends()`, `get_top_performers()`, and `get_attrition_risk()`; reads fact and dimension tables.
- Database operations use exception handling, rollback, commit, and re-raise behavior.

### h) Streamlit frontend

- Entry point: `src/streamlit_app.py`.
- Shared presentation layer: `src/ui/theme.py` and `src/ui/__init__.py`; contains V4C color tokens, CSS, page headers, KPI cards, status badges, info pills, score bands, and Plotly styling.
- Overview: local CSV metrics, department count, MySQL/local status, average score, and employees-by-department chart; calls `EmployeeManager.list_departments()` for connectivity status.
- Employee Onboarding: form using `Employee` and `EmployeeManager.create_employee()`; writes to OLTP and creates the current warehouse version through manager logic.
- Project Management: Create Project and Assign Employee tabs using `Project` and `ProjectManager`; writes to `projects` and `project_assignments`.
- Performance Reviews: form using `Review` and `ReviewManager.create_review()`; writes to `performance_reviews`.
- Analytics Dashboard: calls `AnalyticsManager`; shows year-over-year review score, top performers, and attrition risk charts; supports department-at-review and current-department attribution.
- Local fallback: `load_local_data()` and `local_analytics()` read the three CSV files when analytics queries are unavailable or empty. No local fallback exists for writes.

### i) Configuration and secrets

- `src/config/settings.py`: calls `load_dotenv()` and reads `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME`, with defaults.
- `.streamlit/config.toml`: Streamlit dark theme and V4C primary/background colors.
- `.gitignore`: ignores `.env`, virtual environments, and Python cache files.
- No `st.secrets` usage exists in the code. README documentation mentions Streamlit Cloud secrets.

### j) Version control and CI

- Visible branches: `main`, `Shraddha`, `roshan`; remotes include `origin/main`, `origin/Shraddha`, and `origin/roshan`.
- Recent commits include `fb6e961 Streamlit UI Updated` and `7fdbfa1 Updated code (#1)`.
- No `.github` directory or GitHub Actions workflows exist.
- No automated CI configuration is implemented.

### k) Deployment

- README specifies Python 3.10 or newer and MySQL 8.0 or newer.
- Dependencies are declared in `requirements.txt`.
- Application command: `streamlit run src/streamlit_app.py`.
- Streamlit Community Cloud deployment is documented in `README.md`, but there is no cloud manifest, infrastructure-as-code, hosted database configuration, or deployment settings file.

## 3. DATA FLOW

1. `DataSynthesizer.generate_base_employee_data()` creates the employee snapshot in `src/ETL/synthesizer.py`.
2. `generate_scd_type_2_history()` creates current and historical employee versions.
3. `generate_performance_reviews()` creates one synthetic review per employee.
4. `export_to_csv()` writes the three CSV files under `src/data/`.
5. `src/run_etl.py` constructs `DataWarehouseLoader`.
6. `CSVExtractor.extract()` reads and parses the CSV files.
7. `DataTransformer.build_employee_history()` validates and enriches SCD2 records.
8. `_load_departments()` upserts `departments` and `dim_department`.
9. `_load_oltp_employees()` upserts `employees`.
10. `_load_oltp_reviews()` upserts `performance_reviews`.
11. `_load_employee_versions()` upserts `dim_employee` SCD2 rows.
12. `load_review_facts()` populates `dim_date`.
13. `load_review_facts()` populates `dim_project`.
14. The `ranked_assignments` CTE selects the latest eligible assignment for each review.
15. `load_review_facts()` inserts or updates `fact_performance_reviews` and resolves the effective employee version by review date.
16. Streamlit calls `AnalyticsManager` for warehouse analytics.
17. `get_performance_trends()` reads yearly aggregates from `fact_performance_reviews`.
18. `get_top_performers()` joins facts to `dim_employee` and `dim_department` using effective-date or current-version attribution.
19. `get_attrition_risk()` aggregates current `dim_employee` records by department.
20. When analytics queries are unavailable or empty, `local_analytics()` calculates dashboard data from local CSVs.

## 4. NODES AND EDGES FOR THE DIAGRAM

### a) Nodes

| id            | label                            | layer                       | type     | technology                   |
| ------------- | -------------------------------- | --------------------------- | -------- | ---------------------------- |
| SRC_EMP       | Synthetic employee snapshot      | Sources                     | source   | CSV                          |
| SRC_SCD       | Employee SCD2 history            | Sources                     | source   | CSV                          |
| SRC_REV       | Synthetic performance reviews    | Sources                     | source   | CSV                          |
| SRC_ENV       | `.env` / environment variables   | Cross-cutting               | config   | python-dotenv                |
| GEN           | DataSynthesizer                  | Sources                     | process  | Python, Faker, NumPy, pandas |
| EXTRACT       | CSVExtractor                     | Ingest                      | process  | Python, pandas               |
| VALIDATE      | DataTransformer                  | Ingest                      | process  | Python, pandas               |
| LOADER        | DataWarehouseLoader              | Ingest                      | process  | Python, mysql-connector      |
| BRONZE        | File-based pre-load layer        | Staging (Bronze)            | source   | CSV                          |
| DB            | `employee_analytics`             | OLTP (Silver) / OLAP (Gold) | database | MySQL                        |
| OLTP_DEPT     | `departments`                    | OLTP (Silver)               | database | MySQL                        |
| OLTP_EMP      | `employees`                      | OLTP (Silver)               | database | MySQL                        |
| OLTP_PROJ     | `projects`                       | OLTP (Silver)               | database | MySQL                        |
| OLTP_ASSIGN   | `project_assignments`            | OLTP (Silver)               | database | MySQL                        |
| OLTP_REV      | `performance_reviews`            | OLTP (Silver)               | database | MySQL                        |
| ETL_DATE      | Date dimension load              | ETL                         | process  | SQL issued by Python         |
| ETL_PROJ      | Project dimension load           | ETL                         | process  | SQL issued by Python         |
| ETL_FACT      | Performance fact load            | ETL                         | process  | SQL, CTE, `ROW_NUMBER()`     |
| ETL_SCD       | SCD2 employee load/update        | ETL                         | process  | Python, SQL                  |
| PROC_SCD      | `sp_close_employee_scd2_version` | ETL                         | process  | MySQL stored procedure       |
| DIM_DEPT      | `dim_department`                 | OLAP (Gold)                 | database | MySQL                        |
| DIM_EMP       | `dim_employee`                   | OLAP (Gold)                 | database | MySQL                        |
| DIM_PROJ      | `dim_project`                    | OLAP (Gold)                 | database | MySQL                        |
| DIM_DATE      | `dim_date`                       | OLAP (Gold)                 | database | MySQL                        |
| FACT_REV      | `fact_performance_reviews`       | OLAP (Gold)                 | database | MySQL                        |
| DB_CONN       | `DatabaseConnection`             | Application/Serve           | service  | Python, mysql-connector      |
| MAN_EMP       | `EmployeeManager`                | Application/Serve           | service  | Python                       |
| MAN_PROJ      | `ProjectManager`                 | Application/Serve           | service  | Python                       |
| MAN_REV       | `ReviewManager`                  | Application/Serve           | service  | Python                       |
| MAN_ANALYTICS | `AnalyticsManager`               | Application/Serve           | service  | Python, SQL                  |
| UI            | Streamlit application            | Application/Serve           | ui       | Streamlit, Plotly            |
| UI_LOCAL      | Local analytics fallback         | Application/Serve           | service  | pandas                       |
| CONSUMER_USER | End user                         | Consumers                   | ui       | Browser                      |
| GIT           | Git branches and commits         | Cross-cutting               | devops   | Git                          |
| CONFIG        | Streamlit theme configuration    | Cross-cutting               | config   | TOML                         |
| CLOUD         | Streamlit Community Cloud        | Cross-cutting               | service  | Documented only              |

`BRONZE` is a logical file-based node; no physical Bronze database or table is implemented.

### b) Edges

```text
GEN -> SRC_EMP : writes employee CSV
GEN -> SRC_SCD : writes SCD2 history CSV
GEN -> SRC_REV : writes review CSV
SRC_EMP -> EXTRACT : read CSV
SRC_SCD -> EXTRACT : read CSV
SRC_REV -> EXTRACT : read CSV
EXTRACT -> VALIDATE : parsed DataFrames
VALIDATE -> LOADER : validated employee versions
LOADER -> OLTP_DEPT : upsert departments
LOADER -> OLTP_EMP : batch upsert employees
LOADER -> OLTP_REV : batch upsert reviews
LOADER -> DIM_DEPT : upsert department dimension
LOADER -> ETL_DATE : populate date dimension
LOADER -> ETL_PROJ : populate project dimension
LOADER -> ETL_FACT : populate performance facts
LOADER -> ETL_SCD : populate employee versions
ETL_SCD -> DIM_EMP : insert/update SCD2 versions
ETL_DATE -> DIM_DATE : insert date records
ETL_PROJ -> DIM_PROJ : insert project records
ETL_FACT -> FACT_REV : insert/update review facts
ETL_FACT -> DIM_EMP : effective-date lookup
ETL_FACT -> DIM_PROJ : project lookup
ETL_FACT -> DIM_DATE : date-key lookup
PROC_SCD -> DIM_EMP : close current version
ETL_SCD -> PROC_SCD : procedure exists but is not invoked by loader
DB_CONN -> OLTP_DEPT : connection/query
MAN_EMP -> DB_CONN : employee operations
MAN_EMP -> OLTP_EMP : create/update employees
MAN_EMP -> DIM_EMP : SCD2 updates
MAN_PROJ -> OLTP_PROJ : create projects
MAN_PROJ -> OLTP_ASSIGN : assign employees
MAN_REV -> OLTP_REV : create reviews
MAN_ANALYTICS -> FACT_REV : query trends
MAN_ANALYTICS -> DIM_EMP : query employee versions
MAN_ANALYTICS -> DIM_DEPT : query departments
UI -> MAN_EMP : onboarding and department lookup
UI -> MAN_PROJ : project and assignment forms
UI -> MAN_REV : review form
UI -> MAN_ANALYTICS : analytics queries
UI -> UI_LOCAL : fallback when analytics unavailable
UI_LOCAL -> SRC_EMP : read local snapshot
UI_LOCAL -> SRC_SCD : read local history
UI_LOCAL -> SRC_REV : read local reviews
SRC_ENV -> DB_CONN : database credentials
CONFIG -> UI : Streamlit theme configuration
GIT -> UI : source versioning
GIT -> GEN : source versioning
GIT -> LOADER : source versioning
GIT -> DB : schema source versioning
CLOUD -> UI : documented deployment target
CONSUMER_USER -> UI : browser access
```

## 5. GAPS AND DISCREPANCIES

- **100,000+ synthetic rows with Faker and SCD2 history: IMPLEMENTED.** Default generator creates 100,000 employees and 30% historical versions; generated files are committed under `src/data`.
- **Staging, OLTP, and OLAP schemas in MySQL: PARTIAL.** OLTP and OLAP tables exist in the same `employee_analytics` database; no separate staging/Bronze MySQL schema or tables exist.
- **Star schema and surrogate keys: IMPLEMENTED.** Required fact and dimension tables, surrogate keys, and foreign keys exist in `src/database/schema.sql`.
- **Stored procedures: PARTIAL.** `sp_close_employee_scd2_version` exists, but the Python SCD2 path performs updates directly rather than calling it.
- **Views: NOT IMPLEMENTED.** No SQL views are defined.
- **CTEs and window functions: IMPLEMENTED.** `ranked_assignments` uses `ROW_NUMBER()` and `get_top_performers()` uses CTEs and `DENSE_RANK()`.
- **OOP backend: IMPLEMENTED.** Entity dataclasses, database connection class, managers, validation, transactions, rollbacks, and exception handling exist.
- **Singleton `DatabaseConnection`: PARTIAL.** The singleton registry is keyed by subclass, so each manager subclass has its own singleton instance rather than all managers sharing one instance.
- **Streamlit forms: IMPLEMENTED.** Employee onboarding, project creation, employee assignment, and performance review forms exist.
- **Department change triggering SCD2: PARTIAL.** `EmployeeManager.update_department()` and `_apply_scd2_change()` implement it, but the current Streamlit UI has no department-change form.
- **Analytics dashboard: PARTIAL.** Year-over-year trend, top performers, attrition risk, and department attribution exist; project bottleneck/allocation analytics do not.
- **Project allocation reporting: PARTIAL.** Assignments can be created and selected during fact loading, but no dedicated allocation or bottleneck dashboard exists.
- **GitHub feature branches and PRs: PARTIAL.** Branches and remotes exist, and a commit references `#1`; repository PR metadata and workflow configuration are absent.
- **GitHub Actions CI: NOT IMPLEMENTED.** No `.github` directory or workflow files exist.
- **Streamlit Cloud deployment: PARTIAL.** README documentation exists, but no deployment manifest, infrastructure code, hosted database configuration, or cloud settings file exists.
- **`st.secrets` support: NOT IMPLEMENTED.** Runtime code reads `.env` or shell variables only.
- **Separate OLTP and OLAP schemas: NOT IMPLEMENTED.** Both groups are created in one MySQL schema.

## 6. ASSUMPTIONS OR UNCERTAINTIES

- No live MySQL instance or connection configuration is included, so database availability and deployed row counts cannot be verified from code inspection.
- README Streamlit Cloud deployment text is documentation, not evidence of an actual deployment.
- Git hosting PR details cannot be confirmed locally; only branches and commit messages are visible.
- SQLAlchemy, openpyxl, and related declared dependencies are not shown participating in the active application data flow.
- The stored procedure is defined in the schema, but its deployment and execution status in a live database cannot be confirmed.
- Local analytics fallback depends on the CSV files being present and matching the current code expectations.
- There is no separate Bronze database layer; the Bronze swimlane should represent file-based pre-load storage.
