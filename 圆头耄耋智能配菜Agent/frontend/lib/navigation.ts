import { z } from "zod";

const BaseState = {
  version: z.literal(1),
};

const NavigationStateSchema = z.discriminatedUnion("screen", [
  z.strictObject({
    ...BaseState,
    screen: z.enum(["home", "ingredients", "setup", "result"]),
  }),
  z.strictObject({
    ...BaseState,
    screen: z.literal("recipe"),
    recipeId: z.string().min(1),
  }),
  z.strictObject({
    ...BaseState,
    screen: z.literal("cook"),
    recipeId: z.string().min(1),
    cookStep: z.number().int().min(0),
  }),
]);

export type NavigationState = z.infer<typeof NavigationStateSchema>;

export type NavigationContext = {
  hasIngredients: boolean;
  hasPlan: boolean;
  recipeStepCounts: Readonly<Record<string, number>>;
};

type HistoryWriter = {
  pushState(data: unknown, unused: string, url?: string | URL | null): void;
  replaceState(data: unknown, unused: string, url?: string | URL | null): void;
};

function fallbackState(context: NavigationContext): NavigationState {
  if (context.hasPlan) return { version: 1, screen: "result" };
  if (context.hasIngredients) return { version: 1, screen: "ingredients" };
  return { version: 1, screen: "home" };
}

export function resolveNavigationState(
  raw: unknown,
  context: NavigationContext,
): NavigationState {
  const parsed = NavigationStateSchema.safeParse(raw);
  if (!parsed.success) return fallbackState(context);
  const state = parsed.data;

  if (state.screen === "home") return state;
  if (state.screen === "ingredients") {
    return context.hasIngredients ? state : { version: 1, screen: "home" };
  }
  if (state.screen === "setup") {
    return context.hasIngredients ? state : { version: 1, screen: "home" };
  }
  if (state.screen === "result") {
    if (context.hasPlan) return state;
    return context.hasIngredients
      ? { version: 1, screen: "setup" }
      : { version: 1, screen: "home" };
  }

  if (!context.hasPlan) {
    return context.hasIngredients
      ? { version: 1, screen: "setup" }
      : { version: 1, screen: "home" };
  }
  if (state.screen === "recipe") {
    const stepCount = context.recipeStepCounts[state.recipeId] ?? 0;
    return stepCount > 0 ? state : { version: 1, screen: "result" };
  }
  if (state.screen === "cook") {
    const stepCount = context.recipeStepCounts[state.recipeId] ?? 0;
    if (stepCount <= 0) return { version: 1, screen: "result" };
    return {
      ...state,
      cookStep: Math.min(state.cookStep, stepCount - 1),
    };
  }
  return fallbackState(context);
}

function defaultHistory(): HistoryWriter | null {
  try {
    return typeof history === "undefined" ? null : history;
  } catch {
    return null;
  }
}

export function pushNavigationState(
  state: NavigationState,
  target: HistoryWriter | null = defaultHistory(),
): boolean {
  if (target === null) return false;
  try {
    target.pushState(state, "");
    return true;
  } catch {
    return false;
  }
}

export function replaceNavigationState(
  state: NavigationState,
  target: HistoryWriter | null = defaultHistory(),
): boolean {
  if (target === null) return false;
  try {
    target.replaceState(state, "");
    return true;
  } catch {
    return false;
  }
}
