import asyncio
import hashlib
import os
import sqlite3
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .agent import run_plan_pipeline
from .channels import RecipeChannelService
from .health import inspect_local_database
from .jobs import AsyncJobStore
from .kimi import (
    AppError,
    kimi_model,
    recognize_ingredients,
    resolve_api_key,
)
from .models import (
    AsyncJobResponse,
    ChannelSwapRequest,
    ChannelSwapResult,
    GeneratePlanRequest,
    Ingredient,
    MealPlan,
    RecognitionResult,
    RecognizeRequest,
)
from .skills import skill_versions


def _max_concurrent_jobs() -> int:
    raw_value = os.getenv("KIMI_MAX_CONCURRENT_JOBS", "4").strip()
    try:
        return max(1, min(int(raw_value), 50))
    except ValueError:
        return 4


job_store = AsyncJobStore(max_concurrency=_max_concurrent_jobs())
channel_service = RecipeChannelService(job_store)


app = FastAPI(
    title="耄耋掌勺 API",
    version="1.7.0",
    description="耄耋食材识别、低热量菜品设计与基础热量估算。",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(AppError)
async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "retryable": exc.retryable,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    fields = list(
        dict.fromkeys(
            ".".join(str(part) for part in error.get("loc", ())[1:])
            for error in exc.errors()
            if error.get("loc", ())[1:]
        )
    )
    field_hint = "（{}）".format("、".join(fields[:5])) if fields else ""
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "INVALID_REQUEST",
                "message": "这次提交的信息不完整{}，请检查后再试。".format(
                    field_hint
                ),
                "retryable": False,
            }
        },
    )


@app.get("/__tcb_probe__")
async def tcb_probe() -> dict:
    return {"ok": True}


@app.get("/api/health")
async def health() -> dict:
    try:
        nutrition = await asyncio.to_thread(inspect_local_database)
        nutrition_payload = nutrition.as_payload()
        ok = nutrition.status == "healthy"
    except (OSError, sqlite3.Error, TypeError, ValueError):
        nutrition_payload = {
            "status": "unhealthy",
            "integrity": "unavailable",
            "foodCount": 0,
            "ftsCount": 0,
            "ftsAvailable": False,
            "datasets": [],
        }
        ok = False
    return {
        "ok": ok,
        "service": "maodie-api",
        "appVersion": "1.7.0",
        "model": kimi_model(),
        "agent": "skill-driven",
        "skills": skill_versions(),
        "nutritionDb": nutrition_payload,
    }


@app.post("/api/ingredients/recognize", response_model=RecognitionResult)
async def recognize(body: RecognizeRequest) -> RecognitionResult:
    api_key = resolve_api_key()
    result = await recognize_ingredients(body.imageDataUrl, api_key)
    ingredients = [
        Ingredient(
            id="ingredient-{}".format(uuid4().hex[:10]),
            **item.model_dump(),
        )
        for item in result.ingredients
    ]
    return RecognitionResult(
        ingredients=ingredients,
        warnings=result.warnings,
        skillVersion=skill_versions().get("ingredient-vision", "unknown"),
    )


@app.post(
    "/api/ingredients/jobs",
    status_code=202,
    response_model=AsyncJobResponse[RecognitionResult],
)
async def create_recognition_job(body: RecognizeRequest):
    api_key = resolve_api_key()
    dedupe_key = hashlib.sha256(body.imageDataUrl.encode("utf-8")).hexdigest()

    async def runner(progress):
        progress("recognizing", "耄耋正在看照片里的食材…")
        result = await recognize_ingredients(body.imageDataUrl, api_key)
        ingredients = [
            Ingredient(
                id="ingredient-{}".format(uuid4().hex[:10]),
                **item.model_dump(),
            )
            for item in result.ingredients
        ]
        return RecognitionResult(
            ingredients=ingredients,
            warnings=result.warnings,
            skillVersion=skill_versions().get("ingredient-vision", "unknown"),
        )

    return job_store.start(
        "recognition",
        runner,
        dedupe_key=dedupe_key,
        timeout_seconds=360,
    )


@app.get(
    "/api/ingredients/jobs/{job_id}",
    response_model=AsyncJobResponse[RecognitionResult],
)
async def get_recognition_job(
    job_id: str,
    after: Optional[int] = None,
    waitSeconds: int = Query(default=25, ge=1, le=30),
):
    job = (
        await job_store.wait_for_update(job_id, after, waitSeconds)
        if after is not None
        else job_store.get(job_id)
    )
    if job is None or job["kind"] != "recognition":
        raise AppError(
            "RECOGNITION_JOB_NOT_FOUND",
            "这次识别任务已经失效，请重新选择照片。",
            404,
            True,
        )
    return job


@app.post("/api/plans/generate", response_model=MealPlan)
async def create_plan(body: GeneratePlanRequest) -> MealPlan:
    api_key = resolve_api_key()
    plan = await run_plan_pipeline(body, api_key)
    return channel_service.register_plan(plan, body)


@app.post(
    "/api/plans/jobs",
    status_code=202,
    response_model=AsyncJobResponse[MealPlan],
)
async def create_plan_job(body: GeneratePlanRequest):
    api_key = resolve_api_key()
    dedupe_key = hashlib.sha256(body.model_dump_json().encode("utf-8")).hexdigest()

    async def runner(progress):
        plan = await run_plan_pipeline(body, api_key, progress)
        return channel_service.register_plan(plan, body)

    return job_store.start(
        "plan",
        runner,
        dedupe_key=dedupe_key,
        timeout_seconds=900,
    )


@app.get(
    "/api/plans/jobs/{job_id}",
    response_model=AsyncJobResponse[MealPlan],
)
async def get_plan_job(
    job_id: str,
    after: Optional[int] = None,
    waitSeconds: int = Query(default=25, ge=1, le=30),
):
    job = (
        await job_store.wait_for_update(job_id, after, waitSeconds)
        if after is not None
        else job_store.get(job_id)
    )
    if job is None or job["kind"] != "plan":
        raise AppError(
            "PLAN_JOB_NOT_FOUND",
            "这次菜单任务已经失效，请重新生成。",
            404,
            True,
        )
    return job


@app.get("/api/plans/{plan_id}", response_model=MealPlan)
async def get_plan(plan_id: str) -> MealPlan:
    return channel_service.get_plan(plan_id)


@app.post(
    "/api/plans/channel-swaps",
    status_code=202,
    response_model=AsyncJobResponse[ChannelSwapResult],
)
async def swap_plan_channel(
    body: ChannelSwapRequest,
) -> AsyncJobResponse[ChannelSwapResult]:
    api_key = resolve_api_key()
    return channel_service.begin_swap(body, api_key)


@app.get(
    "/api/plans/channel-swap-jobs/{job_id}",
    response_model=AsyncJobResponse[ChannelSwapResult],
)
async def get_channel_swap_job(
    job_id: str,
    after: Optional[int] = None,
    waitSeconds: int = Query(default=25, ge=1, le=30),
):
    if after is not None:
        job = await job_store.wait_for_update(
            job_id,
            after,
            waitSeconds,
        )
        if job is not None and job.get("kind") != "channel_swap":
            job = None
    else:
        job = channel_service.get_swap_job(job_id)
    if job is None:
        raise AppError(
            "CHANNEL_SWAP_JOB_NOT_FOUND",
            "这次换菜任务已经失效，请刷新菜单。",
            404,
            True,
        )
    return job


static_dir = Path(os.getenv("MAODIE_STATIC_DIR", ""))
if static_dir.is_dir() and (static_dir / "index.html").is_file():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="frontend")
