"""Delete evidence older than OMNI_EVIDENCE_RETENTION_DAYS (default 30). Safe to re-run; run daily (cron / Task Scheduler).
Usage (from backend/):  python ../scripts/cleanup_evidence.py
Use the retention period your institution approves; this tool only enforces it."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import get_settings  # noqa: E402
from app.database.migrate import run_migrations  # noqa: E402
from app.database.session import make_engine, make_sessionmaker  # noqa: E402
from app.evidence.service import EvidenceService  # noqa: E402

s = get_settings()
run_migrations(s.database_url)
engine = make_engine(s.database_url)
print(EvidenceService(make_sessionmaker(engine), s).cleanup(), f"(retention {s.evidence_retention_days} days)")
