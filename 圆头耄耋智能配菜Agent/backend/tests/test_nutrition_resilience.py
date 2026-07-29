import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import nutrition


class _FoodResponse:
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


class _CountingClient:
    calls = 0

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        self.__class__.calls += 1
        await asyncio.sleep(0.01)
        return _FoodResponse()


class NutritionResilienceTest(unittest.IsolatedAsyncioTestCase):
    async def test_packaged_database_matches_common_foods_locally(self):
        queries = (
            "tomatoes red ripe raw",
            "egg whole raw",
            "chicken breast skinless boneless raw",
            "broccoli raw",
            "canola oil",
        )
        for query in queries:
            with self.subTest(query=query):
                match = await nutrition.search_local_nutrition(query)
                self.assertIsNotNone(match)
                self.assertFalse(match.estimated)

    async def test_green_onion_never_matches_kiwi(self):
        match = await nutrition.search_local_nutrition("green onion raw")

        self.assertIsNotNone(match)
        self.assertNotIn("kiwi", match.source_description.lower())
        self.assertIn("onion", match.source_description.lower())

    async def test_aubergine_and_eggplant_resolve_to_same_food(self):
        aubergine = await nutrition.search_local_nutrition("aubergine raw")
        eggplant = await nutrition.search_local_nutrition("eggplant raw")

        self.assertIsNotNone(aubergine)
        self.assertIsNotNone(eggplant)
        self.assertEqual(eggplant.source_id, aubergine.source_id)

    async def test_twenty_concurrent_online_lookups_share_one_request(self):
        _CountingClient.calls = 0
        with (
            patch.object(nutrition, "_read_cache", return_value=None),
            patch.object(nutrition, "_write_cache", return_value=None),
            patch.object(nutrition.httpx, "AsyncClient", _CountingClient),
        ):
            matches = await asyncio.gather(
                *[
                    nutrition.fetch_online_usda_nutrition("onions raw")
                    for _ in range(20)
                ]
            )

        self.assertEqual(1, _CountingClient.calls)
        self.assertTrue(all(item == matches[0] for item in matches))

    async def test_cache_expires_and_is_namespaced_by_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "nutrition_cache.db"
            with patch.object(nutrition, "CACHE_PATH", cache_path):
                nutrition._write_cache(
                    "onions raw",
                    40,
                    9002,
                    "Onions, raw",
                    "SR Legacy",
                )
                self.assertIsNotNone(nutrition._read_cache("onions raw"))

                with sqlite3.connect(cache_path) as connection:
                    connection.execute(
                        """
                        UPDATE nutrition_cache_v2
                        SET expires_at_epoch = 0
                        """
                    )
                    connection.commit()
                self.assertIsNone(nutrition._read_cache("onions raw"))

                with patch.object(
                    nutrition,
                    "NUTRITION_ALGORITHM_VERSION",
                    "future-ranking",
                ):
                    self.assertIsNone(nutrition._read_cache("onions raw"))


if __name__ == "__main__":
    unittest.main()
