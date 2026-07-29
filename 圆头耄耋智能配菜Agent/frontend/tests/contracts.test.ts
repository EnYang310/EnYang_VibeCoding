import { describe, expect, test } from "vitest";

import "./setup";
import {
  AsyncJobSchema,
  ChannelSwapResultSchema,
  MealPlanSchema,
  RecipeChannelSchema,
  SessionV2Schema,
} from "../lib/contracts";
import {
  channelA,
  cloneFixture,
  queuedSwapJob,
  swappingSession,
  validMealPlan,
  validSessionV2,
} from "./fixtures";

describe("on-demand recipe channel contract", () => {
  test("accepts only fixed budget and current recipe", () => {
    expect(RecipeChannelSchema.parse(channelA)).toEqual(channelA);
    expect(
      RecipeChannelSchema.safeParse({ ...channelA, backup: channelA.current })
        .success,
    ).toBe(false);
  });

  test("requires root calorie totals and rejects duplicate channel ids", () => {
    expect(MealPlanSchema.parse(validMealPlan)).toEqual(validMealPlan);
    const noTotal = cloneFixture(validMealPlan) as unknown as Record<
      string,
      unknown
    >;
    delete noTotal.totalKcal;
    expect(MealPlanSchema.safeParse(noTotal).success).toBe(false);

    const duplicate = cloneFixture(validMealPlan);
    duplicate.meals[0].channels[1].id = duplicate.meals[0].channels[0].id;
    expect(MealPlanSchema.safeParse(duplicate).success).toBe(false);
  });

  test("accepts channel_swap jobs and validates the result channel", () => {
    const schema = AsyncJobSchema(ChannelSwapResultSchema);
    expect(schema.safeParse(queuedSwapJob).success).toBe(true);
    expect(
      schema.safeParse({ ...queuedSwapJob, kind: "channel_refill" }).success,
    ).toBe(false);

    expect(
      ChannelSwapResultSchema.safeParse({
        plan: validMealPlan,
        channelId: "channel-a",
      }).success,
    ).toBe(true);
    expect(
      ChannelSwapResultSchema.safeParse({
        plan: validMealPlan,
        channelId: "missing",
      }).success,
    ).toBe(false);
  });

  test("session v2 can persist one active swap without mutating the plan", () => {
    expect(SessionV2Schema.parse(validSessionV2)).toEqual(validSessionV2);
    const swapping = swappingSession();
    expect(SessionV2Schema.parse(swapping)).toEqual(swapping);
    expect(swapping.plan).toEqual(validMealPlan);
  });
});
