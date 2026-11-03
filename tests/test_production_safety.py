"""Tests that do not require cloud credentials or a real PostgreSQL server."""

from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from marketsignal.postgres import PostgresStorage, open_storage
from marketsignal.storage import Storage


class DeploymentSafetyTests(unittest.TestCase):
    def test_cloud_mode_refuses_sqlite_fallback(self):
        with patch.dict(os.environ, {"REQUIRE_PERSISTENT_DB": "1"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "Refusing ephemeral SQLite"):
                open_storage("/tmp/unused.db")

    def test_local_mode_uses_sqlite(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {}, clear=True):
                with open_storage(str(Path(directory) / "local.db")) as store:
                    self.assertIsInstance(store, Storage)

    def test_worker_connection_never_runs_schema_creation(self):
        fake_pg = types.ModuleType("psycopg")
        fake_pg_rows = types.ModuleType("psycopg.rows")
        fake_pg_rows.dict_row = object()
        connection = MagicMock()
        fake_pg.connect = MagicMock(return_value=connection)
        with patch.dict(sys.modules, {"psycopg": fake_pg, "psycopg.rows": fake_pg_rows}):
            with PostgresStorage("postgresql://example.invalid/db"):
                pass
        connection.execute.assert_not_called()
        connection.close.assert_called_once()

    def test_schema_creation_requires_explicit_init(self):
        fake_pg = types.ModuleType("psycopg")
        fake_pg_rows = types.ModuleType("psycopg.rows")
        fake_pg_rows.dict_row = object()
        connection = MagicMock()
        fake_pg.connect = MagicMock(return_value=connection)
        with patch.dict(sys.modules, {"psycopg": fake_pg, "psycopg.rows": fake_pg_rows}):
            with PostgresStorage("postgresql://example.invalid/db", initialize=True):
                pass
        self.assertGreater(connection.execute.call_count, 5)
        executed = "\n".join(args[0][0] for args in connection.execute.call_args_list)
        self.assertIn("ENABLE ROW LEVEL SECURITY", executed)

    def test_connection_failure_does_not_echo_secret(self):
        fake_pg = types.ModuleType("psycopg")
        fake_pg_rows = types.ModuleType("psycopg.rows")
        fake_pg_rows.dict_row = object()
        fake_pg.connect = MagicMock(side_effect=ValueError("password=classified-secret"))
        with patch.dict(sys.modules, {"psycopg": fake_pg, "psycopg.rows": fake_pg_rows}):
            with self.assertRaises(RuntimeError) as error:
                PostgresStorage("postgresql://user:classified-secret@example.invalid/db")
        self.assertIn("PostgreSQL connection/setup failed", str(error.exception))
        self.assertNotIn("classified-secret", str(error.exception))


if __name__ == "__main__":
    unittest.main()
