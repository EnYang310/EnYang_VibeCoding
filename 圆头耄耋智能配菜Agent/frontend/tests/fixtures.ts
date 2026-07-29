import type {
  Ingredient,
  MealPlan,
  PlanConstraints,
  Recipe,
  RecipeChannel,
  SessionV2,
} from "../lib/types";

export function cloneFixture<T>(value: T): T {
  return structuredClone(value);
}

function calorieLine(name: string, grams: number) {
  return {
    name,
    nutritionQuery: `${name} raw`,
    nutritionFallbackQuery: name,
    grams,
    note: "",
    estimatedKcalPer100g: null,
    kcalPer100g: 20,
    kcal: Math.round(grams * 0.2),
    estimated: false,
    nutritionSource: "USDA FoodData Central",
    sourceId: 123,
    sourceDescription: name,
    sourceUrl: "https://fdc.nal.usda.gov/fdc-app.html#/food-details/123",
  };
}

export function recipe(
  id: string,
  name: string,
  ingredient: string,
  grams: number,
): Recipe {
  const line = calorieLine(ingredient, grams);
  return {
    id,
    name,
    description: `${name}说明`,
    ingredients: [line],
    seasonings: [],
    steps: [{ title: "烹饪", detail: "加热至熟。", minutes: 8 }],
    totalMinutes: 10,
    difficulty: "简单",
    lowCalorieReason: "少油。",
    tools: ["炒锅"],
    tags: ["低卡"],
    totalKcal: line.kcal,
    perPersonKcal: Math.round(line.kcal / 2),
    calorieEstimated: false,
  };
}

export const validIngredients: Ingredient[] = [
  {
    id: "ingredient-tomato",
    name: "番茄",
    amount: 2,
    unit: "个",
    estimatedGrams: 300,
    confidence: 0.98,
  },
  {
    id: "ingredient-chicken",
    name: "鸡胸肉",
    amount: 1,
    unit: "块",
    estimatedGrams: 240,
    confidence: 0.96,
  },
];

export const validConstraints: PlanConstraints = {
  people: 2,
  mealCount: 1,
  tools: ["炒锅"],
  avoid: [],
  flavor: "清淡",
};

export const channelA: RecipeChannel = {
  id: "channel-a",
  revision: 0,
  ingredientBudget: [
    {
      id: "ingredient-tomato",
      name: "番茄",
      amount: 2,
      unit: "个",
      estimatedGrams: 300,
    },
  ],
  current: recipe("recipe-a-current", "番茄炒菜", "番茄", 180),
};

export const channelB: RecipeChannel = {
  id: "channel-b",
  revision: 0,
  ingredientBudget: [
    {
      id: "ingredient-chicken",
      name: "鸡胸肉",
      amount: 1,
      unit: "块",
      estimatedGrams: 240,
    },
  ],
  current: recipe("recipe-b-current", "香煎鸡胸", "鸡胸肉", 180),
};

export const validMealPlan = {
  id: "plan-1",
  revision: 0,
  source: "kimi" as const,
  title: "测试菜单",
  summary: "一餐两菜",
  people: 2,
  createdAt: "2026-07-28T00:00:00.000Z",
  meals: [
    {
      id: "meal-1",
      label: "午餐",
      channels: [channelA, channelB],
      totalKcal: channelA.current.totalKcal + channelB.current.totalKcal,
      perPersonKcal:
        channelA.current.perPersonKcal + channelB.current.perPersonKcal,
    },
  ],
  totalKcal: channelA.current.totalKcal + channelB.current.totalKcal,
  perPersonKcal:
    channelA.current.perPersonKcal + channelB.current.perPersonKcal,
  tips: [],
  unusedIngredients: [],
  warnings: [],
  disclaimer: "热量仅供参考。",
  agentTrace: [],
  skillVersions: {},
} as MealPlan;

export const validSessionV2: SessionV2 = {
  version: 2,
  savedAt: "2026-07-28T00:00:00.000Z",
  plan: validMealPlan,
  ingredients: validIngredients,
  constraints: validConstraints,
  activeSwap: null,
};

export function swappingSession(jobId = "job-swap-1"): SessionV2 {
  const session = cloneFixture(validSessionV2);
  session.activeSwap = {
    planId: session.plan.id,
    channelId: "channel-a",
    jobId,
    jobVersion: 0,
    startedAt: "2026-07-28T00:01:00.000Z",
  };
  return session;
}

export const queuedSwapJob = {
  id: "job-swap-1",
  kind: "channel_swap" as const,
  status: "queued" as const,
  phase: "queued",
  message: "任务已创建",
  version: 0,
  result: null,
  error: null,
};
