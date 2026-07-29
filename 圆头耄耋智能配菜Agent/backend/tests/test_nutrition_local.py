import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from app import calories, nutrition
from app.models import FoodLineDraft
from app.nutrition import NutritionMatch


def _make_database(path: Path) -> None:
    rows = [
        (
            1,
            1001,
            "Tomatoes, red, ripe, raw",
            "tomatoes red ripe raw",
            "SR Legacy",
            18,
        ),
        (
            2,
            1002,
            "Tomatoes, canned, red, ripe, diced",
            "tomatoes canned red ripe diced",
            "Foundation",
            18,
        ),
        (
            3,
            1003,
            "Chicken, breast, skinless, boneless, meat only, raw",
            "chicken breast skinless boneless meat only raw",
            "SR Legacy",
            120,
        ),
        (
            4,
            1004,
            "Chicken, breast, meat and skin, cooked, roasted",
            "chicken breast meat and skin cooked roasted",
            "SR Legacy",
            197,
        ),
        (
            5,
            1005,
            "Onions, raw",
            "onions raw",
            "SR Legacy",
            40,
        ),
        (
            6,
            1006,
            "Onions, red, raw",
            "onions red raw",
            "Foundation",
            44,
        ),
    ]
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
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
            CREATE VIRTUAL TABLE nutrition_foods_fts USING fts5(
                description_en,
                content='nutrition_foods',
                content_rowid='id',
                tokenize='porter unicode61'
            );
            """
        )
        connection.executemany(
            """
            INSERT INTO nutrition_foods (
                id, fdc_id, description_en, description_normalized, data_type,
                kcal_per_100g, source_release
            ) VALUES (?, ?, ?, ?, ?, ?, 'test')
            """,
            rows,
        )
        connection.execute(
            """
            INSERT INTO nutrition_foods_fts(rowid, description_en)
            SELECT id, description_en FROM nutrition_foods
            """
        )


class _OnlineOnionResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "foods": [
                {
                    "fdcId": 9002,
                    "description": "Onions, raw",
                    "dataType": "SR Legacy",
                    "foodNutrients": [
                        {
                            "nutrientNumber": "208",
                            "nutrientName": "Energy",
                            "unitName": "KCAL",
                            "value": 40,
                        }
                    ],
                }
            ]
        }


class _OnlineOnionClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        return _OnlineOnionResponse()


class LocalNutritionLookupTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.database = root / "nutrition.db"
        self.cache = root / "nutrition_cache.db"
        _make_database(self.database)
        self.path_patches = (
            patch.object(nutrition, "LOCAL_DB_PATH", self.database),
            patch.object(nutrition, "CACHE_PATH", self.cache),
        )
        for active_patch in self.path_patches:
            active_patch.start()

    async def asyncTearDown(self):
        for active_patch in reversed(self.path_patches):
            active_patch.stop()
        self.temporary_directory.cleanup()

    async def test_exact_local_query_uses_authoritative_row(self):
        result = await nutrition.search_local_nutrition(
            "tomatoes, red, ripe, raw"
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.source_id, 1001)
        self.assertEqual(result.kcal_per_100g, 18)
        self.assertFalse(result.estimated)

    async def test_chinese_food_alias_uses_authoritative_local_row(self):
        result = await nutrition.search_local_nutrition("番茄")

        self.assertIsNotNone(result)
        self.assertEqual(result.source_id, 1001)
        self.assertEqual(result.source, "USDA FoodData Central")
        self.assertFalse(result.estimated)

    async def test_state_conflict_does_not_select_cooked_skin_on_candidate(self):
        result = await nutrition.search_local_nutrition(
            "chicken breast meat only skinless raw"
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.source_id, 1003)
        self.assertNotIn("cooked", result.source_description.lower())

    async def test_exact_generic_food_beats_more_specific_foundation_food(self):
        result = await nutrition.search_local_nutrition("onions raw")

        self.assertIsNotNone(result)
        self.assertEqual(result.source_id, 1005)
        self.assertEqual(result.source_description, "Onions, raw")

    async def test_uses_second_local_query_before_network(self):
        async def online_must_not_run(_query):
            raise AssertionError("local fallback should avoid the online API")

        with patch.object(
            nutrition, "fetch_online_usda_nutrition", online_must_not_run
        ):
            result = await nutrition.resolve_nutrition(
                "yellow tomato unusual",
                "tomatoes red ripe raw",
            )

        self.assertIsNotNone(result)
        self.assertEqual(result.source_id, 1001)

    async def test_primary_local_error_still_tries_local_fallback(self):
        expected = NutritionMatch(
            kcal_per_100g=18,
            source="USDA FoodData Central",
            source_id=1001,
            source_description="Tomatoes, red, ripe, raw",
            source_url="https://example.test/1001",
            estimated=False,
        )
        calls = []

        async def flaky_local(query):
            calls.append(query)
            if query == "broken primary":
                raise sqlite3.DatabaseError("malformed")
            return expected

        with (
            patch.object(nutrition, "search_local_nutrition", flaky_local),
            patch.object(
                nutrition,
                "fetch_online_usda_nutrition",
                new=AsyncMock(side_effect=AssertionError("online should not run")),
            ),
        ):
            result = await nutrition.resolve_nutrition(
                "broken primary",
                "tomatoes raw",
            )

        self.assertEqual(result, expected)
        self.assertEqual(calls, ["broken primary", "tomatoes raw"])

    async def test_two_local_misses_trigger_exactly_one_online_query(self):
        calls = []
        expected = NutritionMatch(
            kcal_per_100g=42,
            source="USDA FoodData Central",
            source_id=9001,
            source_description="Rare ingredient",
            source_url="https://example.test/9001",
            estimated=False,
        )

        async def fake_online(query):
            calls.append(query)
            return expected

        with patch.object(nutrition, "fetch_online_usda_nutrition", fake_online):
            result = await nutrition.resolve_nutrition(
                "rare ingredient primary",
                "rare ingredient fallback",
            )

        self.assertEqual(result, expected)
        self.assertEqual(calls, ["rare ingredient primary"])

    async def test_online_miss_returns_none_for_caller_to_estimate(self):
        async def fake_online(_query):
            return None

        with patch.object(nutrition, "fetch_online_usda_nutrition", fake_online):
            result = await nutrition.resolve_nutrition(
                "not in any database",
                "also unavailable",
            )

        self.assertIsNone(result)

    async def test_malformed_online_json_returns_none(self):
        class MalformedResponse:
            def raise_for_status(self):
                return None

            def json(self):
                raise ValueError("not json")

        class MalformedClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, *args, **kwargs):
                return MalformedResponse()

        with patch.object(nutrition.httpx, "AsyncClient", MalformedClient):
            result = await nutrition.fetch_online_usda_nutrition(
                "rare ingredient"
            )

        self.assertIsNone(result)

    async def test_online_disconnect_returns_none(self):
        class DisconnectingClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, *args, **kwargs):
                raise httpx.ConnectError("offline")

        with patch.object(
            nutrition.httpx,
            "AsyncClient",
            DisconnectingClient,
        ):
            result = await nutrition.fetch_online_usda_nutrition(
                "rare ingredient"
            )

        self.assertIsNone(result)

    async def test_online_empty_foods_returns_none(self):
        class EmptyResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"foods": []}

        class EmptyClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, *args, **kwargs):
                return EmptyResponse()

        with patch.object(nutrition.httpx, "AsyncClient", EmptyClient):
            result = await nutrition.fetch_online_usda_nutrition(
                "rare ingredient"
            )

        self.assertIsNone(result)

    async def test_online_relevance_beats_unrelated_foundation_priority(self):
        foods = [
            {
                "fdcId": 9001,
                "description": "Kiwifruit, green, raw",
                "dataType": "Foundation",
                "foodNutrients": [
                    {
                        "nutrientNumber": "208",
                        "nutrientName": "Energy",
                        "unitName": "KCAL",
                        "value": 61,
                    }
                ],
            },
            {
                "fdcId": 9002,
                "description": "Onions, raw",
                "dataType": "SR Legacy",
                "foodNutrients": [
                    {
                        "nutrientNumber": "208",
                        "nutrientName": "Energy",
                        "unitName": "KCAL",
                        "value": 40,
                    }
                ],
            },
        ]

        selected = nutrition._pick_food(foods, "onions raw")

        self.assertIsNotNone(selected)
        self.assertEqual(selected["fdcId"], 9002)

    async def test_successful_online_result_is_reused_from_local_cache(self):
        class CachedResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "foods": [
                        {
                            "fdcId": 9002,
                            "description": "Onions, raw",
                            "dataType": "SR Legacy",
                            "foodNutrients": [
                                {
                                    "nutrientNumber": "208",
                                    "nutrientName": "Energy",
                                    "unitName": "KCAL",
                                    "value": 40,
                                }
                            ],
                        }
                    ]
                }

        class CountingClient:
            calls = 0

            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, *args, **kwargs):
                self.__class__.calls += 1
                return CachedResponse()

        with patch.object(nutrition.httpx, "AsyncClient", CountingClient):
            first = await nutrition.fetch_online_usda_nutrition("onions raw")
            second = await nutrition.fetch_online_usda_nutrition("onions raw")

        self.assertEqual(CountingClient.calls, 1)
        self.assertEqual(first, second)
        self.assertEqual(second.source_id, 9002)
        self.assertEqual(
            second.source_url,
            nutrition.FDC_WEB_URL.format(9002),
        )

    async def test_cache_read_failure_does_not_block_online_result(self):
        with (
            patch.object(
                nutrition,
                "_read_cache",
                side_effect=sqlite3.DatabaseError("cache malformed"),
            ),
            patch.object(
                nutrition.httpx,
                "AsyncClient",
                _OnlineOnionClient,
            ),
        ):
            result = await nutrition.fetch_online_usda_nutrition("onions raw")

        self.assertIsNotNone(result)
        self.assertEqual(result.source_id, 9002)
        self.assertFalse(result.estimated)

    async def test_cache_write_failure_does_not_discard_online_result(self):
        with (
            patch.object(
                nutrition,
                "_write_cache",
                side_effect=sqlite3.DatabaseError("cache read-only"),
            ),
            patch.object(
                nutrition.httpx,
                "AsyncClient",
                _OnlineOnionClient,
            ),
        ):
            result = await nutrition.fetch_online_usda_nutrition("onions raw")

        self.assertIsNotNone(result)
        self.assertEqual(result.source_id, 9002)
        self.assertFalse(result.estimated)

    async def test_calorie_resolution_forwards_both_model_queries(self):
        calls = []
        expected = NutritionMatch(
            kcal_per_100g=18,
            source="USDA FoodData Central",
            source_id=1001,
            source_description="Tomatoes, red, ripe, raw",
            source_url="https://example.test/1001",
            estimated=False,
        )

        async def fake_lookup(primary, fallback):
            calls.append((primary, fallback))
            return expected

        line = FoodLineDraft(
            name="番茄",
            nutritionQuery="tomatoes red ripe raw",
            nutritionFallbackQuery="tomatoes raw",
            grams=100,
            note="",
            estimatedKcalPer100g=18,
        )
        with patch.object(calories, "fetch_usda_nutrition", fake_lookup):
            matches = await calories._resolve_matches([line])

        self.assertEqual(
            calls,
            [("tomatoes red ripe raw", "tomatoes raw")],
        )
        self.assertEqual(matches[calories.nutrition_query_key(line)], expected)

    async def test_calorie_resolution_failure_uses_explicit_line_estimate(self):
        line = FoodLineDraft(
            name="稀有食材",
            nutritionQuery="rare ingredient raw",
            nutritionFallbackQuery="rare ingredient",
            grams=80,
            note="",
            estimatedKcalPer100g=73,
        )

        with patch.object(
            calories,
            "fetch_usda_nutrition",
            new=AsyncMock(side_effect=RuntimeError("network stack failed")),
        ):
            matches = await calories._resolve_matches([line])

        match = calories.match_for_line(line, matches)
        self.assertTrue(match.estimated)
        self.assertEqual(match.kcal_per_100g, 73)
        self.assertEqual(match.source, "耄耋估算")
        self.assertIsNone(match.source_id)
        self.assertIsNone(match.source_url)


if __name__ == "__main__":
    unittest.main()
