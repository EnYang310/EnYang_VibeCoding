import asyncio
import logging
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .models import (
    CalorieLine,
    FoodLineDraft,
    Meal,
    MealPlan,
    Recipe,
    RecipeDraft,
)
from .nutrition import (
    NutritionMatch,
    fetch_usda_nutrition,
    kimi_estimate,
    normalize_nutrition_query,
)


DISCLAIMER = "热量为基础估算，实际数值会因食材品牌、用油量和烹饪损耗而变化。"
NUTRITION_ESTIMATE_WARNING = (
    "部分食材未匹配 USDA FoodData Central，已明确标记为耄耋估算。"
)
NutritionQueryKey = Tuple[str, str]
logger = logging.getLogger("uvicorn.error")


def nutrition_query_key(line: FoodLineDraft) -> NutritionQueryKey:
    return (
        normalize_nutrition_query(line.nutritionQuery),
        normalize_nutrition_query(line.nutritionFallbackQuery),
    )


def match_for_line(
    line: FoodLineDraft,
    matches: Dict[NutritionQueryKey, Optional[NutritionMatch]],
) -> NutritionMatch:
    return matches.get(nutrition_query_key(line)) or kimi_estimate(
        line.estimatedKcalPer100g,
        "{}（USDA 未匹配）".format(line.name),
    )


def calculate_line(
    line: FoodLineDraft, match: NutritionMatch
) -> CalorieLine:
    return CalorieLine(
        **line.model_dump(),
        kcalPer100g=match.kcal_per_100g,
        kcal=round(line.grams * match.kcal_per_100g / 100),
        estimated=match.estimated,
        nutritionSource=match.source,
        sourceId=match.source_id,
        sourceDescription=match.source_description,
        sourceUrl=match.source_url,
    )


async def calculate_recipe(
    draft: RecipeDraft,
    people: int,
    recipe_id: str,
    matches: Dict[NutritionQueryKey, Optional[NutritionMatch]],
) -> Tuple[Recipe, bool]:
    ingredients = [
        calculate_line(item, match_for_line(item, matches))
        for item in draft.ingredients
    ]
    seasonings = [
        calculate_line(item, match_for_line(item, matches))
        for item in draft.seasonings
    ]
    total_kcal = sum(item.kcal for item in ingredients + seasonings)
    has_estimate = any(item.estimated for item in ingredients + seasonings)

    recipe_data = draft.model_dump(
        exclude={"ingredients", "seasonings"}
    )
    recipe = Recipe(
        **recipe_data,
        id=recipe_id,
        ingredients=ingredients,
        seasonings=seasonings,
        totalKcal=total_kcal,
        perPersonKcal=round(total_kcal / people),
        calorieEstimated=has_estimate,
    )
    return recipe, has_estimate


async def _resolve_match(
    primary: str,
    fallback: str,
) -> Optional[NutritionMatch]:
    try:
        return await fetch_usda_nutrition(primary, fallback)
    except Exception as exc:
        logger.warning(
            "Nutrition lookup ignored: query=%r fallback=%r error=%s",
            primary,
            fallback,
            type(exc).__name__,
        )
        return None


async def _resolve_matches(
    lines: List[FoodLineDraft],
) -> Dict[NutritionQueryKey, Optional[NutritionMatch]]:
    unique = {
        nutrition_query_key(line)
        for line in lines
    }
    keys = sorted(unique)
    results = await asyncio.gather(
        *(_resolve_match(primary, fallback) for primary, fallback in keys)
    )
    return dict(zip(keys, results))


async def calculate_recipe_draft(
    draft: RecipeDraft,
    people: int,
    recipe_id: str,
) -> Recipe:
    matches = await _resolve_matches(
        list(draft.ingredients) + list(draft.seasonings)
    )
    recipe, _ = await calculate_recipe(
        draft,
        people,
        recipe_id,
        matches,
    )
    return recipe


async def calculate_drafts(
    drafts: Sequence[RecipeDraft],
    people: int,
    recipe_ids: Sequence[str],
) -> List[Recipe]:
    if len(drafts) != len(recipe_ids):
        raise ValueError("drafts 与 recipe_ids 数量必须一致")
    if people < 1:
        raise ValueError("people 必须大于 0")

    all_lines = [
        line
        for draft in drafts
        for line in list(draft.ingredients) + list(draft.seasonings)
    ]
    matches = await _resolve_matches(all_lines)
    recipes = []
    for draft, recipe_id in zip(drafts, recipe_ids):
        recipe, _ = await calculate_recipe(
            draft,
            people,
            recipe_id,
            matches,
        )
        recipes.append(recipe)
    return recipes


def iter_current_recipes(meals: Iterable[Meal]) -> Iterable[Recipe]:
    for meal in meals:
        for channel in meal.channels:
            yield channel.current


def recompute_meal_visible_totals(meal: Meal, people: int) -> Meal:
    total_kcal = sum(
        channel.current.totalKcal
        for channel in meal.channels
    )
    return meal.model_copy(
        update={
            "totalKcal": total_kcal,
            "perPersonKcal": round(total_kcal / people),
        }
    )


def reconcile_nutrition_warnings(
    warnings: Sequence[str],
    meals: Sequence[Meal],
) -> List[str]:
    preserved = [
        warning
        for warning in warnings
        if warning != NUTRITION_ESTIMATE_WARNING
    ]
    if any(
        recipe.calorieEstimated
        for recipe in iter_current_recipes(meals)
    ):
        preserved.append(NUTRITION_ESTIMATE_WARNING)
    return preserved


def recompute_visible_nutrition(plan: MealPlan) -> MealPlan:
    meals = [
        recompute_meal_visible_totals(meal, plan.people)
        for meal in plan.meals
    ]
    total_kcal = sum(meal.totalKcal for meal in meals)
    return plan.model_copy(
        update={
            "meals": meals,
            "totalKcal": total_kcal,
            "perPersonKcal": round(total_kcal / plan.people),
            "warnings": reconcile_nutrition_warnings(
                plan.warnings,
                meals,
            ),
        }
    )
