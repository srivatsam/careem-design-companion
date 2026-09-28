import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("DATABASE_PATH", str(ROOT / "data" / "test.db"))
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "1000000")
