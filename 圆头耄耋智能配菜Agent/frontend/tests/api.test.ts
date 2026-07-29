import { afterEach, describe, expect, test, vi } from "vitest";
import { readFileSync } from "node:fs";

import "./setup";
import {
  fetchMealPlan,
  startChannelSwap,
  waitForChannelSwap,
} from "../lib/api";
import type { ChannelCommandRequest } from "../lib/types";
import {
  cloneFixture,
  queuedSwapJob,
  validMealPlan,
} from "./fixtures";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const command: ChannelCommandRequest = {
  planId: "plan-1",
  channelId: "channel-a",
  planRevision: 0,
  channelRevision: 0,
  idempotencyKey: "swap-000000000001",
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("1.7 on-demand channel API", () => {
  test("does not expose refill or replacement endpoints", () => {
    const source = readFileSync(`${process.cwd()}/lib/api.ts`, "utf8");
    expect(source).not.toContain("/api/plans/channel-refills");
    expect(source).not.toContain("/api/plans/replacement-jobs");
  });

  test("GETs and validates the registered plan", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(validMealPlan));
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchMealPlan("plan-1")).resolves.toEqual(validMealPlan);
  });

  test("POSTs one swap command and returns its job", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(queuedSwapJob, 202));
    vi.stubGlobal("fetch", fetchMock);

    await expect(startChannelSwap(command)).resolves.toEqual(queuedSwapJob);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/plans/channel-swaps");
  });

  test("long-polls swap jobs and returns the terminal plan", async () => {
    const changed = cloneFixture(validMealPlan);
    changed.revision = 1;
    changed.meals[0].channels[0].revision = 1;
    changed.meals[0].channels[0].current.id = "recipe-swapped";
    const result = { plan: changed, channelId: "channel-a" };
    const running = {
      ...queuedSwapJob,
      status: "running" as const,
      phase: "swapping",
      message: "正在换菜",
      version: 1,
    };
    const completed = {
      ...running,
      status: "completed" as const,
      version: 2,
      result,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(running))
      .mockResolvedValueOnce(jsonResponse(completed));
    vi.stubGlobal("fetch", fetchMock);

    await expect(waitForChannelSwap(queuedSwapJob)).resolves.toEqual(result);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/plans/channel-swap-jobs/job-swap-1?after=0&waitSeconds=25",
      "/api/plans/channel-swap-jobs/job-swap-1?after=1&waitSeconds=25",
    ]);
  });
});
