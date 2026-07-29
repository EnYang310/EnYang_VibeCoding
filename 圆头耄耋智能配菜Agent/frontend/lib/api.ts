import type {
  ApiFailure,
  AsyncJob,
  ChannelCommandRequest,
  ChannelSwapResult,
  Ingredient,
  MealPlan,
  PlanConstraints,
  RecognitionResult,
} from "./types";
import {
  ApiFailureSchema,
  AsyncJobSchema,
  ChannelSwapResultSchema,
  ChannelSwapRequestSchema,
  MealPlanSchema,
} from "./contracts";
import type { z } from "zod";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const JOB_LONG_POLL_SECONDS = 25;
const MAX_POLL_NETWORK_FAILURES = 3;

export class ApiError extends Error {
  code: string;
  retryable: boolean;

  constructor(failure: ApiFailure) {
    super(failure.message);
    this.name = "ApiError";
    this.code = failure.code;
    this.retryable = failure.retryable;
  }
}

async function post<T>(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ApiError({
      code: "BACKEND_OFFLINE",
      message: "没连上后端，先确认 Python 服务已经启动。",
      retryable: true,
    });
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const failure = ApiFailureSchema.safeParse(
      (payload as { error?: unknown } | null)?.error,
    );
    throw new ApiError(
      failure.success
        ? failure.data
        : {
            code: "UNKNOWN_ERROR",
            message: "耄耋这次没接住，再试一下。",
            retryable: response.status >= 500,
          },
    );
  }
  return payload as T;
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "GET",
      cache: "no-store",
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ApiError({
      code: "BACKEND_OFFLINE",
      message: "没连上后端，先确认 Python 服务已经启动。",
      retryable: true,
    });
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const failure = ApiFailureSchema.safeParse(
      (payload as { error?: unknown } | null)?.error,
    );
    throw new ApiError(
      failure.success
        ? failure.data
        : {
            code: "UNKNOWN_ERROR",
            message: "耄耋这次没接住，再试一下。",
            retryable: response.status >= 500,
          },
    );
  }
  return payload as T;
}

function parseResponse<Schema extends z.ZodTypeAny>(
  schema: Schema,
  payload: unknown,
): z.output<Schema> {
  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw new ApiError({
      code: "INVALID_API_RESPONSE",
      message: "后端返回的数据不完整，请刷新后重试。",
      retryable: true,
    });
  }
  return parsed.data;
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function waitForJob<T>(
  initialJob: AsyncJob<T>,
  statusPath: (job: AsyncJob<T>) => string,
  onProgress?: (message: string) => void,
  signal?: AbortSignal,
): Promise<T> {
  let job = initialJob;
  let networkFailures = 0;

  while (true) {
    onProgress?.(job.message);
    if (job.status === "completed" && job.result) {
      return job.result;
    }
    if (job.status === "failed") {
      throw new ApiError(
        job.error ?? {
          code: "JOB_FAILED",
          message: job.message || "耄耋这次没接住，请重新生成。",
          retryable: true,
        },
      );
    }

    try {
      job = await get<AsyncJob<T>>(statusPath(job), signal);
      networkFailures = 0;
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw error;
      }
      networkFailures += 1;
      if (networkFailures >= MAX_POLL_NETWORK_FAILURES) {
        throw error;
      }
      await delay(2000);
    }
  }
}

export async function fetchMealPlan(
  planId: string,
  signal?: AbortSignal,
): Promise<MealPlan> {
  const payload = await get<unknown>(
    `/api/plans/${encodeURIComponent(planId)}`,
    signal,
  );
  return parseResponse(MealPlanSchema, payload) as MealPlan;
}

export async function startChannelSwap(
  request: ChannelCommandRequest,
  signal?: AbortSignal,
): Promise<AsyncJob<ChannelSwapResult>> {
  const command = parseResponse(ChannelSwapRequestSchema, request);
  const payload = await post<unknown>(
    "/api/plans/channel-swaps",
    command,
    signal,
  );
  return parseResponse(
    AsyncJobSchema(ChannelSwapResultSchema),
    payload,
  ) as AsyncJob<ChannelSwapResult>;
}

export async function waitForChannelSwap(
  initialJob: AsyncJob<ChannelSwapResult>,
  signal?: AbortSignal,
  onProgress?: (message: string) => void,
): Promise<ChannelSwapResult> {
  const schema = AsyncJobSchema(ChannelSwapResultSchema);
  let job = parseResponse(schema, initialJob) as AsyncJob<ChannelSwapResult>;
  let networkFailures = 0;

  while (true) {
    onProgress?.(job.message);
    if (job.status === "completed" && job.result !== null) {
      return job.result;
    }
    if (job.status === "failed") {
      throw new ApiError(
        job.error ?? {
          code: "CHANNEL_SWAP_FAILED",
          message: job.message || "这道菜没换成，请再试一次。",
          retryable: true,
        },
      );
    }

    try {
      const payload = await get<unknown>(
        `/api/plans/channel-swap-jobs/${encodeURIComponent(job.id)}?after=${job.version}&waitSeconds=${JOB_LONG_POLL_SECONDS}`,
        signal,
      );
      job = parseResponse(schema, payload) as AsyncJob<ChannelSwapResult>;
      networkFailures = 0;
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw error;
      }
      networkFailures += 1;
      if (networkFailures >= MAX_POLL_NETWORK_FAILURES) {
        throw error;
      }
      await delay(2000);
    }
  }
}

export function recognizeIngredients(
  imageDataUrl: string,
  onProgress?: (message: string) => void,
  signal?: AbortSignal,
): Promise<RecognitionResult> {
  return post<AsyncJob<RecognitionResult>>("/api/ingredients/jobs", {
    imageDataUrl,
  }, signal).then((job) =>
    waitForJob(
      job,
      (current) =>
        `/api/ingredients/jobs/${current.id}?after=${current.version}&waitSeconds=${JOB_LONG_POLL_SECONDS}`,
      onProgress,
      signal,
    ),
  );
}

export function generateMealPlan(
  ingredients: Ingredient[],
  constraints: PlanConstraints,
  onProgress?: (message: string) => void,
  signal?: AbortSignal,
): Promise<MealPlan> {
  const body = {
    ingredients: ingredients.map(({ confidence: _, ...item }) => item),
    ...constraints,
  };
  return post<AsyncJob<MealPlan>>("/api/plans/jobs", body, signal).then((job) =>
    waitForJob(
      job,
      (current) =>
        `/api/plans/jobs/${current.id}?after=${current.version}&waitSeconds=${JOB_LONG_POLL_SECONDS}`,
      onProgress,
      signal,
    ),
  );
}
