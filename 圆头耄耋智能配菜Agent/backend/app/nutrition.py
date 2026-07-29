import asyncio
import hashlib
import logging
import os
import re
import sqlite3
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import httpx


FDC_API_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
FDC_SOURCE = "USDA FoodData Central"
FDC_WEB_URL = "https://fdc.nal.usda.gov/food-details/{}/nutrients"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
LOCAL_DB_PATH = DATA_DIR / "nutrition.db"
CACHE_PATH = DATA_DIR / "nutrition_cache.db"
NUTRITION_ALGORITHM_VERSION = "maodie-ranking-1.6.0"
NUTRITION_DATA_VERSION = "foundation-2026-04+sr-legacy-2018-04"
CACHE_TTL_SECONDS = 30 * 24 * 60 * 60
logger = logging.getLogger("uvicorn.error")

FOOD_ALIASES = {
    "番茄": "tomatoes red ripe raw",
    "西红柿": "tomatoes red ripe raw",
    "鸡蛋": "egg whole raw",
    "鸡胸肉": "chicken breast skinless boneless raw",
    "西兰花": "broccoli raw",
    "菜籽油": "canola oil",
    "牛肉": "beef raw",
    "豆腐": "tofu raw",
    "土豆": "potatoes raw",
    "马铃薯": "potatoes raw",
    "胡萝卜": "carrots raw",
    "洋葱": "onions raw",
    "green onion raw": "onions spring scallions raw",
    "green onions raw": "onions spring scallions raw",
    "spring onion raw": "onions spring scallions raw",
    "spring onions raw": "onions spring scallions raw",
    "scallion raw": "onions spring scallions raw",
    "scallions raw": "onions spring scallions raw",
    "aubergine raw": "eggplant raw",
}

_ONLINE_INFLIGHT: Dict[str, "asyncio.Task[Optional[NutritionMatch]]"] = {}


@dataclass(frozen=True)
class NutritionMatch:
    kcal_per_100g: float
    source: str
    source_id: Optional[int]
    source_description: str
    source_url: Optional[str]
    estimated: bool


def _connect_cache() -> sqlite3.Connection:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(CACHE_PATH))
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS nutrition_cache_v2 (
            cache_key TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            algorithm_version TEXT NOT NULL,
            data_version TEXT NOT NULL,
            kcal_per_100g REAL NOT NULL,
            source_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            data_type TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            expires_at_epoch REAL NOT NULL
        )
        """
    )
    return connection


def _cache_key(query: str) -> str:
    identity = "\n".join(
        (
            NUTRITION_ALGORITHM_VERSION,
            NUTRITION_DATA_VERSION,
            _normalize_query(query),
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _normalize_query(query: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(query)).strip().lower()
    if normalized in FOOD_ALIASES:
        normalized = FOOD_ALIASES[normalized]
    else:
        for alias, english in sorted(
            FOOD_ALIASES.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            normalized = normalized.replace(alias, " {} ".format(english))
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def normalize_nutrition_query(query: str) -> str:
    return _normalize_query(query)


def _read_cache(query: str) -> Optional[NutritionMatch]:
    normalized = _normalize_query(query)
    with _connect_cache() as connection:
        row = connection.execute(
            """
            SELECT kcal_per_100g, source_id, description
            FROM nutrition_cache_v2
            WHERE cache_key = ?
              AND algorithm_version = ?
              AND data_version = ?
              AND expires_at_epoch > ?
            """,
            (
                _cache_key(normalized),
                NUTRITION_ALGORITHM_VERSION,
                NUTRITION_DATA_VERSION,
                time.time(),
            ),
        ).fetchone()
    if not row:
        return None
    return NutritionMatch(
        kcal_per_100g=float(row[0]),
        source=FDC_SOURCE,
        source_id=int(row[1]),
        source_description=str(row[2]),
        source_url=FDC_WEB_URL.format(row[1]),
        estimated=False,
    )


def _write_cache(
    query: str,
    kcal_per_100g: float,
    source_id: int,
    description: str,
    data_type: str,
) -> None:
    normalized = _normalize_query(query)
    now = datetime.now(timezone.utc)
    with _connect_cache() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO nutrition_cache_v2 (
                cache_key, query, algorithm_version, data_version,
                kcal_per_100g, source_id, description, data_type,
                fetched_at, expires_at_epoch
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _cache_key(normalized),
                normalized,
                NUTRITION_ALGORITHM_VERSION,
                NUTRITION_DATA_VERSION,
                kcal_per_100g,
                source_id,
                description,
                data_type,
                now.isoformat(),
                now.timestamp() + CACHE_TTL_SECONDS,
            ),
        )
        connection.commit()


def _query_tokens(value: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def _stem_token(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("oes"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _stemmed_tokens(value: str) -> Set[str]:
    return {_stem_token(token) for token in _query_tokens(value)}


def _core_food_tokens(tokens: Set[str]) -> Set[str]:
    descriptors = {
        "baked",
        "black",
        "boiled",
        "boneless",
        "canned",
        "cooked",
        "diced",
        "dried",
        "fresh",
        "fried",
        "frozen",
        "green",
        "meat",
        "only",
        "pasteurized",
        "purple",
        "raw",
        "red",
        "ripe",
        "roasted",
        "skinless",
        "steamed",
        "white",
        "whole",
        "yellow",
    }
    return tokens - descriptors


def _has_state_conflict(query: Set[str], candidate: Set[str]) -> bool:
    cooked_states = {
        "baked",
        "boiled",
        "canned",
        "cooked",
        "dried",
        "fried",
        "roasted",
        "steamed",
    }
    if "raw" in query and candidate.intersection(cooked_states):
        return True
    if "cooked" in query and "raw" in candidate and not candidate.intersection(
        cooked_states
    ):
        return True
    if "skinless" in query and "skin" in candidate and "skinless" not in candidate:
        return True
    if "fresh" in query and candidate.intersection({"canned", "dried"}):
        return True
    color_groups = [
        {"red", "yellow", "green", "white", "purple", "black"},
    ]
    for group in color_groups:
        requested = query.intersection(group)
        offered = candidate.intersection(group)
        if requested and offered and requested.isdisjoint(offered):
            return True
    return False


def _candidate_score(
    query: str,
    description: str,
    data_type: str,
    fts_rank: float,
) -> Optional[float]:
    query_tokens = _stemmed_tokens(query)
    candidate_tokens = _stemmed_tokens(description)
    if not query_tokens:
        return None
    if _has_state_conflict(query_tokens, candidate_tokens):
        return None
    core_tokens = _core_food_tokens(query_tokens)
    if core_tokens and core_tokens.isdisjoint(candidate_tokens):
        return None
    matched = len(query_tokens.intersection(candidate_tokens))
    coverage = matched / len(query_tokens)
    if coverage < 0.55:
        return None
    normalized_query = _normalize_query(
        re.sub(r"[^a-z0-9]+", " ", query.lower())
    )
    normalized_description = _normalize_query(
        re.sub(r"[^a-z0-9]+", " ", description.lower())
    )
    exact_bonus = 100 if normalized_query == normalized_description else 0
    source_bonus = 2 if data_type == "Foundation" else 1
    extra_tokens = len(candidate_tokens - query_tokens)
    return (
        exact_bonus
        + coverage * 100
        + source_bonus
        - extra_tokens * 0.25
        - max(fts_rank, 0) * 0.01
    )


def _local_match_from_row(row: Tuple[Any, ...]) -> NutritionMatch:
    return NutritionMatch(
        kcal_per_100g=float(row[3]),
        source=FDC_SOURCE,
        source_id=int(row[1]),
        source_description=str(row[2]),
        source_url=FDC_WEB_URL.format(row[1]),
        estimated=False,
    )


def _search_local_sync(query: str) -> Optional[NutritionMatch]:
    if not LOCAL_DB_PATH.exists():
        return None
    normalized_query = _normalize_query(query)
    tokens = _query_tokens(normalized_query)
    if not tokens:
        return None
    match_expression = " OR ".join('"{}"'.format(token) for token in tokens)
    connection: Optional[sqlite3.Connection] = None
    try:
        connection = sqlite3.connect(
            "file:{}?mode=ro".format(LOCAL_DB_PATH),
            uri=True,
        )
        rows = connection.execute(
            """
            SELECT f.id, f.fdc_id, f.description_en, f.kcal_per_100g,
                   f.data_type, bm25(nutrition_foods_fts) AS fts_rank
            FROM nutrition_foods_fts
            JOIN nutrition_foods AS f ON f.id = nutrition_foods_fts.rowid
            WHERE nutrition_foods_fts MATCH ?
            ORDER BY fts_rank
            LIMIT 60
            """,
            (match_expression,),
        ).fetchall()
    except sqlite3.Error:
        logger.exception("Local USDA nutrition lookup failed")
        return None
    finally:
        if connection is not None:
            connection.close()

    ranked = []
    for row in rows:
        score = _candidate_score(
            query=normalized_query,
            description=str(row[2]),
            data_type=str(row[4]),
            fts_rank=float(row[5]),
        )
        if score is not None:
            ranked.append((score, row))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    return _local_match_from_row(ranked[0][1])


async def search_local_nutrition(query: str) -> Optional[NutritionMatch]:
    return await asyncio.to_thread(_search_local_sync, query)


def _energy_kcal(food: Dict[str, Any]) -> Optional[float]:
    for nutrient in food.get("foodNutrients", []):
        nutrient_name = str(nutrient.get("nutrientName", "")).lower()
        unit_name = str(nutrient.get("unitName", "")).lower()
        nutrient_number = str(nutrient.get("nutrientNumber", ""))
        if (
            nutrient_number == "208"
            or (nutrient_name == "energy" and unit_name == "kcal")
        ):
            value = nutrient.get("value")
            if isinstance(value, (int, float)):
                return float(value)
    return None


def _pick_food(
    foods: Iterable[Dict[str, Any]],
    query: str,
) -> Optional[Dict[str, Any]]:
    ranked = []
    for food in foods:
        energy = _energy_kcal(food)
        if energy is None:
            continue
        description = str(food.get("description", ""))
        data_type = str(food.get("dataType", ""))
        score = _candidate_score(
            query=query,
            description=description,
            data_type=data_type,
            fts_rank=0.0,
        )
        if score is None:
            continue
        ranked.append(
            (
                score,
                food,
                energy,
            )
        )
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    _, food, energy = ranked[0]
    return {**food, "_energyKcal": energy}


async def _fetch_online_usda_uncached(query: str) -> Optional[NutritionMatch]:
    api_key = os.getenv("USDA_API_KEY", "DEMO_KEY").strip() or "DEMO_KEY"
    body = {
        "query": query,
        "dataType": ["Foundation", "SR Legacy"],
        "pageSize": 5,
        "pageNumber": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
            response = await client.post(
                FDC_API_URL,
                params={"api_key": api_key},
                json=body,
            )
            response.raise_for_status()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "USDA online lookup failed: query=%r error=%s",
            query,
            type(exc).__name__,
        )
        return None

    try:
        payload = response.json()
        if not isinstance(payload, dict):
            return None
        foods = payload.get("foods", [])
        if not isinstance(foods, list):
            return None
        food = _pick_food(
            (item for item in foods if isinstance(item, dict)),
            query,
        )
        if not food:
            return None
        source_id = int(food["fdcId"])
        description = str(food.get("description", query)).strip() or query
        data_type = str(food.get("dataType", ""))
        kcal_per_100g = float(food["_energyKcal"])
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning(
            "USDA online response ignored: query=%r error=%s",
            query,
            type(exc).__name__,
        )
        return None
    try:
        await asyncio.to_thread(
            _write_cache,
            query,
            kcal_per_100g,
            source_id,
            description,
            data_type,
        )
    except (OSError, sqlite3.Error) as exc:
        logger.warning(
            "USDA cache write ignored: query=%r error=%s",
            query,
            type(exc).__name__,
        )
    return NutritionMatch(
        kcal_per_100g=kcal_per_100g,
        source=FDC_SOURCE,
        source_id=source_id,
        source_description=description,
        source_url=FDC_WEB_URL.format(source_id),
        estimated=False,
    )


async def fetch_online_usda_nutrition(query: str) -> Optional[NutritionMatch]:
    query = _normalize_query(query)
    if not query:
        return None
    try:
        cached = await asyncio.to_thread(_read_cache, query)
    except (OSError, sqlite3.Error) as exc:
        logger.warning(
            "USDA cache read ignored: query=%r error=%s",
            query,
            type(exc).__name__,
        )
        cached = None
    if cached:
        return cached

    inflight_key = _cache_key(query)
    task = _ONLINE_INFLIGHT.get(inflight_key)
    if task is None:
        task = asyncio.create_task(_fetch_online_usda_uncached(query))
        _ONLINE_INFLIGHT[inflight_key] = task

        def clear_inflight(done: "asyncio.Task[Optional[NutritionMatch]]") -> None:
            if _ONLINE_INFLIGHT.get(inflight_key) is done:
                _ONLINE_INFLIGHT.pop(inflight_key, None)

        task.add_done_callback(clear_inflight)
    return await asyncio.shield(task)


async def resolve_nutrition(
    query: str,
    fallback_query: Optional[str] = None,
) -> Optional[NutritionMatch]:
    primary = _normalize_query(query)
    fallback = _normalize_query(fallback_query or "")
    try:
        local = await search_local_nutrition(primary)
    except Exception as exc:
        logger.warning(
            "Local USDA lookup ignored: query=%r error=%s",
            primary,
            type(exc).__name__,
        )
        local = None
    if local:
        return local
    if fallback and fallback != primary:
        try:
            local = await search_local_nutrition(fallback)
        except Exception as exc:
            logger.warning(
                "Local USDA fallback ignored: query=%r error=%s",
                fallback,
                type(exc).__name__,
            )
            local = None
        if local:
            return local
    try:
        return await fetch_online_usda_nutrition(primary)
    except Exception as exc:
        logger.warning(
            "Online USDA lookup ignored: query=%r error=%s",
            primary,
            type(exc).__name__,
        )
        return None


async def fetch_usda_nutrition(
    query: str,
    fallback_query: Optional[str] = None,
) -> Optional[NutritionMatch]:
    return await resolve_nutrition(query, fallback_query)


def kimi_estimate(kcal_per_100g: Optional[float], description: str) -> NutritionMatch:
    return NutritionMatch(
        kcal_per_100g=kcal_per_100g if kcal_per_100g is not None else 100.0,
        source="耄耋估算",
        source_id=None,
        source_description=description,
        source_url=None,
        estimated=True,
    )
