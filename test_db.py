from src.database.db_manager import DatabaseConnection


db = DatabaseConnection()

result = db.fetch_one(
    "SELECT DATABASE() AS database_name"
)

print("Connected database:", result["database_name"])