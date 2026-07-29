import asyncio
import json
from typing import Any, Dict, List

from .nutrition import fetch_usda_nutrition


LOOKUP_USDA_NUTRITION_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "lookup_usda_nutrition",
        "description": (
            "批量查询 USDA FoodData Central 的 Foundation Foods / SR Legacy。"
            "在输出最终菜谱前必须调用一次，传入全部去重食材和调料的英文标准查询词。"
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": ["queries"],
            "properties": {
                "queries": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 40,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["name", "query", "fallbackQuery"],
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "菜单中展示的中文食材或调料名",
                            },
                            "query": {
                                "type": "string",
                                "description": (
                                    "用于 USDA FoodData Central 的英文标准食物查询词，"
                                    "包含必要的 raw/cooked 状态"
                                ),
                            },
                            "fallbackQuery": {
                                "type": "string",
                                "description": (
                                    "与 query 不同的备用英文标准食物查询词；"
                                    "主查询在本地知识库未命中时使用"
                                ),
                            },
                        },
                    },
                }
            },
        },
    },
}


async def execute_usda_lookup(arguments_json: str) -> str:
    try:
        arguments = json.loads(arguments_json)
        raw_queries = arguments["queries"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return json.dumps(
            {"ok": False, "error": "工具参数不是合法的 queries 数组"},
            ensure_ascii=False,
        )

    unique: Dict[str, Dict[str, str]] = {}
    for item in raw_queries:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        query = str(item.get("query", "")).strip()
        fallback_query = str(item.get("fallbackQuery", "")).strip()
        if name and query and fallback_query:
            unique[query] = {
                "name": name,
                "fallbackQuery": fallback_query,
            }

    results = await asyncio.gather(
        *(
            fetch_usda_nutrition(
                query,
                item["fallbackQuery"],
            )
            for query, item in unique.items()
        )
    )
    matches: List[Dict[str, Any]] = []
    for (query, item), result in zip(unique.items(), results):
        name = item["name"]
        fallback_query = item["fallbackQuery"]
        if result:
            matches.append(
                {
                    "name": name,
                    "query": query,
                    "fallbackQuery": fallback_query,
                    "matched": True,
                    "kcalPer100g": result.kcal_per_100g,
                    "source": result.source,
                    "fdcId": result.source_id,
                    "description": result.source_description,
                    "sourceUrl": result.source_url,
                }
            )
        else:
            matches.append(
                {
                    "name": name,
                    "query": query,
                    "fallbackQuery": fallback_query,
                    "matched": False,
                    "message": "USDA 未匹配；最终结果必须标记为耄耋估算",
                }
            )

    return json.dumps(
        {
            "ok": True,
            "database": "USDA FoodData Central",
            "matchedCount": sum(1 for item in matches if item["matched"]),
            "unmatchedCount": sum(1 for item in matches if not item["matched"]),
            "results": matches,
        },
        ensure_ascii=False,
    )
