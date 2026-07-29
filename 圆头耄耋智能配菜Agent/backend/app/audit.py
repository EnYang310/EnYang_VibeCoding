from collections import defaultdict
from typing import Dict, Iterable, Optional, Union

from .models import (
    GeneratePlanRequest,
    MealPlanDraft,
    Recipe,
    RecipeDraft,
)
from .validation import normalize_identity


METHOD_TERMS = (
    ("凉拌", ("凉拌", "拌匀")),
    ("蒸", ("清蒸", "蒸制", "蒸熟", "上锅蒸")),
    ("烤", ("烘烤", "烤箱", "烤制")),
    ("煎", ("煎制", "煎至", "香煎")),
    ("炒", ("翻炒", "炒制", "快炒", "小炒")),
    ("炖", ("炖煮", "焖炖", "炖至")),
    ("焖", ("焖制", "焖煮", "焖至")),
    ("汤", ("煮汤", "汤品")),
    ("煮", ("水煮", "煮制", "煮至", "焯水")),
)
RecipeLike = Union[RecipeDraft, Recipe]


def _normalize(value: str) -> str:
    return normalize_identity(value)


def _same_food(left: str, right: str) -> bool:
    left_normalized = _normalize(left)
    right_normalized = _normalize(right)
    return (
        left_normalized == right_normalized
        or left_normalized in right_normalized
        or right_normalized in left_normalized
    )


def find_inventory_name(
    name: str,
    inventory: Iterable[str],
) -> Optional[str]:
    candidates = list(inventory)
    normalized_name = _normalize(name)
    for candidate in candidates:
        if _normalize(candidate) == normalized_name:
            return candidate
    fuzzy_matches = [
        candidate for candidate in candidates if _same_food(name, candidate)
    ]
    return max(fuzzy_matches, key=len) if fuzzy_matches else None


def infer_primary_method(recipe: RecipeLike) -> str:
    text = " ".join(
        [
            recipe.name,
            recipe.description,
            *(step.title for step in recipe.steps),
            *(step.detail for step in recipe.steps),
            *recipe.tags,
        ]
    )
    for method, terms in METHOD_TERMS:
        if any(term in text for term in terms):
            return method
    return "其他"


def normalize_plan_inventory(
    draft: MealPlanDraft,
    request: GeneratePlanRequest,
) -> MealPlanDraft:
    inventory = {
        item.name: item.estimatedGrams for item in request.ingredients
    }
    totals: Dict[str, float] = defaultdict(float)
    for meal in draft.meals:
        for recipe in meal.recipes:
            for line in recipe.ingredients + recipe.seasonings:
                inventory_name = find_inventory_name(line.name, inventory)
                if inventory_name:
                    totals[inventory_name] += line.grams

    factors = {
        name: min(1.0, inventory[name] / total)
        for name, total in totals.items()
        if total > 0
    }
    if all(factor >= 1.0 for factor in factors.values()):
        return draft

    meals = []
    for meal in draft.meals:
        recipes = []
        for recipe in meal.recipes:
            ingredients = []
            for line in recipe.ingredients:
                inventory_name = find_inventory_name(line.name, inventory)
                factor = factors.get(inventory_name or "", 1.0)
                scaled = round(line.grams * factor, 1)
                ingredients.append(
                    line.model_copy(update={"grams": max(0.1, scaled)})
                )
            seasonings = []
            for line in recipe.seasonings:
                inventory_name = find_inventory_name(line.name, inventory)
                factor = factors.get(inventory_name or "", 1.0)
                scaled = round(line.grams * factor, 1)
                seasonings.append(
                    line.model_copy(update={"grams": max(0.1, scaled)})
                )
            recipes.append(
                recipe.model_copy(
                    update={
                        "ingredients": ingredients,
                        "seasonings": seasonings,
                    }
                )
            )
        meals.append(meal.model_copy(update={"recipes": recipes}))
    return draft.model_copy(update={"meals": meals})
