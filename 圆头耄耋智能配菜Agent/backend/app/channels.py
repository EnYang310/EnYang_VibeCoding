import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable, Dict, List, Optional, Sequence, Tuple, Union
from uuid import uuid4

from .audit import find_inventory_name
from .jobs import AsyncJobStore
from .kimi import AppError, chat_completion, parse_or_repair_structured_message
from .models import (
    AgentTraceStep,
    AsyncJobResponse,
    ChannelSwapRequest,
    ChannelSwapResult,
    GeneratePlanRequest,
    IngredientInput,
    Meal,
    MealPlan,
    MealPlanDraft,
    PlanAuditResult,
    PlanConstraints,
    Recipe,
    RecipeChannel,
    RecipeDraft,
)


ESTIMATE_WARNING = "部分食材未匹配 USDA FoodData Central，已明确标记为耄耋估算。"
MAX_CHANNEL_AUDITS = 3
SwapRecipeFactory = Callable[
    [str, Tuple[IngredientInput, ...], Recipe, PlanConstraints, str],
    Awaitable[Recipe],
]


@dataclass(frozen=True)
class InitialChannelDraft:
    channel_id: str
    ingredient_budget: Tuple[IngredientInput, ...]
    current: RecipeDraft


@dataclass(frozen=True)
class RegisteredPlan:
    plan: MealPlan
    source: GeneratePlanRequest


@dataclass(frozen=True)
class IdempotencyRecord:
    fingerprint: str
    job_id: str
    expires_at: float


def _constraints_from_source(source: GeneratePlanRequest) -> PlanConstraints:
    return PlanConstraints.model_validate(
        source.model_dump(exclude={"ingredients"})
    )


def find_channel(plan: MealPlan, channel_id: str) -> RecipeChannel:
    for meal in plan.meals:
        for channel in meal.channels:
            if channel.id == channel_id:
                return channel
    raise AppError(
        "CHANNEL_NOT_FOUND",
        "没有找到这道菜的位置，请刷新菜单后再试。",
        404,
        False,
    )


def derive_channel_budget(
    recipe: RecipeDraft,
    source: GeneratePlanRequest,
) -> Tuple[IngredientInput, ...]:
    source_by_name = {item.name: item for item in source.ingredients}
    allocated: Dict[str, float] = {}
    for line in recipe.ingredients:
        source_name = find_inventory_name(line.name, source_by_name)
        if source_name is None:
            continue
        allocated[source_name] = allocated.get(source_name, 0.0) + line.grams

    budget = tuple(
        source_by_name[name].model_copy(
            update={"estimatedGrams": round(grams, 1)}
        )
        for name, grams in allocated.items()
        if grams > 0
    )
    if not budget:
        raise AppError(
            "CHANNEL_BUDGET_EMPTY",
            "这道菜没有可用于换菜的主要食材，请重新生成菜单。",
            502,
            True,
        )
    return budget


def _recipe_draft_from_recipe(recipe: Recipe) -> RecipeDraft:
    payload = recipe.model_dump(
        exclude={
            "id",
            "totalKcal",
            "perPersonKcal",
            "calorieEstimated",
        }
    )
    calorie_fields = {
        "kcalPer100g",
        "kcal",
        "estimated",
        "nutritionSource",
        "sourceId",
        "sourceDescription",
        "sourceUrl",
    }
    for field_name in ("ingredients", "seasonings"):
        payload[field_name] = [
            {
                key: value
                for key, value in line.items()
                if key not in calorie_fields
            }
            for line in payload[field_name]
        ]
    return RecipeDraft.model_validate(payload)


async def generate_channel_swap_candidate(
    *,
    api_key: str,
    channel_id: str,
    ingredient_budget: Sequence[IngredientInput],
    current: Union[RecipeDraft, Recipe],
    constraints: PlanConstraints,
) -> RecipeDraft:
    from .prompts import (
        build_channel_audit_messages,
        build_channel_swap_messages,
    )

    current_draft = (
        current
        if isinstance(current, RecipeDraft)
        else _recipe_draft_from_recipe(current)
    )
    candidate: Optional[RecipeDraft] = None
    violations: List[str] = []
    for _ in range(MAX_CHANNEL_AUDITS):
        message = await chat_completion(
            api_key,
            build_channel_swap_messages(
                channel_id=channel_id,
                ingredient_budget=tuple(ingredient_budget),
                current=current_draft,
                constraints=constraints,
                candidate=candidate,
                violations=violations,
            ),
            2600,
            reasoning_effort="low",
            response_model=RecipeDraft,
            schema_name="channel_swap_recipe",
        )
        parsed = await parse_or_repair_structured_message(
            api_key=api_key,
            message=message,
            response_model=RecipeDraft,
            schema_name="channel_swap_recipe",
            error_message="新菜的信息不完整，请重新换菜。",
            max_completion_tokens=2600,
        )
        candidate = RecipeDraft.model_validate(parsed)
        audit_message = await chat_completion(
            api_key,
            build_channel_audit_messages(
                channel_id=channel_id,
                ingredient_budget=tuple(ingredient_budget),
                current=current_draft,
                candidate=candidate,
                constraints=constraints,
            ),
            500,
            reasoning_effort="low",
            response_model=PlanAuditResult,
            schema_name="channel_swap_audit",
        )
        audit_parsed = await parse_or_repair_structured_message(
            api_key=api_key,
            message=audit_message,
            response_model=PlanAuditResult,
            schema_name="channel_swap_audit",
            error_message="新菜合格审核结果不完整。",
            max_completion_tokens=500,
        )
        audit = PlanAuditResult.model_validate(audit_parsed)
        violations = list(
            dict.fromkeys(
                violation.strip()
                for violation in audit.violations
                if violation.strip()
            )
        )
        if audit.passed and not violations:
            return candidate
        if not violations:
            summary = audit.summary.strip()
            if not summary:
                raise AppError(
                    "CHANNEL_SWAP_AUDIT_INVALID",
                    "新菜审核结果无效，请再试一次。",
                    502,
                    True,
                )
            violations = [summary]
    raise AppError(
        "CHANNEL_SWAP_AUDIT_FAILED",
        "这次找到的新菜没有通过检查，请再试一次。",
        502,
        True,
    )


async def build_initial_channel_drafts(
    *,
    draft: MealPlanDraft,
    source: GeneratePlanRequest,
) -> List[List[InitialChannelDraft]]:
    return [
        [
            InitialChannelDraft(
                channel_id="channel-{}-{}-{}".format(
                    uuid4().hex[:10],
                    meal_index,
                    recipe_index,
                ),
                ingredient_budget=derive_channel_budget(recipe, source),
                current=recipe,
            )
            for recipe_index, recipe in enumerate(meal.recipes)
        ]
        for meal_index, meal in enumerate(draft.meals)
    ]


async def calculate_channel_plan(
    *,
    draft: MealPlanDraft,
    channels: List[List[InitialChannelDraft]],
    people: int,
    agent_trace: Optional[List[AgentTraceStep]] = None,
    versions: Optional[Dict[str, str]] = None,
) -> MealPlan:
    from .calories import DISCLAIMER, calculate_drafts, recompute_visible_nutrition

    plan_token = uuid4().hex[:12]
    if len(channels) != len(draft.meals):
        raise ValueError("channels 与 meals 数量必须一致")

    flat_drafts: List[RecipeDraft] = []
    recipe_ids: List[str] = []
    channel_layout: List[List[Tuple[InitialChannelDraft, int]]] = []
    for meal_draft, meal_channels in zip(draft.meals, channels):
        if len(meal_channels) != len(meal_draft.recipes):
            raise ValueError("每餐 channels 与 recipes 数量必须一致")
        layout: List[Tuple[InitialChannelDraft, int]] = []
        for channel in meal_channels:
            current_index = len(flat_drafts)
            flat_drafts.append(channel.current)
            recipe_ids.append(
                "recipe-{}-current".format(channel.channel_id)
            )
            layout.append((channel, current_index))
        channel_layout.append(layout)

    calculated = await calculate_drafts(
        flat_drafts,
        people=people,
        recipe_ids=recipe_ids,
    )
    meals: List[Meal] = []
    for meal_index, (meal_draft, layout) in enumerate(
        zip(draft.meals, channel_layout)
    ):
        calculated_channels = [
            RecipeChannel(
                id=channel.channel_id,
                revision=0,
                ingredientBudget=channel.ingredient_budget,
                current=calculated[current_index],
            )
            for channel, current_index in layout
        ]
        total_kcal = sum(
            channel.current.totalKcal for channel in calculated_channels
        )
        meals.append(
            Meal(
                id="meal-{}-{}".format(plan_token, meal_index),
                label=meal_draft.label,
                channels=calculated_channels,
                totalKcal=total_kcal,
                perPersonKcal=round(total_kcal / people),
            )
        )

    total_kcal = sum(meal.totalKcal for meal in meals)
    plan = MealPlan(
        id="plan-{}".format(plan_token),
        revision=0,
        title=draft.title,
        summary=draft.summary,
        people=people,
        createdAt=datetime.now(timezone.utc).isoformat(),
        meals=meals,
        totalKcal=total_kcal,
        perPersonKcal=round(total_kcal / people),
        tips=draft.tips,
        unusedIngredients=draft.unusedIngredients,
        warnings=[],
        disclaimer=DISCLAIMER,
        agentTrace=agent_trace or [],
        skillVersions=versions or {},
    )
    return recompute_visible_nutrition(plan)


def _recompute_plan(
    plan: MealPlan,
    meals: List[Meal],
    revision: int,
) -> MealPlan:
    recalculated: List[Meal] = []
    has_estimate = False
    for meal in meals:
        total = sum(channel.current.totalKcal for channel in meal.channels)
        has_estimate = has_estimate or any(
            channel.current.calorieEstimated for channel in meal.channels
        )
        recalculated.append(
            meal.model_copy(
                update={
                    "totalKcal": total,
                    "perPersonKcal": round(total / plan.people),
                }
            )
        )
    warnings = [item for item in plan.warnings if item != ESTIMATE_WARNING]
    if has_estimate:
        warnings.append(ESTIMATE_WARNING)
    total_kcal = sum(meal.totalKcal for meal in recalculated)
    return plan.model_copy(
        update={
            "revision": revision,
            "meals": recalculated,
            "totalKcal": total_kcal,
            "perPersonKcal": round(total_kcal / plan.people),
            "warnings": warnings,
        }
    )


def _replace_channel(
    plan: MealPlan,
    channel_id: str,
    replacement: RecipeChannel,
) -> MealPlan:
    found = False
    meals: List[Meal] = []
    for meal in plan.meals:
        channels: List[RecipeChannel] = []
        for channel in meal.channels:
            if channel.id == channel_id:
                channels.append(replacement)
                found = True
            else:
                channels.append(channel)
        meals.append(meal.model_copy(update={"channels": channels}))
    if not found:
        raise AppError(
            "CHANNEL_NOT_FOUND",
            "没有找到这道菜的位置，请刷新菜单后再试。",
            404,
            False,
        )
    return _recompute_plan(plan, meals, plan.revision + 1)


class RecipeChannelService:
    def __init__(
        self,
        job_store: AsyncJobStore,
        *,
        swap_recipe_factory: Optional[SwapRecipeFactory] = None,
        idempotency_ttl_seconds: float = 1800,
    ) -> None:
        self._job_store = job_store
        self._swap_recipe_factory = (
            swap_recipe_factory or self._default_swap_recipe
        )
        self._idempotency_ttl_seconds = idempotency_ttl_seconds
        self._plans: Dict[str, RegisteredPlan] = {}
        self._idempotency: Dict[str, IdempotencyRecord] = {}
        self._active_swap_job_id: Optional[str] = None

    @property
    def active_swap_job_id(self) -> Optional[str]:
        return self._active_swap_job_id

    def register_plan(
        self,
        plan: MealPlan,
        source: GeneratePlanRequest,
    ) -> MealPlan:
        self._plans[plan.id] = RegisteredPlan(plan=plan, source=source)
        return plan

    def get_plan(self, plan_id: str) -> MealPlan:
        registered = self._plans.get(plan_id)
        if registered is None:
            raise AppError(
                "PLAN_NOT_FOUND",
                "这份菜单已经失效，请重新生成。",
                404,
                True,
            )
        return registered.plan

    def get_swap_job(self, job_id: str) -> Optional[dict]:
        job = self._job_store.get(job_id)
        if job is None or job.get("kind") != "channel_swap":
            return None
        return job

    @staticmethod
    def _fingerprint(request: ChannelSwapRequest) -> str:
        payload = (
            request.planId,
            request.channelId,
            request.planRevision,
            request.channelRevision,
        )
        return hashlib.sha256(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _cleanup_idempotency(self) -> None:
        now = time.monotonic()
        expired = [
            key
            for key, record in self._idempotency.items()
            if record.expires_at <= now
        ]
        for key in expired:
            self._idempotency.pop(key, None)

    def _replay(
        self,
        request: ChannelSwapRequest,
    ) -> Optional[AsyncJobResponse[ChannelSwapResult]]:
        self._cleanup_idempotency()
        record = self._idempotency.get(request.idempotencyKey)
        if record is None:
            return None
        if record.fingerprint != self._fingerprint(request):
            self._ensure_idle()
            raise AppError(
                "IDEMPOTENCY_CONFLICT",
                "这次操作标识已用于另一条换菜请求，请重新点击。",
                409,
                False,
            )
        job = self._job_store.get(record.job_id)
        if job is None:
            raise AppError(
                "CHANNEL_SWAP_JOB_NOT_FOUND",
                "这次换菜任务已经失效，请刷新菜单。",
                404,
                True,
            )
        return AsyncJobResponse[ChannelSwapResult].model_validate(job)

    def _validate_request(
        self,
        request: ChannelSwapRequest,
    ) -> Tuple[RegisteredPlan, RecipeChannel]:
        registered = self._plans.get(request.planId)
        if registered is None:
            raise AppError(
                "PLAN_NOT_FOUND",
                "这份菜单已经失效，请重新生成。",
                404,
                True,
            )
        plan = registered.plan
        if plan.revision != request.planRevision:
            raise AppError(
                "PLAN_REVISION_CONFLICT",
                "菜单已经更新，请刷新后再换菜。",
                409,
                True,
            )
        channel = find_channel(plan, request.channelId)
        if channel.revision != request.channelRevision:
            raise AppError(
                "CHANNEL_REVISION_CONFLICT",
                "这道菜已经更新，请刷新后再操作。",
                409,
                True,
            )
        return registered, channel

    def _ensure_idle(self) -> None:
        if self._active_swap_job_id is not None:
            raise AppError(
                "REPLACEMENT_BUSY",
                "别急，一个一个来！",
                409,
                True,
            )

    def _store_plan(
        self,
        registered: RegisteredPlan,
        plan: MealPlan,
    ) -> None:
        self._plans[plan.id] = RegisteredPlan(
            plan=plan,
            source=registered.source,
        )

    def _clear_active_swap(self, job_id: str) -> None:
        if self._active_swap_job_id == job_id:
            self._active_swap_job_id = None

    def begin_swap(
        self,
        request: ChannelSwapRequest,
        api_key: str,
    ) -> AsyncJobResponse[ChannelSwapResult]:
        replay = self._replay(request)
        if replay is not None:
            return replay
        self._ensure_idle()
        registered, channel = self._validate_request(request)
        job_identity: Dict[str, str] = {}

        async def runner(progress):
            progress("swapping", "耄耋正在按当前食材换一道新菜…")
            return await self._run_swap(
                job_id=job_identity["id"],
                plan_id=registered.plan.id,
                channel_id=channel.id,
                expected_plan_revision=registered.plan.revision,
                expected_channel_revision=channel.revision,
                api_key=api_key,
            )

        def on_failure(job_id: str, _error: dict) -> None:
            self._clear_active_swap(job_id)

        job = self._job_store.start(
            "channel_swap",
            runner,
            dedupe_key="swap:{}".format(request.idempotencyKey),
            timeout_seconds=900,
            on_failure=on_failure,
        )
        job_identity["id"] = job["id"]
        self._active_swap_job_id = job["id"]
        self._idempotency[request.idempotencyKey] = IdempotencyRecord(
            fingerprint=self._fingerprint(request),
            job_id=job["id"],
            expires_at=time.monotonic() + self._idempotency_ttl_seconds,
        )
        return AsyncJobResponse[ChannelSwapResult].model_validate(job)

    async def _default_swap_recipe(
        self,
        channel_id: str,
        budget: Tuple[IngredientInput, ...],
        current: Recipe,
        constraints: PlanConstraints,
        api_key: str,
    ) -> Recipe:
        from .calories import calculate_recipe_draft

        draft = await generate_channel_swap_candidate(
            api_key=api_key,
            channel_id=channel_id,
            ingredient_budget=budget,
            current=current,
            constraints=constraints,
        )
        return await calculate_recipe_draft(
            draft,
            constraints.people,
            "recipe-swap-{}".format(uuid4().hex[:12]),
        )

    def _finish_success(
        self,
        plan_id: str,
        channel_id: str,
        expected_plan_revision: int,
        expected_channel_revision: int,
        replacement: Recipe,
    ) -> MealPlan:
        registered = self._plans[plan_id]
        plan = registered.plan
        channel = find_channel(plan, channel_id)
        if (
            plan.revision != expected_plan_revision
            or channel.revision != expected_channel_revision
        ):
            raise AppError(
                "CHANNEL_REVISION_CONFLICT",
                "换菜完成时菜单状态已经变化，请刷新。",
                409,
                True,
            )
        updated_channel = channel.model_copy(
            update={
                "revision": channel.revision + 1,
                "current": replacement,
            }
        )
        updated = _replace_channel(plan, channel_id, updated_channel)
        self._store_plan(registered, updated)
        return updated

    async def _run_swap(
        self,
        *,
        job_id: str,
        plan_id: str,
        channel_id: str,
        expected_plan_revision: int,
        expected_channel_revision: int,
        api_key: str,
    ) -> ChannelSwapResult:
        try:
            registered = self._plans[plan_id]
            channel = find_channel(registered.plan, channel_id)
            replacement = await self._swap_recipe_factory(
                channel_id,
                tuple(channel.ingredientBudget),
                channel.current,
                _constraints_from_source(registered.source),
                api_key,
            )
            plan = self._finish_success(
                plan_id,
                channel_id,
                expected_plan_revision,
                expected_channel_revision,
                replacement,
            )
            return ChannelSwapResult(plan=plan, channelId=channel_id)
        finally:
            self._clear_active_swap(job_id)
