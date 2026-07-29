export type IngredientInput = {
  id: string;
  name: string;
  amount: number;
  unit: string;
  estimatedGrams: number;
};

export type Ingredient = IngredientInput & {
  confidence?: number;
};

export type RecognitionResult = {
  source: "kimi";
  ingredients: Ingredient[];
  warnings: string[];
  skillVersion: string;
};

export type PlanConstraints = {
  people: number;
  mealCount: number;
  tools: string[];
  avoid: string[];
  flavor: string;
};

export type CalorieLine = {
  name: string;
  nutritionQuery: string;
  nutritionFallbackQuery: string;
  grams: number;
  note: string;
  estimatedKcalPer100g?: number | null;
  kcalPer100g: number;
  kcal: number;
  estimated: boolean;
  nutritionSource: string;
  sourceId?: number | null;
  sourceDescription: string;
  sourceUrl?: string | null;
};

export type RecipeStep = {
  title: string;
  detail: string;
  minutes: number;
};

export type Recipe = {
  id: string;
  name: string;
  description: string;
  ingredients: CalorieLine[];
  seasonings: CalorieLine[];
  steps: RecipeStep[];
  totalMinutes: number;
  difficulty: "简单" | "适中";
  lowCalorieReason: string;
  tools: string[];
  tags: string[];
  totalKcal: number;
  perPersonKcal: number;
  calorieEstimated: boolean;
};

export type ApiFailure = {
  code: string;
  message: string;
  retryable: boolean;
};

export type RecipeChannel = {
  id: string;
  revision: number;
  ingredientBudget: IngredientInput[];
  current: Recipe;
};

export type Meal = {
  id: string;
  label: string;
  channels: RecipeChannel[];
  totalKcal: number;
  perPersonKcal: number;
};

export type AgentTraceStep = {
  id: string;
  skill: string;
  title: string;
  detail: string;
  status: "completed" | "repaired" | "warning";
};

export type MealPlan = {
  id: string;
  revision: number;
  source: "kimi";
  title: string;
  summary: string;
  people: number;
  createdAt: string;
  meals: Meal[];
  totalKcal: number;
  perPersonKcal: number;
  tips: string[];
  unusedIngredients: string[];
  warnings: string[];
  disclaimer: string;
  agentTrace: AgentTraceStep[];
  skillVersions: Record<string, string>;
};

export type AsyncJobKind = "recognition" | "plan" | "channel_swap";
export type AsyncJobStatus = "queued" | "running" | "completed" | "failed";

export type AsyncJob<T> = {
  id: string;
  kind: AsyncJobKind;
  status: AsyncJobStatus;
  phase: string;
  message: string;
  version: number;
  result: T | null;
  error: ApiFailure | null;
};

export type ChannelCommandRequest = {
  planId: string;
  channelId: string;
  planRevision: number;
  channelRevision: number;
  idempotencyKey: string;
};

export type ChannelSwapRequest = ChannelCommandRequest;

export type ChannelSwapResult = {
  plan: MealPlan;
  channelId: string;
};

export type ActiveSwap = {
  planId: string;
  channelId: string;
  jobId: string;
  jobVersion: number;
  startedAt: string;
};

export type SessionV2 = {
  version: 2;
  savedAt: string;
  plan: MealPlan;
  ingredients: Ingredient[];
  constraints: PlanConstraints;
  activeSwap: ActiveSwap | null;
};
