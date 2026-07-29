import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Tuple

from .nutrition import LOCAL_DB_PATH


EXPECTED_FOOD_COUNT = 7_888
EXPECTED_DATASETS = {
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
}


@dataclass(frozen=True)
class DatasetHealth:
    source: str
    dataType: str
    release: str
    license: str
    rows: int


@dataclass(frozen=True)
class NutritionDatabaseHealth:
    status: str
    integrity: str
    foodCount: int
    ftsCount: int
    ftsAvailable: bool
    datasets: Tuple[DatasetHealth, ...]

    def as_payload(self) -> dict:
        return asdict(self)


def inspect_local_database(
    path: Optional[Path] = None,
) -> NutritionDatabaseHealth:
    database = path or LOCAL_DB_PATH
    connection = sqlite3.connect(
        "file:{}?mode=ro".format(database),
        uri=True,
    )
    try:
        integrity = str(
            connection.execute("PRAGMA integrity_check").fetchone()[0]
        )
        food_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM nutrition_foods"
            ).fetchone()[0]
        )
        fts_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM nutrition_foods_fts"
            ).fetchone()[0]
        )
        fts_available = (
            connection.execute(
                "SELECT rowid FROM nutrition_foods_fts "
                "WHERE nutrition_foods_fts MATCH 'tomato' LIMIT 1"
            ).fetchone()
            is not None
        )
        dataset_rows = connection.execute(
            """
            SELECT d.source, d.data_type, d.release, d.license, COUNT(f.id)
            FROM dataset_info AS d
            LEFT JOIN nutrition_foods AS f
              ON f.data_type = d.data_type
             AND f.source_release = d.release
            GROUP BY d.id, d.data_type, d.release
            ORDER BY d.id
            """
        ).fetchall()
    finally:
        connection.close()

    dataset_signature = {
        (
            str(source),
            str(data_type),
            str(release),
            str(license_name),
            int(rows),
        )
        for source, data_type, release, license_name, rows in dataset_rows
    }
    healthy = (
        integrity == "ok"
        and food_count == EXPECTED_FOOD_COUNT
        and fts_count == EXPECTED_FOOD_COUNT
        and fts_available
        and len(dataset_rows) == len(EXPECTED_DATASETS)
        and dataset_signature == EXPECTED_DATASETS
    )
    return NutritionDatabaseHealth(
        status="healthy" if healthy else "unhealthy",
        integrity=integrity,
        foodCount=food_count,
        ftsCount=fts_count,
        ftsAvailable=fts_available,
        datasets=tuple(
            DatasetHealth(
                source=str(source),
                dataType=str(data_type),
                release=str(release),
                license=str(license_name),
                rows=int(rows),
            )
            for source, data_type, release, license_name, rows in dataset_rows
        ),
    )
