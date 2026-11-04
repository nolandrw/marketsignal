"""Conservative, durable USD ceiling for opt-in text-only model experiments.

Reservations are charged *before* a request. A crash, timeout, or response
without trustworthy usage retains the full reservation. One SQLite ledger is
shared across processes and cases; no network call can reset its budget.

This is an application-level guard, not a substitute for an account/project
billing limit at the provider. Recheck the published price card before use.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path


MICRO = Decimal("1000000")
PRICE_CARD = {
    # OpenAI official model page, checked 2026-11-04; USD per 1M tokens.
    "gpt-5-mini": {"input": Decimal("0.25"),
                   "cached_input": Decimal("0.025"),
                   "output": Decimal("2.00")},
}


class ModelBudgetExceeded(RuntimeError):
    """Request refused before billing, or conservative usage guard failed."""


def _micro_usd(model: str, *, input_tokens: int, output_tokens: int,
               cached_tokens: int = 0) -> int:
    if (model not in PRICE_CARD or any(type(value) is not int or value < 0
                                      for value in (input_tokens, output_tokens, cached_tokens)) or
            cached_tokens > input_tokens):
        raise ValueError("Unknown model or invalid token usage")
    rates = PRICE_CARD[model]
    dollars = ((input_tokens - cached_tokens) * rates["input"] +
               cached_tokens * rates["cached_input"] +
               output_tokens * rates["output"]) / MICRO
    return int((dollars * MICRO).to_integral_value(rounding=ROUND_CEILING))


def estimate_pilot_cost(*, model: str = "gpt-5-mini", cases: int = 4,
                        calls_per_case: int = 5, input_tokens_per_call: int = 10000,
                        output_tokens_per_call: int = 2400) -> dict:
    if not 1 <= cases <= 100 or not 1 <= calls_per_case <= 20:
        raise ValueError("Unbounded pilot size")
    price = _micro_usd(model, input_tokens=input_tokens_per_call,
                       output_tokens=output_tokens_per_call)
    return {"model": model, "cases": cases, "calls_per_case": calls_per_case,
            "total_calls": cases * calls_per_case,
            "illustrative_input_tokens_per_call": input_tokens_per_call,
            "illustrative_output_tokens_per_call": output_tokens_per_call,
            "estimated_usd": round(price * cases * calls_per_case / 1_000_000, 6),
            "type": "illustrative_not_a_provider_invoice"}


class ModelBudget:
    """Shared per-experiment budget, with pessimistic pre-request reserves."""

    def __init__(self, path: str | Path, max_usd: str, *, model: str = "gpt-5-mini"):
        self.path = Path(path)
        if (self.path.suffix != ".sqlite" or "private" not in self.path.parts or
                any(part in {"site", "archive", "docs", "tests", "examples"}
                    for part in self.path.parts) or model not in PRICE_CARD):
            raise ValueError("Budget requires a private SQLite path and priced model")
        try:
            ceiling = Decimal(str(max_usd))
            if not ceiling.is_finite() or not Decimal("0.01") <= ceiling <= Decimal("1000"):
                raise ValueError("Budget must be between $0.01 and $1000")
            self.max_micro = int((ceiling * MICRO).to_integral_value(rounding=ROUND_CEILING))
        except (InvalidOperation, TypeError):
            raise ValueError("Invalid USD budget") from None
        self.model = model
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS budget
                (id INTEGER PRIMARY KEY CHECK(id=1), model TEXT NOT NULL,
                 max_micro INTEGER NOT NULL,
                 used_micro INTEGER NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS model_calls
                (id INTEGER PRIMARY KEY AUTOINCREMENT, model TEXT NOT NULL,
                 reserved_micro INTEGER NOT NULL, charged_micro INTEGER,
                 status TEXT NOT NULL)""")
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT model,max_micro FROM budget WHERE id=1").fetchone()
            if existing is None:
                db.execute("INSERT INTO budget(id,model,max_micro,used_micro) VALUES(1,?,?,0)",
                           (self.model, self.max_micro))
            elif existing != (self.model, self.max_micro):
                raise ValueError("Existing budget model/ceiling cannot silently change")

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def reserve(self, *, request_bytes: int, max_output_tokens: int) -> int:
        """Debit an intentionally oversized input+output estimate before API I/O.

        4 tokens/serialized UTF-8 byte plus 8192 protocol-overhead tokens is
        deliberately pessimistic for text-only requests. Provider-side costs
        can still differ; use a provider project limit as a second defense.
        """
        if (type(request_bytes) is not int or not 1 <= request_bytes <= 100000 or
                type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 5000):
            raise ValueError("Invalid bounded model request")
        reserved = _micro_usd(self.model, input_tokens=4 * request_bytes + 8192,
                              output_tokens=max_output_tokens)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            used, limit = db.execute("SELECT used_micro,max_micro FROM budget WHERE id=1").fetchone()
            if used + reserved > limit:
                raise ModelBudgetExceeded("Model experiment USD ceiling reached")
            db.execute("UPDATE budget SET used_micro=used_micro+? WHERE id=1", (reserved,))
            cursor = db.execute("""INSERT INTO model_calls(model,reserved_micro,status)
                                   VALUES(?,?,'reserved')""", (self.model, reserved))
            return cursor.lastrowid

    def settle(self, call_id: int, usage: dict | None) -> None:
        """Refund unused reservation only when usage is complete and valid."""
        if not isinstance(usage, dict):
            return  # Missing usage could still have been billed.
        try:
            input_tokens = usage["input_tokens"]
            output_tokens = usage["output_tokens"]
            details = usage.get("input_tokens_details") or {}
            cached = details.get("cached_tokens", 0)
            actual = _micro_usd(self.model, input_tokens=input_tokens,
                                output_tokens=output_tokens, cached_tokens=cached)
        except (KeyError, TypeError, ValueError, AttributeError):
            return
        exceeds_reservation = False
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT reserved_micro,status FROM model_calls WHERE id=?",
                             (call_id,)).fetchone()
            if row is None or row[1] != "reserved":
                raise ModelBudgetExceeded("Invalid or already settled model reservation")
            reserved = row[0]
            if actual > reserved:
                db.execute("UPDATE model_calls SET status='provider_usage_over_reserve' WHERE id=?",
                           (call_id,))
                # Keep the full reservation; a charge larger than our assumed
                # maximum indicates the pricing/input estimate is wrong.
                exceeds_reservation = True
            else:
                db.execute("UPDATE budget SET used_micro=used_micro-? WHERE id=1",
                           (reserved - actual,))
                db.execute("""UPDATE model_calls SET charged_micro=?,status='settled'
                              WHERE id=?""", (actual, call_id))
        if exceeds_reservation:
            raise ModelBudgetExceeded("Provider usage exceeded conservative reserve")

    def summary(self) -> dict:
        with self._connect() as db:
            used, limit = db.execute("SELECT used_micro,max_micro FROM budget WHERE id=1").fetchone()
            calls = db.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0]
        return {"model": self.model, "budget_usd": round(limit / 1_000_000, 6),
                "debited_usd": round(used / 1_000_000, 6),
                "remaining_usd": round((limit - used) / 1_000_000, 6),
                "attempted_calls": calls,
                "unverified_response_reservations_remain_charged": True}
