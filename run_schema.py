from pathlib import Path
from dotenv import load_dotenv
import os
import pymysql

# Load .env (checks Mini_project_V4C/.env then parent dir)
load_dotenv()
if not os.getenv("DB_HOST"):
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

host = os.getenv("DB_HOST", "localhost")
port = int(os.getenv("DB_PORT", 3306))
user = os.getenv("DB_USER", "root")
password = os.getenv("DB_PASSWORD", "")

print(f"Connecting to MySQL at {host}:{port} as user '{user}'...")
conn = pymysql.connect(
    host=host,
    port=port,
    user=user,
    password=password,
)

schema_path = Path(__file__).resolve().parent / "src" / "database" / "schema.sql"
schema_sql = schema_path.read_text(encoding="utf-8")


def parse_sql_script(sql_text: str) -> list[str]:
    """Parse SQL script handling DELIMITER directives and skipping comments."""
    delimiter = ";"
    statements: list[str] = []
    current_lines: list[str] = []

    for line in sql_text.splitlines():
        trimmed = line.strip()

        # Handle DELIMITER change command (e.g. DELIMITER $$, DELIMITER ;)
        if trimmed.upper().startswith("DELIMITER"):
            parts = trimmed.split()
            if len(parts) >= 2:
                delimiter = parts[1].strip()
            continue

        # Skip standalone comment lines when outside a statement
        if trimmed.startswith("--") and not current_lines:
            continue

        current_lines.append(line)

        # Statement boundary reached
        if trimmed.endswith(delimiter):
            stmt_text = "\n".join(current_lines).rstrip()
            if stmt_text.endswith(delimiter):
                stmt_text = stmt_text[:-len(delimiter)]

# regular statements (before DELIMITER $$)
cursor = conn.cursor()

try:
    for stmt in statements:
        cursor.execute(stmt)
        print(f"  ✔ {stmt[:80]}...")
conn.commit()

#  stored procedure blocks 
if len(parts) > 1:
    for proc_block in parts[1:]:
        proc_block = proc_block.replace("DELIMITER ;", "")
        for proc in proc_block.split("$$"):
            stmt = proc.strip()
            if stmt:
                cursor.execute(stmt)
                print(f"  ✔ {stmt[:80]}...")
    conn.commit()

cursor.close()
conn.close()
print("\n Schema created successfully!")
