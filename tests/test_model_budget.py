"""No-network regression checks for the four-case model-spend guard."""

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

from marketsignal.cli import main
from marketsignal.model_budget import (
    ModelBudget, ModelBudgetExceeded, estimate_pilot_cost,
)
from marketsignal.model_gateway import ModelUnavailable, ResponsesJSONModel


class FakeResponse(io.BytesIO):
    status = 200


class ModelBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "private" / "budget.sqlite"

    def test_zero_cost_four_case_estimate(self):
        estimate = estimate_pilot_cost()
        self.assertEqual(estimate["total_calls"], 20)
        self.assertEqual(estimate["estimated_usd"], 0.25)
        self.assertEqual(main(["model-budget-estimate", "--cases", "4"]), 0)

    def test_settlement_refunds_to_actual_and_persists_across_instances(self):
        first = ModelBudget(self.db, "0.25")
        reservation = first.reserve(request_bytes=500, max_output_tokens=1000)
        self.assertGreater(first.summary()["debited_usd"], 0)
        first.settle(reservation, {"input_tokens": 750, "output_tokens": 100,
                                   "input_tokens_details": {"cached_tokens": 250}})
        second = ModelBudget(self.db, "0.25")
        # 500 uncached input, 250 cached, 100 output = $0.00033125.
        self.assertEqual(second.summary()["debited_usd"], 0.000332)
        self.assertEqual(second.summary()["attempted_calls"], 1)
        with self.assertRaises(ModelBudgetExceeded):
            second.settle(reservation, {"input_tokens": 1, "output_tokens": 1})

    def test_shared_ceiling_blocks_before_another_call(self):
        first = ModelBudget(self.db, "0.01")
        first.reserve(request_bytes=1000, max_output_tokens=2400)
        second = ModelBudget(self.db, "0.01")
        with self.assertRaises(ModelBudgetExceeded):
            second.reserve(request_bytes=1000, max_output_tokens=2400)
        self.assertEqual(first.summary()["attempted_calls"], 1)
        with self.assertRaises(ValueError):
            ModelBudget(self.db, "0.02")

    def test_missing_or_unusable_usage_keeps_full_reservation(self):
        budget = ModelBudget(self.db, "0.25")
        ticket = budget.reserve(request_bytes=1000, max_output_tokens=2400)
        before = budget.summary()["debited_usd"]
        budget.settle(ticket, None)
        budget.settle(ticket, {"input_tokens": "bad", "output_tokens": 1})
        self.assertEqual(budget.summary()["debited_usd"], before)

    def test_provider_usage_over_reservation_is_logged_and_fail_closed(self):
        budget = ModelBudget(self.db, "0.25")
        ticket = budget.reserve(request_bytes=1000, max_output_tokens=100)
        before = budget.summary()["debited_usd"]
        with self.assertRaises(ModelBudgetExceeded):
            budget.settle(ticket, {"input_tokens": 10000000, "output_tokens": 1})
        self.assertEqual(budget.summary()["debited_usd"], before)

    def test_unpriced_model_and_public_path_rejected(self):
        with self.assertRaises(ValueError):
            ModelBudget(self.db, "0.25", model="made-up-model")
        with self.assertRaises(ValueError):
            ModelBudget(Path(self.temp.name) / "docs" / "budget.sqlite", "0.25")

    def test_model_gateway_reserves_before_http_and_settles(self):
        budget = ModelBudget(self.db, "0.25")
        response = {"status": "completed", "output": [{"content": [
            {"type": "output_text", "text": json.dumps({"result": "ok"})}]}],
            "usage": {"input_tokens": 300, "output_tokens": 20}}
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only-dummy"}):
            gateway = ResponsesJSONModel(budget=budget)
        with patch("marketsignal.model_gateway.urlopen",
                   return_value=FakeResponse(json.dumps(response).encode())) as fake_http:
            value = gateway.complete("topic_lead", {"test": True})
        self.assertEqual(value, {"result": "ok"})
        self.assertEqual(fake_http.call_count, 1)
        request_payload = json.loads(fake_http.call_args.args[0].data)
        self.assertEqual(request_payload["reasoning"], {"effort": "low"})
        self.assertEqual(request_payload["max_output_tokens"], 5000)
        self.assertEqual(budget.summary()["debited_usd"], 0.000115)

    def test_model_gateway_rejects_before_http_when_cap_exhausted(self):
        budget = ModelBudget(self.db, "0.01")
        budget.reserve(request_bytes=1000, max_output_tokens=2400)
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only-dummy"}):
            gateway = ResponsesJSONModel(budget=budget)
        with patch("marketsignal.model_gateway.urlopen") as fake_http:
            with self.assertRaises(ModelBudgetExceeded):
                gateway.complete("topic_lead", {"test": True})
        fake_http.assert_not_called()

    def test_provider_http_status_is_safe_without_response_body(self):
        budget = ModelBudget(self.db, "0.25")
        secret_body = b"secret provider error response"
        error = HTTPError("https://api.openai.com/v1/responses", 400,
                          "invalid request", {}, io.BytesIO(secret_body))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only-dummy"}):
            gateway = ResponsesJSONModel(budget=budget)
        with patch("marketsignal.model_gateway.urlopen", side_effect=error):
            with self.assertRaises(ModelUnavailable) as raised:
                gateway.complete("topic_lead", {"test": True})
        self.assertEqual(raised.exception.diagnostic_code, "provider_http_400")
        self.assertNotIn("secret", str(raised.exception))
        self.assertEqual(budget.summary()["attempted_calls"], 1)

    def test_incomplete_model_response_reports_safe_token_limit_reason(self):
        budget = ModelBudget(self.db, "0.25")
        response = {"status": "incomplete", "incomplete_details": {
            "reason": "max_output_tokens", "private_debug": "secret response text"},
            "output": [], "usage": {"input_tokens": 300, "output_tokens": 2400}}
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only-dummy"}):
            gateway = ResponsesJSONModel(budget=budget)
        with patch("marketsignal.model_gateway.urlopen",
                   return_value=FakeResponse(json.dumps(response).encode())):
            with self.assertRaises(ModelUnavailable) as raised:
                gateway.complete("topic_lead", {"test": True})
        self.assertEqual(raised.exception.diagnostic_code,
                         "response_incomplete_max_output_tokens")
        self.assertNotIn("secret", str(raised.exception))
        self.assertEqual(budget.summary()["attempted_calls"], 1)
        # Incomplete responses can still carry authoritative usage numbers.
        # They must be recorded rather than left as pessimistic reservations.
        self.assertEqual(budget.summary()["debited_usd"], 0.004875)


if __name__ == "__main__":
    unittest.main()
