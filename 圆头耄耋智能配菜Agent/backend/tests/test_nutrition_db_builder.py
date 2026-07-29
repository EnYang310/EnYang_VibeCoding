import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.build_nutrition_db import DatasetSource, build_database


NUTRIENTS = [
    {
        "id": "1003",
        "name": "Protein",
        "unit_name": "G",
        "nutrient_nbr": "203",
        "rank": "600",
    },
    {
        "id": "1004",
        "name": "Total lipid (fat)",
        "unit_name": "G",
        "nutrient_nbr": "204",
        "rank": "800",
    },
    {
        "id": "1005",
        "name": "Carbohydrate, by difference",
        "unit_name": "G",
        "nutrient_nbr": "205",
        "rank": "1110",
    },
    {
        "id": "1008",
        "name": "Energy",
        "unit_name": "KCAL",
        "nutrient_nbr": "208",
        "rank": "300",
    },
]


def _write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _make_dataset(
    root: Path,
    *,
    fdc_id: int,
    data_type: str,
    description: str,
    kcal: float,
):
    _write_csv(root / "nutrient.csv", NUTRIENTS)
    _write_csv(
        root / "food.csv",
        [
            {
                "fdc_id": str(fdc_id),
                "data_type": data_type,
                "description": description,
                "food_category_id": "1",
                "publication_date": "2026-04-30",
            },
            {
                "fdc_id": str(fdc_id + 99),
                "data_type": "sample_food",
                "description": "SHOULD NOT BE IMPORTED",
                "food_category_id": "1",
                "publication_date": "2026-04-30",
            },
        ],
    )
    subtype_file = (
        "foundation_food.csv"
        if data_type == "foundation_food"
        else "sr_legacy_food.csv"
    )
    _write_csv(root / subtype_file, [{"fdc_id": str(fdc_id), "NDB_number": "1"}])
    nutrient_amounts = {
        "1003": 1.0,
        "1004": 2.0,
        "1005": 3.0,
        "1008": kcal,
    }
    _write_csv(
        root / "food_nutrient.csv",
        [
            {
                "id": str(index),
                "fdc_id": str(fdc_id),
                "nutrient_id": nutrient_id,
                "amount": str(amount),
            }
            for index, (nutrient_id, amount) in enumerate(
                nutrient_amounts.items(), start=1
            )
        ],
    )


class NutritionDatabaseBuilderTest(unittest.TestCase):
    def test_builds_authoritative_food_rows_and_source_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            foundation = root / "foundation"
            legacy = root / "legacy"
            output = root / "nutrition.db"
            _make_dataset(
                foundation,
                fdc_id=1001,
                data_type="foundation_food",
                description="Tomatoes, red, ripe, raw",
                kcal=18,
            )
            _make_dataset(
                legacy,
                fdc_id=2001,
                data_type="sr_legacy_food",
                description="Egg, whole, raw, fresh",
                kcal=143,
            )

            build_database(
                [
                    DatasetSource(
                        path=foundation,
                        data_type="Foundation",
                        release="2026-04",
                        source_url="https://example.test/foundation.zip",
                    ),
                    DatasetSource(
                        path=legacy,
                        data_type="SR Legacy",
                        release="2018-04",
                        source_url="https://example.test/legacy.zip",
                    ),
                ],
                output,
            )

            with sqlite3.connect(output) as connection:
                foods = connection.execute(
                    """
                    SELECT fdc_id, description_en, data_type, kcal_per_100g,
                           protein_per_100g, fat_per_100g, carbs_per_100g
                    FROM nutrition_foods
                    ORDER BY fdc_id
                    """
                ).fetchall()
                metadata = connection.execute(
                    """
                    SELECT source, release, license
                    FROM dataset_info
                    ORDER BY release DESC
                    """
                ).fetchall()
                fts_count = connection.execute(
                    "SELECT COUNT(*) FROM nutrition_foods_fts"
                ).fetchone()[0]

            self.assertEqual(
                foods,
                [
                    (
                        1001,
                        "Tomatoes, red, ripe, raw",
                        "Foundation",
                        18.0,
                        1.0,
                        2.0,
                        3.0,
                    ),
                    (
                        2001,
                        "Egg, whole, raw, fresh",
                        "SR Legacy",
                        143.0,
                        1.0,
                        2.0,
                        3.0,
                    ),
                ],
            )
            self.assertEqual(len(metadata), 2)
            self.assertTrue(all(row[0] == "USDA FoodData Central" for row in metadata))
            self.assertTrue(all(row[2] == "CC0 1.0" for row in metadata))
            self.assertEqual(fts_count, 2)


if __name__ == "__main__":
    unittest.main()
