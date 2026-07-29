from typing import Dict, Generic, List, Literal, Optional, Tuple, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .validation import (
    normalize_identity,
    require_unique,
    validate_usda_query,
)


MODEL_CONTRACT_VERSION = "maodie-model-contract-1.7.0"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApiFailure(StrictModel):
    code: str
    message: str
    retryable: bool


JobResultT = TypeVar("JobResultT")


class AsyncJobResponse(StrictModel, Generic[JobResultT]):
    id: str
    kind: Literal["recognition", "plan", "channel_swap"]
    status: Literal["queued", "running", "completed", "failed"]
    phase: str
    message: str
    version: int = Field(ge=0)
    result: Optional[JobResultT]
    error: Optional[ApiFailure]

    @model_validator(mode="after")
    def validate_terminal_payload(self) -> "AsyncJobResponse":
        if self.status == "completed":
            if self.result is None or self.error is not None:
                raise ValueError("completed job 必须只有 result")
        elif self.status == "failed":
            if self.result is not None or self.error is None:
                raise ValueError("failed job 必须只有 error")
        elif self.result is not None or self.error is not None:
            raise ValueError("非终态 job 不得包含 result/error")
        return self


class IngredientInput(StrictModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=30)
    amount: float = Field(gt=0)
    unit: str = Field(min_length=1, max_length=10)
    estimatedGrams: float = Field(gt=0, le=10000)


class Ingredient(IngredientInput):
    confidence: Optional[float] = Field(default=None, ge=0, le=1)


class RecognizedIngredient(StrictModel):
    name: str = Field(min_length=1, max_length=30)
    amount: float = Field(gt=0)
    unit: str = Field(min_length=1, max_length=10)
    estimatedGrams: float = Field(gt=0, le=10000)
    confidence: float = Field(ge=0, le=1)


class RecognizeRequest(StrictModel):
    imageDataUrl: str = Field(min_length=100, max_length=12_000_000)


class RecognizeModelResult(StrictModel):
    ingredients: List[RecognizedIngredient] = Field(max_length=40)
    warnings: List[str] = Field(max_length=10)


class RecognitionResult(StrictModel):
    source: Literal["kimi"] = "kimi"
    ingredients: List[Ingredient]
    warnings: List[str] = Field(default_factory=list)
    skillVersion: str = "1.0.0"


class PlanConstraints(StrictModel):
    people: int = Field(ge=1, le=8)
    mealCount: int = Field(ge=1, le=4)
    tools: List[str] = Field(default_factory=list, max_length=10)
    avoid: List[str] = Field(default_factory=list, max_length=20)
    flavor: str = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_unique_constraint_items(self) -> "PlanConstraints":
        require_unique(self.tools, "tools")
        require_unique(self.avoid, "avoid")
        return self


class GeneratePlanRequest(PlanConstraints):
    ingredients: List[IngredientInput] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def validate_unique_ingredients(self) -> "GeneratePlanRequest":
        require_unique(
            (ingredient.id for ingredient in self.ingredients),
            "ingredient.id",
        )
        require_unique(
            (ingredient.name for ingredient in self.ingredients),
            "ingredient.name",
        )
        return self


class FoodLineDraft(StrictModel):
    name: str = Field(min_length=1, max_length=40)
    nutritionQuery: str = Field(min_length=2, max_length=120)
    nutritionFallbackQuery: str = Field(min_length=2, max_length=120)
    grams: float = Field(ge=0, le=10000)
    note: str = Field(max_length=80)
    estimatedKcalPer100g: float = Field(ge=0, le=1000)

    @field_validator("nutritionQuery", "nutritionFallbackQuery")
    @classmethod
    def validate_nutrition_query(cls, value: str) -> str:
        return validate_usda_query(value)

    @model_validator(mode="after")
    def validate_distinct_nutrition_queries(self) -> "FoodLineDraft":
        if normalize_identity(self.nutritionQuery) == normalize_identity(
            self.nutritionFallbackQuery
        ):
            raise ValueError("nutrition 主查询与备查询必须不同")
        return self


class RecipeStep(StrictModel):
    title: str = Field(min_length=1, max_length=60)
    detail: str = Field(min_length=1, max_length=500)
    minutes: int = Field(ge=0, le=240)


class RecipeDraft(StrictModel):
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(min_length=1, max_length=180)
    ingredients: List[FoodLineDraft] = Field(min_length=1, max_length=30)
    seasonings: List[FoodLineDraft] = Field(max_length=20)
    steps: List[RecipeStep] = Field(min_length=1, max_length=15)
    totalMinutes: int = Field(gt=0, le=300)
    difficulty: Literal["简单", "适中"]
    lowCalorieReason: str = Field(min_length=1, max_length=240)
    tools: List[str] = Field(max_length=10)
    tags: List[str] = Field(max_length=8)


class MealDraft(StrictModel):
    label: str = Field(min_length=1, max_length=30)
    recipes: List[RecipeDraft] = Field(min_length=1, max_length=8)


class MealPlanDraft(StrictModel):
    title: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=300)
    meals: List[MealDraft] = Field(min_length=1, max_length=4)
    tips: List[str] = Field(max_length=10)
    unusedIngredients: List[str] = Field(max_length=30)


class CalorieLine(FoodLineDraft):
    kcalPer100g: float = Field(ge=0)
    kcal: int = Field(ge=0)
    estimated: bool
    nutritionSource: str
    sourceId: Optional[int] = None
    sourceDescription: str
    sourceUrl: Optional[str] = None


class Recipe(StrictModel):
    id: str = Field(min_length=1)
    name: str
    description: str
    ingredients: List[CalorieLine]
    seasonings: List[CalorieLine]
    steps: List[RecipeStep]
    totalMinutes: int
    difficulty: Literal["简单", "适中"]
    lowCalorieReason: str
    tools: List[str]
    tags: List[str]
    totalKcal: int
    perPersonKcal: int
    calorieEstimated: bool


class RecipeChannel(StrictModel):
    id: str = Field(min_length=1)
    revision: int = Field(ge=0)
    ingredientBudget: Tuple[IngredientInput, ...] = Field(
        min_length=1,
        max_length=40,
    )
    current: Recipe

    @model_validator(mode="after")
    def validate_ingredient_budget(self) -> "RecipeChannel":
        require_unique(
            (ingredient.id for ingredient in self.ingredientBudget),
            "ingredientBudget.id",
        )
        require_unique(
            (ingredient.name for ingredient in self.ingredientBudget),
            "ingredientBudget.name",
        )
        return self


class Meal(StrictModel):
    id: str = Field(min_length=1)
    label: str
    channels: List[RecipeChannel] = Field(min_length=1, max_length=8)
    totalKcal: int
    perPersonKcal: int


class AgentTraceStep(StrictModel):
    id: str
    skill: str
    title: str
    detail: str
    status: Literal["completed", "repaired", "warning"] = "completed"


class PlanAuditResult(StrictModel):
    passed: bool
    violations: List[str] = Field(max_length=12)
    summary: str = Field(min_length=1, max_length=240)


class MealPlan(StrictModel):
    id: str = Field(min_length=1)
    revision: int = Field(ge=0)
    source: Literal["kimi"] = "kimi"
    title: str
    summary: str
    people: int = Field(ge=1, le=8)
    createdAt: str
    meals: List[Meal]
    totalKcal: int = Field(ge=0)
    perPersonKcal: int = Field(ge=0)
    tips: List[str]
    unusedIngredients: List[str]
    warnings: List[str]
    disclaimer: str
    agentTrace: List[AgentTraceStep] = Field(default_factory=list)
    skillVersions: Dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_unique_identifiers(self) -> "MealPlan":
        require_unique(
            (meal.id for meal in self.meals),
            "meal.id",
        )
        channel_ids = [
            channel.id
            for meal in self.meals
            for channel in meal.channels
        ]
        require_unique(channel_ids, "channel.id")
        recipe_ids = [
            channel.current.id
            for meal in self.meals
            for channel in meal.channels
        ]
        require_unique(recipe_ids, "recipe.id")
        return self


class ChannelSwapResult(StrictModel):
    plan: MealPlan
    channelId: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_channel_id(self) -> "ChannelSwapResult":
        channels = [
            channel
            for meal in self.plan.meals
            for channel in meal.channels
            if channel.id == self.channelId
        ]
        if not channels:
            raise ValueError("channelId 不存在于 plan")
        return self


class ChannelSwapRequest(StrictModel):
    planId: str = Field(min_length=1)
    channelId: str = Field(min_length=1)
    planRevision: int = Field(ge=0)
    channelRevision: int = Field(ge=0)
    idempotencyKey: str = Field(min_length=16, max_length=128)
