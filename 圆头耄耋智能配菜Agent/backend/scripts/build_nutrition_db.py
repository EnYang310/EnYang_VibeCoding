from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Set


TARGET_NUTRIENT_NUMBERS = {
    "203": "protein_per_100g",
    "204": "fat_per_100g",
    "205": "carbs_per_100g",
    "208": "kcal_per_100g",
}


@dataclass(frozen=True)
class DatasetSource:
    path: Path
    data_type: str
    release: str
    source_url: str


def _normalize_description(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _find_dataset_root(path: Path) -> Path:
    if (path / "food.csv").exists():
        return path
    matches = list(path.rglob("food.csv"))
    if len(matches) != 1:
        raise ValueError(
            "{} 中应当且只能找到一个 food.csv，实际为 {}".format(
                path, len(matches)
            )
        )
    return matches[0].parent


def _prepare_source(path: Path, temporary_root: Path, index: int) -> Path:
    if path.is_dir():
        return _find_dataset_root(path)
    if not path.is_file() or path.suffix.lower() != ".zip":
        raise ValueError("{} 不是 USDA ZIP 或已解压目录".format(path))
    extracted = temporary_root / "source-{}".format(index)
    extracted.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as archive:
        archive.extractall(extracted)
    return _find_dataset_root(extracted)


def _read_valid_food_ids(root: Path, data_type: str) -> Set[int]:
    subtype_file = (
        "foundation_food.csv"
        if data_type == "Foundation"
        else "sr_legacy_food.csv"
    )
    path = root / subtype_file
    if not path.exists():
        raise ValueError("{} 缺少 {}".format(root, subtype_file))
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {int(row["fdc_id"]) for row in csv.DictReader(handle)}


def _read_nutrient_ids(root: Path) -> Dict[str, str]:
    result: Dict[str, str] = {}
    with (root / "nutrient.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            number = row["nutrient_nbr"].strip()
            if number in TARGET_NUTRIENT_NUMBERS:
                result[row["id"]] = number
    missing = set(TARGET_NUTRIENT_NUMBERS) - set(result.values())
    if missing:
        raise ValueError("USDA nutrient.csv 缺少营养素编号 {}".format(sorted(missing)))
    return result


def _read_food_descriptions(
    root: Path, valid_food_ids: Set[int]
) -> Dict[int, str]:
    result: Dict[int, str] = {}
    with (root / "food.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            fdc_id = int(row["fdc_id"])
            if fdc_id in valid_food_ids:
                result[fdc_id] = row["description"].strip()
    return result


def _read_nutrients(
    root: Path,
    valid_food_ids: Set[int],
    nutrient_ids: Mapping[str, str],
) -> Dict[int, Dict[str, float]]:
    result: Dict[int, Dict[str, float]] = {}
    with (root / "food_nutrient.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            nutrient_number = nutrient_ids.get(row["nutrient_id"])
            if nutrient_number is None:
                continue
            fdc_id = int(row["fdc_id"])
            if fdc_id not in valid_food_ids:
                continue
            amount = row.get("amount", "").strip()
            if not amount:
                continue
            result.setdefault(fdc_id, {})[
                TARGET_NUTRIENT_NUMBERS[nutrient_number]
            ] = float(amount)
    return result


def _dataset_rows(root: Path, source: DatasetSource) -> Iterable[tuple]:
    valid_food_ids = _read_valid_food_ids(root, source.data_type)
    nutrient_ids = _read_nutrient_ids(root)
    descriptions = _read_food_descriptions(root, valid_food_ids)
    nutrient_values = _read_nutrients(root, valid_food_ids, nutrient_ids)
    for fdc_id in sorted(valid_food_ids):
        values = nutrient_values.get(fdc_id, {})
        description = descriptions.get(fdc_id)
        if description is None or "kcal_per_100g" not in values:
            continue
        yield (
            fdc_id,
            description,
            _normalize_description(description),
            source.data_type,
            values["kcal_per_100g"],
            values.get("protein_per_100g"),
            values.get("fat_per_100g"),
            values.get("carbs_per_100g"),
            source.release,
        )


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA journal_mode = DELETE;
        PRAGMA synchronous = OFF;

        CREATE TABLE nutrition_foods (
            id INTEGER PRIMARY KEY,
            fdc_id INTEGER NOT NULL UNIQUE,
            description_en TEXT NOT NULL,
            description_normalized TEXT NOT NULL,
            data_type TEXT NOT NULL,
            kcal_per_100g REAL NOT NULL,
            protein_per_100g REAL,
            fat_per_100g REAL,
            carbs_per_100g REAL,
            source_release TEXT NOT NULL
        );

        CREATE INDEX nutrition_foods_normalized_idx
        ON nutrition_foods(description_normalized);

        CREATE TABLE dataset_info (
            id INTEGER PRIMARY KEY,
            source TEXT NOT NULL,
            data_type TEXT NOT NULL,
            release TEXT NOT NULL,
            source_url TEXT NOT NULL,
            license TEXT NOT NULL,
            built_at TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE nutrition_foods_fts USING fts5(
            description_en,
            content='nutrition_foods',
            content_rowid='id',
            tokenize='porter unicode61'
        );
        """
    )


def build_database(sources: List[DatasetSource], output: Path) -> None:
    if not sources:
        raise ValueError("至少需要一个 USDA 数据源")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output.with_suffix(output.suffix + ".tmp")
    if temporary_output.exists():
        temporary_output.unlink()

    with tempfile.TemporaryDirectory(prefix="maodie-usda-build-") as directory:
        extracted_root = Path(directory)
        with sqlite3.connect(temporary_output) as connection:
            _create_schema(connection)
            for index, source in enumerate(sources):
                root = _prepare_source(Path(source.path), extracted_root, index)
                connection.executemany(
                    """
                    INSERT INTO nutrition_foods (
                        fdc_id, description_en, description_normalized, data_type,
                        kcal_per_100g, protein_per_100g, fat_per_100g,
                        carbs_per_100g, source_release
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _dataset_rows(root, source),
                )
                connection.execute(
                    """
                    INSERT INTO dataset_info (
                        source, data_type, release, source_url, license, built_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "USDA FoodData Central",
                        source.data_type,
                        source.release,
                        source.source_url,
                        "CC0 1.0",
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
            connection.execute(
                """
                INSERT INTO nutrition_foods_fts(rowid, description_en)
                SELECT id, description_en FROM nutrition_foods
                """
            )
            connection.execute("ANALYZE")
            connection.commit()
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError("SQLite integrity_check: {}".format(integrity))

    temporary_output.replace(output)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the compact Maodie USDA nutrition knowledge base."
    )
    parser.add_argument("--foundation", required=True, type=Path)
    parser.add_argument("--sr-legacy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    build_database(
        [
            DatasetSource(
                path=arguments.foundation,
                data_type="Foundation",
                release="2026-04",
                source_url=(
                    "https://fdc.nal.usda.gov/fdc-datasets/"
                    "FoodData_Central_foundation_food_csv_2026-04-30.zip"
                ),
            ),
            DatasetSource(
                path=arguments.sr_legacy,
                data_type="SR Legacy",
                release="2018-04",
                source_url=(
                    "https://fdc.nal.usda.gov/fdc-datasets/"
                    "FoodData_Central_sr_legacy_food_csv_2018-04.zip"
                ),
            ),
        ],
        arguments.output,
    )


if __name__ == "__main__":
    main()
