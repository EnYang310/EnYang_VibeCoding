import { describe, expect, test, vi } from "vitest";

import "./setup";
import {
  pushNavigationState,
  replaceNavigationState,
  resolveNavigationState,
} from "../lib/navigation";

const fullContext = {
  hasIngredients: true,
  hasPlan: true,
  recipeStepCounts: {
    "recipe-a": 3,
  },
};

describe("navigation history state", () => {
  test.each([
    null,
    { version: 1, screen: "loading" },
    { version: 1, screen: "recipe" },
    { version: 1, screen: "cook", recipeId: "recipe-a" },
    { version: 1, screen: "home", extra: true },
  ])("rejects dirty state and falls back to the nearest legal result", (raw) => {
    expect(resolveNavigationState(raw, fullContext)).toEqual({
      version: 1,
      screen: "result",
    });
  });

  test("degrades pages whose data dependencies are missing", () => {
    expect(
      resolveNavigationState(
        { version: 1, screen: "result" },
        {
          hasIngredients: true,
          hasPlan: false,
          recipeStepCounts: {},
        },
      ),
    ).toEqual({ version: 1, screen: "setup" });
    expect(
      resolveNavigationState(
        { version: 1, screen: "setup" },
        {
          hasIngredients: false,
          hasPlan: false,
          recipeStepCounts: {},
        },
      ),
    ).toEqual({ version: 1, screen: "home" });
    expect(
      resolveNavigationState(
        { version: 1, screen: "recipe", recipeId: "missing" },
        fullContext,
      ),
    ).toEqual({ version: 1, screen: "result" });
  });

  test("restores recipe and clamps a dirty cook step to the recipe", () => {
    expect(
      resolveNavigationState(
        { version: 1, screen: "recipe", recipeId: "recipe-a" },
        fullContext,
      ),
    ).toEqual({
      version: 1,
      screen: "recipe",
      recipeId: "recipe-a",
    });
    expect(
      resolveNavigationState(
        {
          version: 1,
          screen: "cook",
          recipeId: "recipe-a",
          cookStep: 99,
        },
        fullContext,
      ),
    ).toEqual({
      version: 1,
      screen: "cook",
      recipeId: "recipe-a",
      cookStep: 2,
    });
  });

  test("writes history defensively without throwing", () => {
    const target = {
      pushState: vi.fn(() => {
        throw new DOMException("blocked", "SecurityError");
      }),
      replaceState: vi.fn(),
    };

    expect(
      pushNavigationState(
        { version: 1, screen: "home" },
        target,
      ),
    ).toBe(false);
    expect(
      replaceNavigationState(
        { version: 1, screen: "home" },
        target,
      ),
    ).toBe(true);
  });
});
