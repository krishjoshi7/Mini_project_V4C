from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class DatabaseSettings:
	host: str = os.getenv("DB_HOST", "localhost")
	port: int = int(os.getenv("DB_PORT", "3306"))
	user: str = os.getenv("DB_USER", "root")
	password: str = os.getenv("DB_PASSWORD", "")
	database: str = os.getenv("DB_NAME", "employee_analytics")


settings = DatabaseSettings()
