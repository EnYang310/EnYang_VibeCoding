"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  pushNavigationState,
  replaceNavigationState,
  resolveNavigationState,
  type NavigationState,
} from "../lib/navigation";
import {
  ApiError,
  fetchMealPlan,
  generateMealPlan,
  recognizeIngredients,
  startChannelSwap,
  waitForChannelSwap,
} from "../lib/api";
import { compressImage } from "../lib/image";
import { OperationEpoch } from "../lib/operation";
import { loadSession, saveSession } from "../lib/session";
import type {
  ActiveSwap,
  AsyncJob,
  ChannelSwapResult,
  Ingredient,
  MealPlan,
  PlanConstraints,
  Recipe,
  RecipeChannel,
  SessionV2,
} from "../lib/types";

type Screen =
  | "home"
  | "loading"
  | "ingredients"
  | "setup"
  | "result"
  | "recipe"
  | "cook"
  | "error";

const TOOL_OPTIONS = ["炒锅", "汤锅", "电饭煲", "蒸锅", "空气炸锅", "微波炉"];
const FLAVOR_OPTIONS = ["清淡", "家常", "酸辣", "微辣"];
const REPLACEMENT_BUSY_MESSAGE = "别急，一个一个来！";
const MAX_INGREDIENTS = 40;
const MAX_INGREDIENT_NAME = 30;
const MAX_INGREDIENT_GRAMS = 10_000;
const MAX_AVOID_ITEMS = 20;

function isMobileCaptureDevice() {
  if (typeof navigator === "undefined") return false;
  const userAgent = navigator.userAgent;
  return (
    /Android|iPhone|iPad|iPod/i.test(userAgent) ||
    (/Macintosh/i.test(userAgent) && navigator.maxTouchPoints > 1)
  );
}

function Mascot({
  size = "small",
  angry = false,
}: {
  size?: "small" | "medium" | "large";
  angry?: boolean;
}) {
  return (
    <div className={`mascot mascot-${size} ${angry ? "mascot-angry" : ""}`}>
      <img
        src={angry ? "/maodie-angry.jpg" : "/maodie-calm.jpg"}
        alt={angry ? "哈气耄耋" : "圆头耄耋"}
      />
    </div>
  );
}

function Topbar({
  onHome,
  showModel,
}: {
  onHome: () => void;
  showModel: boolean;
}) {
  return (
    <header className="topbar">
      <button className="brand-button" onClick={onHome}>
        <span className="brand-dot" />
        耄耋掌勺
      </button>
      {showModel && (
        <span className="model-chip">
          <span>●</span>
          Kimi K2.6
        </span>
      )}
    </header>
  );
}

function idempotencyKey(): string {
  try {
    if (typeof crypto.randomUUID === "function") {
      return `swap-${crypto.randomUUID()}`;
    }
  } catch {
    // Older Safari/private contexts can expose crypto without randomUUID.
  }
  return `swap-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function channelFromPlan(
  plan: MealPlan,
  channelId: string,
): RecipeChannel | null {
  return (
    plan.meals
      .flatMap((meal) => meal.channels)
      .find((channel) => channel.id === channelId) ?? null
  );
}

function clampIngredientGrams(value: number): number {
  if (!Number.isFinite(value)) return 1;
  return Math.min(MAX_INGREDIENT_GRAMS, Math.max(1, value));
}

function parseAvoidItems(value: string): string[] {
  return value
    .split(/[，,、\s]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, MAX_AVOID_ITEMS);
}

function isUsableRecipe(recipe: Recipe | null): recipe is Recipe {
  return (
    recipe !== null &&
    recipe.steps.length > 0 &&
    recipe.steps.every(
      (step) =>
        step.title.trim().length > 0 &&
        step.detail.trim().length > 0 &&
        Number.isFinite(step.minutes) &&
        step.minutes >= 0,
    )
  );
}

export default function MaodieApp() {
  const [screen, setScreen] = useState<Screen>("home");
  const [imagePreview, setImagePreview] = useState("");
  const [ingredients, setIngredients] = useState<Ingredient[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [loadingText, setLoadingText] = useState("耄耋正在看食材…");
  const [errorMessage, setErrorMessage] = useState("");
  const [errorRetry, setErrorRetry] = useState<(() => void) | null>(null);
  const [plan, setPlan] = useState<MealPlan | null>(null);
  const [selectedRecipeId, setSelectedRecipeId] = useState("");
  const [cookStep, setCookStep] = useState(0);
  const [replacingId, setReplacingId] = useState("");
  const [activeSwap, setActiveSwap] = useState<ActiveSwap | null>(null);
  const [swapDialogOpen, setSwapDialogOpen] = useState(false);
  const [replacementError, setReplacementError] = useState<{
    channelId: string;
    message: string;
  } | null>(null);
  const [newIngredient, setNewIngredient] = useState("");
  const [constraints, setConstraints] = useState<PlanConstraints>({
    people: 2,
    mealCount: 2,
    tools: ["炒锅", "电饭煲"],
    avoid: [],
    flavor: "清淡",
  });
  const [avoidInput, setAvoidInput] = useState("");

  const cameraRef = useRef<HTMLInputElement>(null);
  const albumRef = useRef<HTMLInputElement>(null);
  const ingredientsRef = useRef<Ingredient[]>([]);
  const planRef = useRef<MealPlan | null>(null);
  const swapBusyRef = useRef(false);
  const planGenerationBusyRef = useRef(false);
  const activeSwapRef = useRef<ActiveSwap | null>(null);
  const operationEpochRef = useRef(new OperationEpoch());
  const foregroundEpochRef = useRef(new OperationEpoch());

  useEffect(() => {
    ingredientsRef.current = ingredients;
  }, [ingredients]);

  useEffect(() => {
    const restored = loadSession();
    if (restored) {
      planRef.current = restored.plan;
      ingredientsRef.current = restored.ingredients;
      setPlan(restored.plan);
      setIngredients(restored.ingredients);
      setConstraints(restored.constraints);
      activeSwapRef.current = restored.activeSwap;
      setActiveSwap(restored.activeSwap);
      swapBusyRef.current = restored.activeSwap !== null;

      const handle = operationEpochRef.current.begin();
      void resumeSession(restored, handle);
    }

    let initialState: unknown = null;
    try {
      initialState = history.state;
    } catch {
      // Sandboxed history behaves like a fresh home entry.
    }
    const resolvedInitial =
      initialState === null
        ? ({ version: 1, screen: "home" } as const)
        : resolveNavigationState(initialState, navigationContext());
    applyNavigationState(resolvedInitial);
    replaceNavigationState(resolvedInitial);

    const handlePopState = (event: PopStateEvent) => {
      const resolved = resolveNavigationState(
        event.state,
        navigationContext(),
      );
      foregroundEpochRef.current.cancel();
      planGenerationBusyRef.current = false;
      applyNavigationState(resolved);
      replaceNavigationState(resolved);
    };
    window.addEventListener("popstate", handlePopState);

    return () => {
      window.removeEventListener("popstate", handlePopState);
      operationEpochRef.current.cancel();
      foregroundEpochRef.current.cancel();
    };
  }, []);

  const selectedRecipe = useMemo(() => {
    if (!plan) return null;
    return (
      plan.meals
        .flatMap((meal) => meal.channels.map((channel) => channel.current))
        .find((recipe) => recipe.id === selectedRecipeId) ?? null
    );
  }, [plan, selectedRecipeId]);
  const selectedRecipeIsUsable = isUsableRecipe(selectedRecipe);
  const ingredientsAreValid =
    ingredients.length > 0 &&
    ingredients.length <= MAX_INGREDIENTS &&
    ingredients.every(
      (ingredient) =>
        ingredient.name.trim().length > 0 &&
        ingredient.name.length <= MAX_INGREDIENT_NAME &&
        ingredient.estimatedGrams >= 1 &&
        ingredient.estimatedGrams <= MAX_INGREDIENT_GRAMS,
    );

  useEffect(() => {
    if (
      (screen === "recipe" || screen === "cook") &&
      !selectedRecipeIsUsable
    ) {
      navigateTo({ version: 1, screen: "result" }, true);
      return;
    }
    if (
      screen === "cook" &&
      selectedRecipe &&
      cookStep >= selectedRecipe.steps.length
    ) {
      const nextStep = Math.max(0, selectedRecipe.steps.length - 1);
      setCookStep(nextStep);
      replaceNavigationState({
        version: 1,
        screen: "cook",
        recipeId: selectedRecipe.id,
        cookStep: nextStep,
      });
    }
  }, [cookStep, screen, selectedRecipe, selectedRecipeIsUsable]);

  function persist(
    nextPlan: MealPlan,
    nextActiveSwap: ActiveSwap | null,
    nextIngredients = ingredients,
    nextConstraints = constraints,
  ) {
    planRef.current = nextPlan;
    setPlan(nextPlan);
    activeSwapRef.current = nextActiveSwap;
    setActiveSwap(nextActiveSwap);
    saveSession({
      version: 2,
      savedAt: new Date().toISOString(),
      plan: nextPlan,
      ingredients: nextIngredients,
      constraints: nextConstraints,
      activeSwap: nextActiveSwap,
    });
  }

  function navigationContext() {
    const recipeStepCounts: Record<string, number> = {};
    for (const recipe of (planRef.current?.meals ?? []).flatMap((meal) =>
      meal.channels.map((channel) => channel.current),
    )) {
      recipeStepCounts[recipe.id] = recipe.steps.length;
    }
    return {
      hasIngredients: ingredientsRef.current.length > 0,
      hasPlan: planRef.current !== null,
      recipeStepCounts,
    };
  }

  function applyNavigationState(state: NavigationState) {
    if (state.screen === "recipe") {
      setSelectedRecipeId(state.recipeId);
      setCookStep(0);
    } else if (state.screen === "cook") {
      setSelectedRecipeId(state.recipeId);
      setCookStep(state.cookStep);
    } else {
      setSelectedRecipeId("");
      setCookStep(0);
    }
    setScreen(state.screen);
  }

  function navigateTo(state: NavigationState, replace = false) {
    applyNavigationState(state);
    if (replace) {
      replaceNavigationState(state);
    } else {
      pushNavigationState(state);
    }
  }

  async function resumeSession(
    restored: SessionV2,
    handle: ReturnType<OperationEpoch["begin"]>,
  ) {
    if (!restored) return;
    let currentPlan = restored.plan;
    try {
      const remotePlan = await fetchMealPlan(restored.plan.id, handle.signal);
      if (!operationEpochRef.current.canCommit(handle)) return;
      currentPlan = remotePlan;
      persist(
        remotePlan,
        restored.activeSwap,
        restored.ingredients,
        restored.constraints,
      );
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
    }

    const savedSwap = restored.activeSwap;
    if (
      savedSwap === null ||
      !operationEpochRef.current.canCommit(handle)
    ) {
      return;
    }
    const resumableJob: AsyncJob<ChannelSwapResult> = {
      id: savedSwap.jobId,
      kind: "channel_swap",
      status: "running",
      phase: "resuming",
      message: "继续等待这次换菜…",
      version: savedSwap.jobVersion,
      result: null,
      error: null,
    };
    await finishSwap(
      resumableJob,
      savedSwap.channelId,
      currentPlan,
      handle,
      restored.ingredients,
      restored.constraints,
    );
  }

  function openPicker(kind: "camera" | "album") {
    const picker =
      kind === "camera" && isMobileCaptureDevice()
        ? cameraRef.current
        : albumRef.current;
    picker?.click();
  }

  function fail(error: unknown, retry?: () => void) {
    const message =
      error instanceof ApiError || error instanceof Error
        ? error.message
        : "耄耋这次没接住，再试一下。";
    setErrorMessage(message);
    setErrorRetry(retry ? () => retry : null);
    setScreen("error");
  }

  async function handleFile(file?: File) {
    if (!file) return;
    const action = () => handleFile(file);
    const handle = foregroundEpochRef.current.begin();
    planGenerationBusyRef.current = false;
    try {
      setLoadingText("耄耋正在看你拍了啥…");
      setScreen("loading");
      const dataUrl = await compressImage(file);
      if (!foregroundEpochRef.current.canCommit(handle)) return;
      setImagePreview(dataUrl);
      const result = await recognizeIngredients(
        dataUrl,
        (message) => {
          if (foregroundEpochRef.current.canCommit(handle)) {
            setLoadingText(message);
          }
        },
        handle.signal,
      );
      if (!foregroundEpochRef.current.canCommit(handle)) return;
      setIngredients(result.ingredients.slice(0, MAX_INGREDIENTS));
      setWarnings(result.warnings);
      navigateTo({ version: 1, screen: "ingredients" });
    } catch (error) {
      if (
        (error instanceof DOMException && error.name === "AbortError") ||
        !foregroundEpochRef.current.canCommit(handle)
      ) {
        return;
      }
      fail(error, action);
    } finally {
      if (cameraRef.current) cameraRef.current.value = "";
      if (albumRef.current) albumRef.current.value = "";
    }
  }

  function updateIngredient(
    id: string,
    patch: Partial<Pick<Ingredient, "name" | "estimatedGrams">>,
  ) {
    setIngredients((current) =>
      current.map((item) => {
        if (item.id !== id) return item;
        return {
          ...item,
          ...patch,
          ...(patch.name === undefined
            ? {}
            : { name: patch.name.slice(0, MAX_INGREDIENT_NAME) }),
          ...(patch.estimatedGrams === undefined
            ? {}
            : {
                estimatedGrams: clampIngredientGrams(
                  patch.estimatedGrams,
                ),
              }),
        };
      }),
    );
  }

  function addIngredient() {
    if (ingredients.length >= MAX_INGREDIENTS) return;
    const name = newIngredient.trim().slice(0, MAX_INGREDIENT_NAME);
    if (!name) return;
    setIngredients((current) => [
      ...current,
      {
        id: `manual-${Date.now()}`,
        name,
        amount: 1,
        unit: "份",
        estimatedGrams: 200,
      },
    ]);
    setNewIngredient("");
  }

  async function createPlan(nextConstraints = constraints) {
    if (planGenerationBusyRef.current) return;
    planGenerationBusyRef.current = true;
    const action = () => createPlan(nextConstraints);
    const handle = foregroundEpochRef.current.begin();
    try {
      setLoadingText("耄耋正在分配食材、设计低卡菜…");
      setScreen("loading");
      const result = await generateMealPlan(
        ingredients,
        nextConstraints,
        (message) => {
          if (foregroundEpochRef.current.canCommit(handle)) {
            setLoadingText(message);
          }
        },
        handle.signal,
      );
      if (!foregroundEpochRef.current.canCommit(handle)) return;
      planRef.current = result;
      setPlan(result);
      persist(result, null, ingredients, nextConstraints);
      navigateTo({ version: 1, screen: "result" });
    } catch (error) {
      if (
        (error instanceof DOMException && error.name === "AbortError") ||
        !foregroundEpochRef.current.canCommit(handle)
      ) {
        return;
      }
      fail(error, action);
    } finally {
      if (foregroundEpochRef.current.canCommit(handle)) {
        planGenerationBusyRef.current = false;
      }
    }
  }

  function showReplacementBusyNotice() {
    setSwapDialogOpen(true);
  }

  async function finishSwap(
    swapJob: AsyncJob<ChannelSwapResult>,
    channelId: string,
    originalPlan: MealPlan,
    handle: ReturnType<OperationEpoch["begin"]>,
    sessionIngredients = ingredients,
    sessionConstraints = constraints,
  ) {
    try {
      const result = await waitForChannelSwap(
        swapJob,
        handle.signal,
        setLoadingText,
      );
      if (!operationEpochRef.current.canCommit(handle)) return;
      persist(
        result.plan,
        null,
        sessionIngredients,
        sessionConstraints,
      );
      setReplacementError(null);
    } catch (error) {
      if (
        error instanceof DOMException &&
        error.name === "AbortError"
      ) {
        return;
      }
      if (!operationEpochRef.current.canCommit(handle)) return;
      persist(
        planRef.current ?? originalPlan,
        null,
        sessionIngredients,
        sessionConstraints,
      );
      setReplacementError({
        channelId,
        message:
          error instanceof Error
            ? error.message
            : "这道菜没换成，请再试一次。",
      });
    } finally {
      if (operationEpochRef.current.canCommit(handle)) {
        swapBusyRef.current = false;
        activeSwapRef.current = null;
        setActiveSwap(null);
        setReplacingId("");
      }
    }
  }

  async function runChannelSwap(channelId: string) {
    const currentPlan = planRef.current ?? plan;
    if (!currentPlan) return;
    const currentChannel = channelFromPlan(currentPlan, channelId);
    if (!currentChannel) return;
    if (swapBusyRef.current) {
      showReplacementBusyNotice();
      return;
    }

    swapBusyRef.current = true;
    const handle = operationEpochRef.current.begin();
    try {
      setReplacingId(channelId);
      setReplacementError(null);
      const request = {
        planId: currentPlan.id,
        channelId,
        planRevision: currentPlan.revision,
        channelRevision: currentChannel.revision,
        idempotencyKey: idempotencyKey(),
      };
      const job = await startChannelSwap(request, handle.signal);
      if (!operationEpochRef.current.canCommit(handle)) return;

      const nextActive: ActiveSwap = {
        planId: currentPlan.id,
        channelId,
        jobId: job.id,
        jobVersion: job.version,
        startedAt: new Date().toISOString(),
      };
      persist(currentPlan, nextActive);
      setReplacingId("");
      await finishSwap(
        job,
        channelId,
        currentPlan,
        handle,
      );
    } catch (error) {
      if (
        error instanceof DOMException &&
        error.name === "AbortError"
      ) {
        return;
      }
      if (!operationEpochRef.current.canCommit(handle)) return;
      if (error instanceof ApiError && error.code === "REPLACEMENT_BUSY") {
        showReplacementBusyNotice();
      } else {
        setReplacementError({
          channelId,
          message:
            error instanceof ApiError || error instanceof Error
              ? error.message
              : "这道没换成，再试一次。",
        });
      }
      swapBusyRef.current = false;
      activeSwapRef.current = null;
      setActiveSwap(null);
      setReplacingId("");
    }
  }

  function replaceOne(channelId: string) {
    void runChannelSwap(channelId);
  }

  function openRecipe(recipe: Recipe) {
    setSelectedRecipeId(recipe.id);
    setCookStep(0);
    navigateTo({
      version: 1,
      screen: "recipe",
      recipeId: recipe.id,
    });
  }

  function goHome() {
    foregroundEpochRef.current.cancel();
    planGenerationBusyRef.current = false;
    navigateTo({ version: 1, screen: "home" });
  }

  return (
    <main className="app-shell">
      <input
        ref={cameraRef}
        className="file-picker-input"
        tabIndex={-1}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        capture="environment"
        onChange={(event) => handleFile(event.target.files?.[0])}
      />
      <input
        ref={albumRef}
        className="file-picker-input"
        tabIndex={-1}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        onChange={(event) => handleFile(event.target.files?.[0])}
      />

      {screen !== "error" && (
        <Topbar onHome={goHome} showModel={screen === "home"} />
      )}

      {swapDialogOpen && (
        <div className="swap-busy-overlay">
          <section
            className="swap-busy-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="swap-busy-title"
          >
            <button
              className="swap-busy-close"
              aria-label="关闭提示"
              onClick={() => setSwapDialogOpen(false)}
            >
              ×
            </button>
            <Mascot size="medium" angry />
            <h2 id="swap-busy-title">耄耋哈气了</h2>
            <p>{REPLACEMENT_BUSY_MESSAGE}</p>
            <small>当前菜还在更换中，完成前不会接收或排队新请求。</small>
          </section>
        </div>
      )}

      {screen === "home" && (
        <section className="screen home-screen">
          <div className="hero-copy">
            <span className="eyebrow">AI 低卡造菜助手</span>
            <h1>
              冰箱有啥，
              <br />
              耄耋就做啥。
            </h1>
            <p>
              拍下现有食材，耄耋识别后设计适合人数的低热量菜品，热量由 USDA
              权威数据重算。
            </p>
          </div>

          <div className="mascot-stage">
            <div className="sun-ring" />
            <Mascot size="large" />
            <div className="speech-bubble">把食材交出来。今天我掌勺。</div>
            <span className="steam-badge">♨</span>
          </div>

          <div className="home-actions">
            <button className="primary-button camera-button" onClick={() => openPicker("camera")}>
              <span>📷</span> 拍食材，让耄耋掌勺
            </button>
            <button className="secondary-button" onClick={() => openPicker("album")}>
              从相册选择
            </button>
          </div>

          {plan && (
            <button
              className="last-plan-card"
              onClick={() =>
                navigateTo({ version: 1, screen: "result" })
              }
            >
              <span>
                <b>上次菜单</b>
                <small>{plan.title}</small>
              </span>
              <span>继续看 →</span>
            </button>
          )}

          <div className="trust-row">
            <span>✓ 耄耋真识别</span>
            <span>✓ USDA 热量来源</span>
            <span>✓ 不用登录</span>
          </div>
        </section>
      )}

      {screen === "loading" && (
        <section className="screen center-screen">
          <div className="thinking-orbit">
            <Mascot size="large" />
            <span className="orbit-dot dot-one" />
            <span className="orbit-dot dot-two" />
            <span className="orbit-dot dot-three" />
          </div>
          <span className="eyebrow">耄耋正在工作</span>
          <h2>{loadingText}</h2>
          <p className="muted">识别通常较快，完整菜单会多做几步核对，请稍等。</p>
          <div className="loading-bar">
            <span />
          </div>
          {loadingText.includes("设计") && (
            <div className="live-agent-steps">
              <span className="active">1</span>
              <div>
                <b>菜品规划 Skill</b>
                <small>耄耋正在按人数和库存设计真正的菜</small>
              </div>
              <span>2</span>
              <div>
                <b>USDA 营养 Tool</b>
                <small>批量检索权威食物成分数据</small>
              </div>
              <span>3</span>
              <div>
                <b>合格检查 Skill</b>
                <small>只查基础硬错误；有错就修复并复审，合格才交付</small>
              </div>
            </div>
          )}
        </section>
      )}

      {screen === "ingredients" && (
        <section className="screen">
          <div className="page-intro">
            <div>
              <span className="eyebrow">第一步 · 对答案</span>
              <h2>耄耋认出了这些</h2>
            </div>
            <Mascot size="medium" />
          </div>
          {imagePreview && (
            <div className="photo-preview">
              <img src={imagePreview} alt="拍摄的食材" />
              <span>耄耋图片识别</span>
            </div>
          )}
          {warnings.map((warning) => (
            <p className="warning-note" key={warning}>
              △ {warning}
            </p>
          ))}
          <div className="ingredient-list">
            {ingredients.map((item) => (
              <div className="ingredient-row" key={item.id}>
                <div className="ingredient-main">
                  <input
                    aria-label="食材名称"
                    maxLength={MAX_INGREDIENT_NAME}
                    value={item.name}
                    onChange={(event) =>
                      updateIngredient(item.id, { name: event.target.value })
                    }
                  />
                  <small>
                    {item.amount} {item.unit}
                    {item.confidence !== undefined &&
                      ` · ${Math.round(item.confidence * 100)}% 把握`}
                  </small>
                </div>
                <label className="gram-input">
                  <input
                    type="number"
                    min={1}
                    max={MAX_INGREDIENT_GRAMS}
                    value={Math.round(item.estimatedGrams)}
                    onChange={(event) =>
                      updateIngredient(item.id, {
                        estimatedGrams: Number(event.target.value),
                      })
                    }
                  />
                  g
                </label>
                <button
                  className="icon-button"
                  aria-label={`删除${item.name}`}
                  onClick={() =>
                    setIngredients((current) =>
                      current.filter((candidate) => candidate.id !== item.id),
                    )
                  }
                >
                  ×
                </button>
              </div>
            ))}
          </div>
          <div className="add-row">
            <input
              value={newIngredient}
              maxLength={MAX_INGREDIENT_NAME}
              onChange={(event) =>
                setNewIngredient(
                  event.target.value.slice(0, MAX_INGREDIENT_NAME),
                )
              }
              onKeyDown={(event) => event.key === "Enter" && addIngredient()}
              placeholder="漏了什么？手动补一个"
            />
            <button
              disabled={ingredients.length >= MAX_INGREDIENTS}
              onClick={addIngredient}
            >
              添加
            </button>
          </div>
          {ingredients.length >= MAX_INGREDIENTS && (
            <p className="warning-note">最多添加 40 种食材</p>
          )}
          <div className="mascot-tip">
            <Mascot size="small" />
            <p>重量不用特别准，按一盒、一个的大概分量改就行。</p>
          </div>
          <button
            className="primary-button sticky-action"
            disabled={!ingredientsAreValid}
            onClick={() =>
              navigateTo({ version: 1, screen: "setup" })
            }
          >
            食材没毛病，继续
          </button>
        </section>
      )}

      {screen === "setup" && (
        <section className="screen">
          <div className="page-intro">
            <div>
              <span className="eyebrow">第二步 · 定规矩</span>
              <h2>这顿饭怎么做？</h2>
            </div>
            <Mascot size="medium" />
          </div>

          <div className="form-card">
            <div className="form-heading">
              <div>
                <b>几个人吃</b>
                <small>菜品数量会跟着人数变化</small>
              </div>
              <div className="stepper">
                <button
                  onClick={() =>
                    setConstraints((value) => ({
                      ...value,
                      people: Math.max(1, value.people - 1),
                    }))
                  }
                >
                  −
                </button>
                <strong>{constraints.people}</strong>
                <button
                  onClick={() =>
                    setConstraints((value) => ({
                      ...value,
                      people: Math.min(8, value.people + 1),
                    }))
                  }
                >
                  +
                </button>
              </div>
            </div>
          </div>

          <div className="form-card">
            <div className="form-heading">
              <div>
                <b>安排几餐</b>
                <small>1–4 餐，适合当天或周末</small>
              </div>
              <div className="stepper">
                <button
                  onClick={() =>
                    setConstraints((value) => ({
                      ...value,
                      mealCount: Math.max(1, value.mealCount - 1),
                    }))
                  }
                >
                  −
                </button>
                <strong>{constraints.mealCount}</strong>
                <button
                  onClick={() =>
                    setConstraints((value) => ({
                      ...value,
                      mealCount: Math.min(4, value.mealCount + 1),
                    }))
                  }
                >
                  +
                </button>
              </div>
            </div>
          </div>

          <div className="form-card">
            <b>能用的厨具</b>
            <div className="chip-grid">
              {TOOL_OPTIONS.map((tool) => {
                const active = constraints.tools.includes(tool);
                return (
                  <button
                    key={tool}
                    className={active ? "chip active" : "chip"}
                    onClick={() =>
                      setConstraints((value) => ({
                        ...value,
                        tools: active
                          ? value.tools.filter((item) => item !== tool)
                          : [...value.tools, tool],
                      }))
                    }
                  >
                    {active ? "✓ " : ""}
                    {tool}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="form-card">
            <b>口味</b>
            <div className="chip-grid">
              {FLAVOR_OPTIONS.map((flavor) => (
                <button
                  key={flavor}
                  className={constraints.flavor === flavor ? "chip active" : "chip"}
                  onClick={() =>
                    setConstraints((value) => ({ ...value, flavor }))
                  }
                >
                  {flavor}
                </button>
              ))}
            </div>
          </div>

          <div className="form-card">
            <label className="field-label" htmlFor="avoid">
              忌口或不想吃
            </label>
            <input
              id="avoid"
              className="plain-input"
              value={avoidInput}
              onChange={(event) => {
                const raw = event.target.value;
                const items = raw
                  .split(/[，,、\s]+/)
                  .map((item) => item.trim())
                  .filter(Boolean);
                setAvoidInput(
                  items.length > MAX_AVOID_ITEMS
                    ? items.slice(0, MAX_AVOID_ITEMS).join("、")
                    : raw,
                );
              }}
              placeholder="例如：花生、香菜；没有可不填"
            />
          </div>

          <div className="mascot-tip">
            <Mascot size="small" />
            <p>我会自己决定做几道菜，不硬凑数，也不让你吃草。</p>
          </div>
          <button
            className="primary-button sticky-action"
            onClick={() => {
              const nextConstraints = {
                ...constraints,
                avoid: parseAvoidItems(avoidInput),
              };
              setConstraints(nextConstraints);
              void createPlan(nextConstraints);
            }}
          >
            让耄耋开菜单
          </button>
        </section>
      )}

      {screen === "result" && plan && (
        <section className="screen result-screen">
          <div className="result-hero">
            <div>
              <span className="eyebrow">耄耋的低卡方案</span>
              <h2>{plan.title}</h2>
              <p>{plan.summary}</p>
            </div>
            <Mascot size="medium" />
          </div>
          <div className="plan-facts">
            <span>{plan.people} 人</span>
            <span>{plan.meals.length} 餐</span>
            <span>
              {plan.meals.reduce(
                (sum, meal) => sum + meal.channels.length,
                0,
              )}{" "}
              道菜
            </span>
          </div>

          {activeSwap && (
            <p className="swap-status" role="status">
              耄耋正在现做新菜，当前菜会保留到成功为止…
            </p>
          )}

          {plan.meals.map((meal) => (
            <div className="meal-block" key={meal.id}>
              <div className="meal-heading">
                <div>
                  <span className="eyebrow">{meal.label}</span>
                  <h3>人均约 {meal.perPersonKcal} kcal</h3>
                </div>
                <small>整餐约 {meal.totalKcal} kcal</small>
              </div>
              {meal.channels.map((channel, index) => {
                const recipe = channel.current;
                return (
                <article className="recipe-card" key={channel.id}>
                  <button className="recipe-open" onClick={() => openRecipe(recipe)}>
                    <span className="recipe-number">{index + 1}</span>
                    <span className="recipe-copy">
                      <b>{recipe.name}</b>
                      <small>{recipe.description}</small>
                      <span className="recipe-meta">
                        {recipe.totalMinutes} 分钟 · {recipe.difficulty} · 人均{" "}
                        {recipe.perPersonKcal} kcal
                      </span>
                    </span>
                    <span>›</span>
                  </button>
                  <div className="recipe-card-footer">
                    <span>
                      {recipe.calorieEstimated ? "含估算项" : "USDA 已匹配"}
                    </span>
                    <button
                      onClick={() => replaceOne(channel.id)}
                    >
                      {replacingId === channel.id
                        ? "耄耋接单中…"
                        : activeSwap?.channelId === channel.id
                          ? "正在换菜…"
                          : "换一道"}
                    </button>
                  </div>
                  {replacementError?.channelId === channel.id && (
                    <div className="replacement-error" role="alert">
                      <span>{replacementError.message}</span>
                      <button onClick={() => replaceOne(channel.id)}>
                        再换一次
                      </button>
                    </div>
                  )}
                </article>
                );
              })}
            </div>
          ))}

          <div className="source-card">
            <Mascot size="small" />
            <div>
              <b>热量不是耄耋瞎猜的</b>
              <p>
                优先匹配 USDA FoodData Central 的 Foundation / SR Legacy
                数据，再按实际克数由 Python 重算。
              </p>
            </div>
          </div>

          {plan.agentTrace?.length > 0 && (
            <div className="agent-trace-card">
              <div className="agent-trace-head">
                <div>
                  <span className="eyebrow">Agent 执行记录</span>
                  <h3>耄耋不是一问一答</h3>
                </div>
                <span className="agent-badge">耄耋 · Skills</span>
              </div>
              <div className="agent-trace-list">
                {plan.agentTrace.map((step, index) => (
                  <div className="agent-trace-row" key={step.id}>
                    <span
                      className={`trace-index trace-${step.status}`}
                    >
                      {step.status === "warning" ? "!" : step.status === "repaired" ? "↻" : index + 1}
                    </span>
                    <div>
                      <b>{step.title}</b>
                      <small>{step.skill}</small>
                      <p>{step.detail}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {plan.warnings.map((warning) => (
            <p className="warning-note" key={warning}>
              △ {warning}
            </p>
          ))}
          <p className="disclaimer">{plan.disclaimer}</p>
          <button className="secondary-button" onClick={goHome}>
            再拍一冰箱
          </button>
        </section>
      )}

      {screen === "recipe" && selectedRecipeIsUsable && (
        <section className="screen">
          <button
            className="back-button"
            onClick={() =>
              navigateTo({ version: 1, screen: "result" })
            }
          >
            ← 返回菜单
          </button>
          <div className="recipe-detail-head">
            <div>
              <span className="eyebrow">耄耋开小灶</span>
              <h2>{selectedRecipe.name}</h2>
              <p>{selectedRecipe.description}</p>
            </div>
            <Mascot size="medium" />
          </div>
          <div className="detail-stats">
            <span>
              <b>{selectedRecipe.perPersonKcal}</b>
              <small>人均 kcal</small>
            </span>
            <span>
              <b>{selectedRecipe.totalMinutes}</b>
              <small>分钟</small>
            </span>
            <span>
              <b>{selectedRecipe.difficulty}</b>
              <small>难度</small>
            </span>
          </div>
          <div className="reason-card">
            <b>为什么相对低卡</b>
            <p>{selectedRecipe.lowCalorieReason}</p>
          </div>
          <h3 className="section-title">食材与热量来源</h3>
          <div className="nutrition-list">
            {[...selectedRecipe.ingredients, ...selectedRecipe.seasonings].map(
              (item, index) => (
                <div className="nutrition-row" key={`${item.name}-${index}`}>
                  <div>
                    <b>{item.name}</b>
                    <small>
                      {item.grams}g · {item.note || "按克数使用"}
                    </small>
                  </div>
                  <div className="nutrition-value">
                    <b>{item.kcal} kcal</b>
                    {item.sourceUrl ? (
                      <a href={item.sourceUrl} target="_blank" rel="noreferrer">
                        USDA · FDC #{item.sourceId}
                      </a>
                    ) : (
                      <small className="estimate-label">耄耋估算</small>
                    )}
                  </div>
                </div>
              ),
            )}
          </div>
          <h3 className="section-title">步骤预览</h3>
          <ol className="step-preview">
            {selectedRecipe.steps.map((step, index) => (
              <li key={`${step.title}-${index}`}>
                <span>{index + 1}</span>
                <div>
                  <b>{step.title}</b>
                  <p>{step.detail}</p>
                </div>
              </li>
            ))}
          </ol>
          <button
            className="primary-button sticky-action"
            onClick={() => {
              setCookStep(0);
              navigateTo({
                version: 1,
                screen: "cook",
                recipeId: selectedRecipe.id,
                cookStep: 0,
              });
            }}
          >
            开始跟着做
          </button>
        </section>
      )}

      {screen === "cook" && selectedRecipeIsUsable && (
        <section className="screen cook-screen">
          <div className="cook-top">
            <button
              onClick={() =>
                navigateTo({
                  version: 1,
                  screen: "recipe",
                  recipeId: selectedRecipe.id,
                })
              }
            >
              退出
            </button>
            <span>
              {cookStep + 1} / {selectedRecipe.steps.length}
            </span>
          </div>
          <div className="cook-mascot">
            <Mascot size="medium" />
            <span>耄耋盯着你，别把火开太大。</span>
          </div>
          <div className="step-counter">STEP {cookStep + 1}</div>
          <h2>{selectedRecipe.steps[cookStep].title}</h2>
          <p className="cook-detail">{selectedRecipe.steps[cookStep].detail}</p>
          <div className="timer-pill">⏱ 约 {selectedRecipe.steps[cookStep].minutes} 分钟</div>
          <div className="cook-actions">
            <button
              className="secondary-button"
              disabled={cookStep === 0}
              onClick={() =>
                setCookStep((step) => {
                  const nextStep = Math.max(0, step - 1);
                  replaceNavigationState({
                    version: 1,
                    screen: "cook",
                    recipeId: selectedRecipe.id,
                    cookStep: nextStep,
                  });
                  return nextStep;
                })
              }
            >
              上一步
            </button>
            <button
              className="primary-button"
              onClick={() => {
                if (cookStep === selectedRecipe.steps.length - 1) {
                  navigateTo({ version: 1, screen: "result" });
                } else {
                  setCookStep((step) => {
                    const nextStep = step + 1;
                    replaceNavigationState({
                      version: 1,
                      screen: "cook",
                      recipeId: selectedRecipe.id,
                      cookStep: nextStep,
                    });
                    return nextStep;
                  });
                }
              }}
            >
              {cookStep === selectedRecipe.steps.length - 1 ? "做好了，开吃" : "完成，下一步"}
            </button>
          </div>
        </section>
      )}

      {screen === "error" && (
        <section className="screen center-screen error-screen">
          <Mascot size="large" angry />
          <span className="eyebrow">耄耋炸毛了</span>
          <h2>这次没搞定</h2>
          <p>{errorMessage}</p>
          {errorRetry && (
            <button className="primary-button" onClick={errorRetry}>
              再试一次
            </button>
          )}
          <button className="secondary-button" onClick={goHome}>
            回首页检查
          </button>
        </section>
      )}
    </main>
  );
}
