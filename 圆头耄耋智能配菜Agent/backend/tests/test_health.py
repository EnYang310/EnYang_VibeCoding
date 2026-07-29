import sqlite3
import tempfile
import unittest
from shutil import copy2
from pathlib import Path
from unittest.mock import patch

from app.health import inspect_local_database
from app.nutrition import LOCAL_DB_PATH


class NutritionHealthTest(unittest.TestCase):
    def test_packaged_database_is_exactly_healthy(self):
        health = inspect_local_database(LOCAL_DB_PATH)

        self.assertEqual("healthy", health.status)
        self.assertEqual(7_888, health.foodCount)
        self.assertEqual(7_888, health.ftsCount)
        self.assertEqual(
            {
                (
                    "USDA FoodData Central",
                    "Foundation",
                    "2026-04",
                    "CC0 1.0",
                    95,
                ),
                (
                    "USDA FoodData Central",
                    "SR Legacy",
                    "2018-04",
                    "CC0 1.0",
                    7_793,
                ),
            },
            {
                (
                    item.source,
                    item.dataType,
                    item.release,
                    item.license,
                    item.rows,
                )
                for item in health.datasets
            },
        )

    def test_one_row_database_cannot_report_healthy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nutrition.db"
            with sqlite3.connect(path) as connection:
                connection.executescript(
                    """
                    CREATE TABLE nutrition_foods (
                        id INTEGER PRIMARY KEY,
                        data_type TEXT NOT NULL,
                        source_release TEXT NOT NULL
                    );
                    INSERT INTO nutrition_foods
                    VALUES (1, 'Foundation', '2026-04');
                    CREATE VIRTUAL TABLE nutrition_foods_fts
                    USING fts5(description_en);
                    INSERT INTO nutrition_foods_fts(rowid, description_en)
                    VALUES (1, 'tomato raw');
                    CREATE TABLE dataset_info (
                        id INTEGER PRIMARY KEY,
                        source TEXT NOT NULL,
                        data_type TEXT NOT NULL,
                        release TEXT NOT NULL,
                        source_url TEXT NOT NULL,
                        license TEXT NOT NULL,
                        built_at TEXT NOT NULL
                    );
                    """
                )

            health = inspect_local_database(path)

        self.assertEqual("unhealthy", health.status)
        self.assertEqual(1, health.foodCount)
        self.assertEqual((), health.datasets)

    def test_duplicate_dataset_metadata_cannot_report_healthy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nutrition.db"
            copy2(LOCAL_DB_PATH, path)
            with sqlite3.connect(path) as connection:
                row = connection.execute(
                    """
                    SELECT source, data_type, release, source_url, license, built_at
                    FROM dataset_info
                    WHERE data_type = 'Foundation'
                    """
                ).fetchone()
                connection.execute(
                    """
                    INSERT INTO dataset_info(
                        source, data_type, release, source_url, license, built_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    row,
                )

            health = inspect_local_database(path)

        self.assertEqual("unhealthy", health.status)
        self.assertEqual(3, len(health.datasets))

    def test_health_uses_full_integrity_check(self):
        statements: list[str] = []
        connection = sqlite3.connect(
            "file:{}?mode=ro".format(LOCAL_DB_PATH),
            uri=True,
        )

        class RecordingConnection:
            def execute(self, statement, *args, **kwargs):
                statements.append(str(statement).strip())
                return connection.execute(statement, *args, **kwargs)

            def close(self):
                connection.close()

        with patch(
            "app.health.sqlite3.connect",
            return_value=RecordingConnection(),
        ):
            health = inspect_local_database(LOCAL_DB_PATH)

        self.assertEqual("healthy", health.status)
        self.assertIn("PRAGMA integrity_check", statements)
        self.assertNotIn("PRAGMA quick_check", statements)


if __name__ == "__main__":
    unittest.main()
