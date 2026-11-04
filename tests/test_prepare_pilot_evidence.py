"""Preparation must record real quotes and keep research packets private."""

import io
import json
import time
import unittest
from unittest.mock import patch

from marketsignal.models import Market
from scripts import prepare_pilot_evidence as prep


class Response(io.BytesIO):
    def __init__(self, data):
        super().__init__(json.dumps(data).encode())
        self.headers = {"Content-Type": "application/json"}


class PilotPreparationTests(unittest.TestCase):
    def test_public_api_quote_requires_same_frozen_market_and_token(self):
        before = Market("market1", "event1", "Original event", "event-slug",
                        "A specific market question?", "123456", 0.4,
                        100_000, 100_000, "")
        data = {"id": "market1", "question": before.question,
                "active": True, "closed": False,
                "outcomes": '["Yes", "No"]', "outcomePrices": '["0.62", "0.38"]',
                "clobTokenIds": '["123456", "7890"]', "volume24hr": 140_000,
                "liquidityNum": 110_000, "description": "Original explicit resolution terms."}
        with patch.object(prep, "urlopen", return_value=Response(data)):
            current, as_of, description = prep._live_market("market1", before)
        self.assertEqual(current.yes_price, 0.62)
        self.assertEqual(current.yes_token_id, before.yes_token_id)
        self.assertLessEqual(abs(as_of - int(time.time())), 3)
        self.assertEqual(description, "Original explicit resolution terms.")
        with patch.object(prep, "urlopen", return_value=Response({**data,
                                                            "clobTokenIds": '["999", "7890"]'})):
            with self.assertRaisesRegex(ValueError, "outcome token"):
                prep._live_market("market1", before)

    def test_fixed_case_registry_has_only_approved_original_hosts(self):
        self.assertEqual(set(prep.SOURCES), set(prep.EXPECTED_IDS))
        self.assertTrue(all(url.startswith("https://") for values in prep.SOURCES.values()
                            for url in values))


if __name__ == "__main__":
    unittest.main()
