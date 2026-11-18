"""Global daily budgets for paid/limited upstream APIs.

Counters reset at 00:00 UTC and are persisted to disk so a restart doesn't
hand out a fresh budget.
"""
import json
import os
import threading
from datetime import datetime, timezone

from ..config import CACHE_DIR, GEMINI_DAILY_LIMIT, AV_DAILY_LIMIT, FILING_INGEST_DAILY_LIMIT


class QuotaExceeded(Exception):
    def __init__(self, name: str):
        super().__init__(f"Daily {name} budget for this demo has been used up. It resets at 00:00 UTC.")
        self.name = name


class DailyBudget:
    def __init__(self, name: str, limit: int):
        self.name = name
        self.limit = limit
        self._lock = threading.Lock()
        self._path = os.path.join(CACHE_DIR, f"quota_{name}.json")
        self._day, self._used = self._load()

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _load(self):
        try:
            with open(self._path, "r") as f:
                data = json.load(f)
            return data["day"], int(data["used"])
        except (OSError, ValueError, KeyError):
            return self._today(), 0

    def _save(self):
        try:
            with open(self._path, "w") as f:
                json.dump({"day": self._day, "used": self._used}, f)
        except OSError:
            pass

    def _roll(self):
        today = self._today()
        if today != self._day:
            self._day, self._used = today, 0

    def try_consume(self, n: int = 1) -> bool:
        with self._lock:
            self._roll()
            if self._used + n > self.limit:
                return False
            self._used += n
            self._save()
            return True

    def consume(self, n: int = 1) -> None:
        if not self.try_consume(n):
            raise QuotaExceeded(self.name)

    def remaining(self) -> int:
        with self._lock:
            self._roll()
            return max(0, self.limit - self._used)

    def snapshot(self) -> dict:
        return {"limit": self.limit, "remaining": self.remaining()}


gemini_budget = DailyBudget("gemini", GEMINI_DAILY_LIMIT)
alpha_vantage_budget = DailyBudget("alpha_vantage", AV_DAILY_LIMIT)
filing_budget = DailyBudget("filing_ingest", FILING_INGEST_DAILY_LIMIT)
