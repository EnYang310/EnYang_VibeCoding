import {
  act,
  cleanup,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import "./setup";
import type {
  ApiFailure,
  ChannelSwapResult,
  MealPlan,
} from "../lib/types";
import { SESSION_STORAGE_KEY } from "../lib/session";
import {
  cloneFixture,
  queuedSwapJob,
  swappingSession,
  validMealPlan,
  validSessionV2,
} from "./fixtures";

const apiMocks = vi.hoisted(() => ({
  fetchMealPlan: vi.fn(),
  generateMealPlan: vi.fn(),
  recognizeIngredients: vi.fn(),
  startChannelSwap: vi.fn(),
  waitForChannelSwap: vi.fn(),
}));

const imageMocks = vi.hoisted(() => ({
  compressImage: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  ApiError: class ApiError extends Error {
    code: string;
    retryable: boolean;

    constructor(failure: ApiFailure) {
      super(failure.message);
      this.code = failure.code;
      this.retryable = failure.retryable;
    }
  },
  ...apiMocks,
}));

vi.mock("../lib/image", () => imageMocks);

import MaodieApp from "../components/maodie-app";

type Deferred<T> = {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (error: unknown) => void;
};

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function swappedPlan(
  source = validMealPlan,
  channelId = "channel-a",
): MealPlan {
  const plan = cloneFixture(source);
  const channel = plan.meals
    .flatMap((meal) => meal.channels)
    .find((candidate) => candidate.id === channelId)!;
  channel.current = {
    ...channel.current,
    id: `${channelId}-swapped-${plan.revision + 1}`,
    name: `${channel.current.name}新做法`,
  };
  channel.revision += 1;
  plan.revision += 1;
  return plan;
}

async function openSavedPlan(user = userEvent.setup()) {
  render(<MaodieApp />);
  await user.click(await screen.findByRole("button", { name: /上次菜单/ }));
  return user;
}

beforeEach(() => {
  history.replaceState(null, "", "/");
  localStorage.clear();
  localStorage.setItem(
    SESSION_STORAGE_KEY,
    JSON.stringify(validSessionV2),
  );
  apiMocks.fetchMealPlan.mockResolvedValue(validMealPlan);
  apiMocks.generateMealPlan.mockReset();
  apiMocks.recognizeIngredients.mockReset();
  apiMocks.startChannelSwap.mockReset();
  apiMocks.waitForChannelSwap.mockReset();
  imageMocks.compressImage.mockReset();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  localStorage.clear();
});

describe("1.7 on-demand recipe swap", () => {
  test("restores a current-only menu", async () => {
    const user = await openSavedPlan();

    expect(screen.getByText("番茄炒菜")).toBeInTheDocument();
    expect(screen.getByText("香煎鸡胸")).toBeInTheDocument();
    expect(screen.getByText("2 道菜")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /番茄炒菜/ }));
    expect(
      screen.getByRole("heading", { name: "番茄炒菜" }),
    ).toBeInTheDocument();
  });

  test("keeps the old dish until one on-demand result succeeds", async () => {
    const polling = deferred<ChannelSwapResult>();
    apiMocks.startChannelSwap.mockResolvedValue(queuedSwapJob);
    apiMocks.waitForChannelSwap.mockReturnValue(polling.promise);
    const user = await openSavedPlan();

    await user.click(screen.getAllByRole("button", { name: "换一道" })[0]);

    expect(screen.getByText("番茄炒菜")).toBeInTheDocument();
    expect(screen.getByText("正在换菜…")).toBeInTheDocument();
    expect(apiMocks.startChannelSwap).toHaveBeenCalledWith(
      expect.objectContaining({
        planId: "plan-1",
        channelId: "channel-a",
        planRevision: 0,
        channelRevision: 0,
        idempotencyKey: expect.stringMatching(/^swap-/),
      }),
      expect.any(AbortSignal),
    );

    const changed = swappedPlan();
    await act(async () => {
      polling.resolve({ plan: changed, channelId: "channel-a" });
      await polling.promise;
    });

    expect(screen.getByText("番茄炒菜新做法")).toBeInTheDocument();
    expect(screen.queryByText("番茄炒菜")).not.toBeInTheDocument();
  });

  test("busy clicks open a persistent angry modal and never send or queue", async () => {
    const polling = deferred<ChannelSwapResult>();
    apiMocks.startChannelSwap.mockResolvedValue(queuedSwapJob);
    apiMocks.waitForChannelSwap.mockReturnValue(polling.promise);
    const user = await openSavedPlan();
    const buttons = screen.getAllByRole("button", { name: "换一道" });

    await user.click(buttons[0]);
    await user.click(buttons[1]);

    const dialog = await screen.findByRole("dialog", {
      name: "耄耋哈气了",
    });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByAltText("哈气耄耋")).toHaveAttribute(
      "src",
      "/maodie-angry.jpg",
    );
    expect(screen.getByText("别急，一个一个来！")).toBeInTheDocument();
    expect(apiMocks.startChannelSwap).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "关闭提示" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(apiMocks.waitForChannelSwap).toHaveBeenCalledTimes(1);

    await user.click(buttons[1]);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(apiMocks.startChannelSwap).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "关闭提示" }));
    const changed = swappedPlan();
    await act(async () => {
      polling.resolve({ plan: changed, channelId: "channel-a" });
      await polling.promise;
    });
    expect(screen.getByText("番茄炒菜新做法")).toBeInTheDocument();
  });

  test("failure preserves the old dish and a later click starts a fresh swap", async () => {
    const retryPolling = deferred<ChannelSwapResult>();
    apiMocks.startChannelSwap
      .mockResolvedValueOnce(queuedSwapJob)
      .mockResolvedValueOnce({ ...queuedSwapJob, id: "job-swap-2" });
    apiMocks.waitForChannelSwap
      .mockRejectedValueOnce(new Error("这道菜没换成。"))
      .mockReturnValueOnce(retryPolling.promise);
    const user = await openSavedPlan();

    await user.click(screen.getAllByRole("button", { name: "换一道" })[0]);
    expect(await screen.findByText("这道菜没换成。")).toBeInTheDocument();
    expect(screen.getByText("番茄炒菜")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "再换一次" }));
    expect(apiMocks.startChannelSwap).toHaveBeenCalledTimes(2);
  });

  test("refresh resumes the same job and busy click still sends nothing", async () => {
    const session = swappingSession();
    localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
    apiMocks.fetchMealPlan.mockResolvedValue(session.plan);
    apiMocks.waitForChannelSwap.mockReturnValue(
      deferred<ChannelSwapResult>().promise,
    );
    const user = await openSavedPlan();

    await waitFor(() =>
      expect(apiMocks.waitForChannelSwap).toHaveBeenCalledWith(
        expect.objectContaining({
          id: "job-swap-1",
          kind: "channel_swap",
        }),
        expect.any(AbortSignal),
        expect.any(Function),
      ),
    );
    await user.click(screen.getByRole("button", { name: "换一道" }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(apiMocks.startChannelSwap).not.toHaveBeenCalled();
  });
});

describe("visual and picker boundaries", () => {
  test("modal CSS blocks the background and animates the angry avatar", () => {
    const css = readFileSync(`${process.cwd()}/app/globals.css`, "utf8");
    expect(css).toContain(".swap-busy-overlay");
    expect(css).toMatch(/\.swap-busy-overlay\s*\{[^}]*inset:\s*0/s);
    expect(css).toContain("@keyframes maodie-angry-shake");
  });

  test("desktop camera action uses the ordinary picker", async () => {
    localStorage.clear();
    const user = userEvent.setup();
    const { container } = render(<MaodieApp />);
    const cameraInput = container.querySelector<HTMLInputElement>(
      'input[type="file"][capture="environment"]',
    )!;
    const albumInput = Array.from(
      container.querySelectorAll<HTMLInputElement>('input[type="file"]'),
    ).find((input) => !input.hasAttribute("capture"))!;
    const cameraClick = vi.spyOn(cameraInput, "click");
    const albumClick = vi.spyOn(albumInput, "click");

    await user.click(
      screen.getByRole("button", {
        name: "📷 拍食材，让耄耋掌勺",
      }),
    );

    expect(albumClick).toHaveBeenCalledTimes(1);
    expect(cameraClick).not.toHaveBeenCalled();
  });
});
