"""Create/upgrade the database to the latest migration.  Usage: python scripts/init_db.py (from backend/)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import get_settings  # noqa: E402
from app.database.migrate import run_migrations  # noqa: E402

if __name__ == "__main__":
    s = get_settings()
    run_migrations(s.database_url)
    print("Database is at the latest migration:", s.database_url)
