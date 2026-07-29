import { z } from "zod";

const IdSchema = z.string().min(1);
const NonNegativeIntegerSchema = z.number().int().min(0);

export const IngredientInputSchema = z.strictObject({
  id: IdSchema,
  name: z.string().min(1).max(30),
  amount: z.number().positive(),
  unit: z.string().min(1).max(10),
  estimatedGrams: z.number().positive().max(10_000),
});

export const IngredientSchema = IngredientInputSchema.extend({
  confidence: z.number().min(0).max(1).optional(),
});

export const RecognitionResultSchema = z.strictObject({
  source: z.literal("kimi"),
  ingredients: z.array(IngredientSchema).max(40),
  warnings: z.array(z.string()).max(10),
  skillVersion: z.string().min(1),
});

export const PlanConstraintsSchema = z.strictObject({
  people: z.number().int().min(1).max(8),
  mealCount: z.number().int().min(1).max(4),
  tools: z.array(z.string()).max(10),
  avoid: z.array(z.string()).max(20),
  flavor: z.string().min(1).max(20),
});

export const CalorieLineSchema = z.strictObject({
  name: z.string().min(1).max(40),
  nutritionQuery: z.string().min(2).max(120),
  nutritionFallbackQuery: z.string().min(1).max(120),
  grams: z.number().min(0).max(10_000),
  note: z.string().max(80),
  estimatedKcalPer100g: z.number().min(0).max(1_000).nullish(),
  kcalPer100g: z.number().min(0),
  kcal: NonNegativeIntegerSchema,
  estimated: z.boolean(),
  nutritionSource: z.string(),
  sourceId: z.number().int().nullable().optional(),
  sourceDescription: z.string(),
  sourceUrl: z.string().url().nullable().optional(),
});

export const RecipeStepSchema = z.strictObject({
  title: z.string().min(1).max(60),
  detail: z.string().min(1).max(500),
  minutes: z.number().int().min(0).max(240),
});

export const RecipeSchema = z.strictObject({
  id: IdSchema,
  name: z.string().min(1).max(60),
  description: z.string().min(1).max(180),
  ingredients: z.array(CalorieLineSchema).min(1).max(30),
  seasonings: z.array(CalorieLineSchema).max(20),
  steps: z.array(RecipeStepSchema).min(1).max(15),
  totalMinutes: z.number().int().positive().max(300),
  difficulty: z.enum(["简单", "适中"]),
  lowCalorieReason: z.string().min(1).max(240),
  tools: z.array(z.string()).max(10),
  tags: z.array(z.string()).max(8),
  totalKcal: NonNegativeIntegerSchema,
  perPersonKcal: NonNegativeIntegerSchema,
  calorieEstimated: z.boolean(),
});

export const ApiFailureSchema = z.strictObject({
  code: z.string().min(1),
  message: z.string().min(1),
  retryable: z.boolean(),
});

export const RecipeChannelSchema = z
  .strictObject({
    id: IdSchema,
    revision: NonNegativeIntegerSchema,
    ingredientBudget: z.array(IngredientInputSchema).min(1).max(40),
    current: RecipeSchema,
  })
  .superRefine((channel, context) => {
    const ingredientIds = new Set<string>();
    for (const [index, ingredient] of channel.ingredientBudget.entries()) {
      if (ingredientIds.has(ingredient.id)) {
        context.addIssue({
          code: "custom",
          message: "ingredientBudget ingredient id 必须唯一",
          path: ["ingredientBudget", index, "id"],
        });
      }
      ingredientIds.add(ingredient.id);
    }

  });

export const MealSchema = z.strictObject({
  id: IdSchema,
  label: z.string().min(1).max(30),
  channels: z.array(RecipeChannelSchema).min(1).max(8),
  totalKcal: NonNegativeIntegerSchema,
  perPersonKcal: NonNegativeIntegerSchema,
});

export const AgentTraceStepSchema = z.strictObject({
  id: IdSchema,
  skill: z.string().min(1),
  title: z.string().min(1),
  detail: z.string().min(1),
  status: z.enum(["completed", "repaired", "warning"]),
});

export const MealPlanSchema = z
  .strictObject({
    id: IdSchema,
    revision: NonNegativeIntegerSchema,
    source: z.literal("kimi"),
    title: z.string().min(1),
    summary: z.string().min(1),
    people: z.number().int().min(1).max(8),
    createdAt: z.string().datetime({ offset: true }),
    meals: z.array(MealSchema).min(1).max(4),
    totalKcal: NonNegativeIntegerSchema,
    perPersonKcal: NonNegativeIntegerSchema,
    tips: z.array(z.string()),
    unusedIngredients: z.array(z.string()),
    warnings: z.array(z.string()),
    disclaimer: z.string(),
    agentTrace: z.array(AgentTraceStepSchema),
    skillVersions: z.record(z.string(), z.string()),
  })
  .superRefine((plan, context) => {
    const channelIds = new Set<string>();
    for (const [mealIndex, meal] of plan.meals.entries()) {
      for (const [channelIndex, channel] of meal.channels.entries()) {
        if (channelIds.has(channel.id)) {
          context.addIssue({
            code: "custom",
            message: "channel id 必须在 plan 内唯一",
            path: ["meals", mealIndex, "channels", channelIndex, "id"],
          });
        }
        channelIds.add(channel.id);
      }
    }
  });

export const AsyncJobKindSchema = z.enum([
  "recognition",
  "plan",
  "channel_swap",
]);

export const AsyncJobStatusSchema = z.enum([
  "queued",
  "running",
  "completed",
  "failed",
]);

export function AsyncJobSchema<ResultSchema extends z.ZodTypeAny>(
  resultSchema: ResultSchema,
) {
  const nullableResultSchema = z.union([resultSchema, z.null()]) as z.ZodType<
    z.output<ResultSchema> | null
  >;
  return z
    .strictObject({
      id: IdSchema,
      kind: AsyncJobKindSchema,
      status: AsyncJobStatusSchema,
      phase: z.string(),
      message: z.string(),
      version: NonNegativeIntegerSchema,
      result: nullableResultSchema,
      error: ApiFailureSchema.nullable(),
    })
    .superRefine((job, context) => {
      if (job.status === "completed") {
        if (job.result === null || job.error !== null) {
          context.addIssue({
            code: "custom",
            message: "completed job 必须只有 result",
            path: ["status"],
          });
        }
        return;
      }

      if (job.status === "failed") {
        if (job.result !== null || job.error === null) {
          context.addIssue({
            code: "custom",
            message: "failed job 必须只有 error",
            path: ["status"],
          });
        }
        return;
      }

      if (job.result !== null || job.error !== null) {
        context.addIssue({
          code: "custom",
          message: "非终态 job 不得包含 result 或 error",
          path: ["status"],
        });
      }
    });
}

export const ChannelSwapRequestSchema = z.strictObject({
  planId: IdSchema,
  channelId: IdSchema,
  planRevision: NonNegativeIntegerSchema,
  channelRevision: NonNegativeIntegerSchema,
  idempotencyKey: IdSchema,
});

export const ChannelSwapResultSchema = z
  .strictObject({
    plan: MealPlanSchema,
    channelId: IdSchema,
  })
  .superRefine((result, context) => {
    const channel = result.plan.meals
      .flatMap((meal) => meal.channels)
      .find((candidate) => candidate.id === result.channelId);

    if (!channel) {
      context.addIssue({
        code: "custom",
        message: "swap result 必须引用 plan 内通道",
        path: ["channelId"],
      });
    }
  });

export const ActiveSwapSchema = z.strictObject({
  planId: IdSchema,
  channelId: IdSchema,
  jobId: IdSchema,
  jobVersion: NonNegativeIntegerSchema,
  startedAt: z.string().datetime({ offset: true }),
});

export const SessionV2Schema = z
  .strictObject({
    version: z.literal(2),
    savedAt: z.string().datetime({ offset: true }),
    plan: MealPlanSchema,
    ingredients: z.array(IngredientSchema).min(1).max(40),
    constraints: PlanConstraintsSchema,
    activeSwap: ActiveSwapSchema.nullable(),
  })
  .superRefine((session, context) => {
    if (session.activeSwap === null) return;
    const active = session.activeSwap;
    const channelExists = session.plan.meals
      .flatMap((meal) => meal.channels)
      .some((channel) => channel.id === active.channelId);
    const matches =
      active.planId === session.plan.id &&
      channelExists;
    if (!matches) {
      context.addIssue({
        code: "custom",
        message: "activeSwap 必须匹配当前 plan 内菜位",
        path: ["activeSwap"],
      });
    }
  });
