import json
from typing import Any, Dict, List, Optional, Sequence, Union

from .audit import infer_primary_method
from .contracts import compact_contract_skeleton
from .models import (
    MODEL_CONTRACT_VERSION,
    GeneratePlanRequest,
    IngredientInput,
    MealPlanDraft,
    PlanAuditResult,
    PlanConstraints,
    Recipe,
    RecipeDraft,
    RecognizeModelResult,
)
from .skills import load_skill


RECOGNITION_PROMPT_VERSION = "recognition-v1.6.0"
PLAN_PROMPT_VERSION = "meal-plan-v1.6.0"
CHANNEL_PROMPT_VERSION = "recipe-channel-swap-v1.7.0"


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _fixed_output(model) -> str:
    return "\n".join(
        [
            "# FIXED_OUTPUT",
            MODEL_CONTRACT_VERSION,
            compact_contract_skeleton(model),
            "只返回一个 JSON 对象，不输出 Markdown，不增加字段。",
        ]
    )


def recognition_user_prompt() -> str:
    return "\n".join(
        [
            "# TASK",
            "分析随本消息提供的食材照片，只返回结构化食材事实。",
            "# EMPTY",
            "没有可靠食材时返回空 ingredients，并在 warnings 提醒重新拍摄。",
            _fixed_output(RecognizeModelResult),
        ]
    )


def build_plan_user_prompt(request: GeneratePlanRequest) -> str:
    return "\n".join(
        [
            "# TASK",
            "用现有食材设计能直接下厨的低热量家常菜。餐次数必须准确；食材不足就少做，不得违反忌口、厨具和库存。",
            "# FACTS",
            _json(request),
            _fixed_output(MealPlanDraft),
        ]
    )


def build_plan_messages(request: GeneratePlanRequest) -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": load_skill("meal-planning"),
        },
        {
            "role": "user",
            "content": build_plan_user_prompt(request),
        },
    ]


def _audit_line_facts(lines: Sequence[Any]) -> List[Dict[str, Any]]:
    return [
        {
            "name": line.name,
            "grams": line.grams,
        }
        for line in lines
    ]


def audit_snapshot(
    draft: MealPlanDraft,
    request: GeneratePlanRequest,
) -> Dict[str, Any]:
    return {
        "constraints": {
            "mealCount": request.mealCount,
            "tools": request.tools,
            "avoid": request.avoid,
        },
        "inventory": [
            {
                "name": item.name,
                "grams": item.estimatedGrams,
            }
            for item in request.ingredients
        ],
        "meals": [
            {
                "label": meal.label,
                "recipes": [
                    {
                        "name": recipe.name,
                        "ingredients": _audit_line_facts(recipe.ingredients),
                        "seasonings": _audit_line_facts(recipe.seasonings),
                        "tools": recipe.tools,
                        "steps": [
                            "{}：{}".format(step.title, step.detail)
                            for step in recipe.steps
                        ],
                    }
                    for recipe in meal.recipes
                ],
            }
            for meal in draft.meals
        ]
    }


def build_audit_messages(
    draft: MealPlanDraft,
    request: GeneratePlanRequest,
) -> List[Dict[str, str]]:
    prompt = "\n".join(
        [
            "# TASK",
            "你是唯一业务合格审核者。只按 Skill 做宽松的最低合格检查，不修改菜单。",
            "# MENU_FACTS",
            _json(audit_snapshot(draft, request)),
            "# RULES",
            "只拒绝事实中明确可证的基础错误；有疑问一律通过。禁止评价营养、口味、搭配、措辞、菜名创意或做法优劣。",
            _fixed_output(PlanAuditResult),
        ]
    )
    return [
        {"role": "system", "content": load_skill("plan-audit")},
        {"role": "user", "content": prompt},
    ]


def build_plan_repair_messages(
    request: GeneratePlanRequest,
    draft: MealPlanDraft,
    violations: Sequence[str],
) -> List[Dict[str, str]]:
    prompt = "\n".join(
        [
            "# TASK",
            "只修复 LLM 审核列出的明确基础错误，其他菜品与数值尽量保持不变，返回完整菜单。",
            "# REQUEST",
            _json(request),
            "# CURRENT",
            _json(draft),
            "# FIX_ONLY",
            _json(list(violations)),
            _fixed_output(MealPlanDraft),
        ]
    )
    return [
        {"role": "system", "content": load_skill("meal-planning")},
        {"role": "user", "content": prompt},
    ]


def _compact_current(current: Union[RecipeDraft, Recipe]) -> Dict[str, Any]:
    return {
        "name": current.name,
        "ingredientNames": [line.name for line in current.ingredients],
        "primaryMethod": infer_primary_method(current),
        "tools": current.tools,
        "tags": current.tags,
    }


def build_channel_swap_messages(
    *,
    channel_id: str,
    ingredient_budget: Sequence[IngredientInput],
    current: Union[RecipeDraft, Recipe],
    constraints: PlanConstraints,
    candidate: Optional[RecipeDraft],
    violations: Sequence[str],
) -> List[Dict[str, str]]:
    facts = {
        "channelId": channel_id,
        "ingredientBudget": [
            {
                "id": item.id,
                "name": item.name,
                "grams": item.estimatedGrams,
            }
            for item in ingredient_budget
        ],
        "current": _compact_current(current),
        "constraints": {
            "people": constraints.people,
            "tools": constraints.tools,
            "avoid": constraints.avoid,
            "flavor": constraints.flavor,
        },
    }
    if candidate is not None:
        facts["candidateToRepair"] = candidate.model_dump()
        facts["repairOnly"] = list(violations)
    task = (
        "只为这个菜位现做一份不同做法的完整新菜。必须使用 ingredientBudget 中每种核心食材，"
        "不得增加其他非基础主要食材，不得超过各自克数。"
        if candidate is None
        else "只修复 candidateToRepair 中 repairOnly 列出的明确基础错误，保持其他内容不变，返回完整 RecipeDraft。"
    )
    prompt = "\n".join(
        [
            "# TASK",
            task,
            "# TARGET_CHANNEL_ONLY",
            _json(facts),
            _fixed_output(RecipeDraft),
        ]
    )
    return [
        {
            "role": "system",
            "content": load_skill("recipe-channel-swap"),
        },
        {"role": "user", "content": prompt},
    ]


def channel_audit_snapshot(
    *,
    channel_id: str,
    ingredient_budget: Sequence[IngredientInput],
    current: Union[RecipeDraft, Recipe],
    candidate: RecipeDraft,
    constraints: PlanConstraints,
) -> Dict[str, Any]:
    return {
        "channelId": channel_id,
        "constraints": {
            "tools": constraints.tools,
            "avoid": constraints.avoid,
        },
        "ingredientBudget": [
            {
                "name": item.name,
                "grams": item.estimatedGrams,
            }
            for item in ingredient_budget
        ],
        "current": _compact_current(current),
        "candidate": {
            "name": candidate.name,
            "ingredients": _audit_line_facts(candidate.ingredients),
            "seasonings": _audit_line_facts(candidate.seasonings),
            "tools": candidate.tools,
            "steps": [
                "{}：{}".format(step.title, step.detail)
                for step in candidate.steps
            ],
        },
    }


def build_channel_audit_messages(
    *,
    channel_id: str,
    ingredient_budget: Sequence[IngredientInput],
    current: Union[RecipeDraft, Recipe],
    candidate: RecipeDraft,
    constraints: PlanConstraints,
) -> List[Dict[str, str]]:
    prompt = "\n".join(
        [
            "# TASK",
            "你是这个菜品通道唯一的业务合格审核者。只按 Skill 做宽松的最低合格检查，不修改菜品。",
            "# CHANNEL_FACTS",
            _json(
                channel_audit_snapshot(
                    channel_id=channel_id,
                    ingredient_budget=ingredient_budget,
                    current=current,
                    candidate=candidate,
                    constraints=constraints,
                )
            ),
            "# RULES",
            "只拒绝事实中明确可证的基础错误；有疑问一律通过。不得因食材相同、烹饪大类相同、口味或创意不足而拒绝。",
            _fixed_output(PlanAuditResult),
        ]
    )
    return [
        {
            "role": "system",
            "content": load_skill("recipe-channel-audit"),
        },
        {"role": "user", "content": prompt},
    ]
