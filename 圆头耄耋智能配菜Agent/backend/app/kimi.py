import asyncio
import base64
import binascii
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Type

import httpx
from pydantic import BaseModel, ValidationError

from .contracts import (
    MODEL_CONTRACT_VERSION,
    compact_contract_skeleton,
    kimi_mfjs_schema,
)
from .models import (
    RecognizeModelResult,
)
from .skills import load_skill
from .shared_key import read_shared_key


logger = logging.getLogger("uvicorn.error")
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _kimi_max_concurrent_requests() -> int:
    raw_value = os.getenv("KIMI_MAX_CONCURRENT_REQUESTS", "8").strip()
    try:
        return max(1, min(int(raw_value), 50))
    except ValueError:
        return 8


_KIMI_REQUEST_SEMAPHORE = asyncio.Semaphore(_kimi_max_concurrent_requests())
_KIMI_RATE_LOCK = asyncio.Lock()
_last_kimi_request_started = 0.0


def _kimi_min_request_interval() -> float:
    raw_value = os.getenv("KIMI_MIN_REQUEST_INTERVAL_SECONDS", "0").strip()
    try:
        return max(0.0, float(raw_value))
    except ValueError:
        return 0.0


def _kimi_request_timeout() -> float:
    raw_value = os.getenv("KIMI_REQUEST_TIMEOUT_SECONDS", "300").strip()
    try:
        return max(30.0, min(float(raw_value), 600.0))
    except ValueError:
        return 300.0


def kimi_model() -> str:
    return os.getenv("KIMI_MODEL", "kimi-k2.6").strip() or "kimi-k2.6"


def _reasoning_body(model: str, reasoning_effort: str) -> Dict[str, Any]:
    if reasoning_effort not in {"low", "medium", "high"}:
        raise ValueError("unsupported reasoning_effort")
    if re.match(r"^kimi-k2\.(?:5|6)(?:$|[-:])", model):
        return {
            "thinking": {
                "type": (
                    "disabled"
                    if reasoning_effort == "low"
                    else "enabled"
                )
            }
        }
    if re.match(r"^kimi-k3(?:$|[-:])", model):
        return {"reasoning_effort": reasoning_effort}
    return {}


async def _wait_for_kimi_rate_slot(stage: str) -> None:
    global _last_kimi_request_started

    interval = _kimi_min_request_interval()
    elapsed = time.monotonic() - _last_kimi_request_started
    delay = max(0.0, interval - elapsed)
    if delay:
        logger.info(
            "Kimi pacing: stage=%s delay=%.1fs",
            stage,
            delay,
        )
        await asyncio.sleep(delay)
    _last_kimi_request_started = time.monotonic()


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable


def resolve_api_key() -> str:
    key = (
        os.getenv("MOONSHOT_API_KEY", "").strip()
        or (read_shared_key() or "")
    )
    if not key:
        raise AppError(
            "API_KEY_REQUIRED",
            "耄耋服务还没配置好，请联系管理员。",
            503,
        )
    if len(key) < 10:
        raise AppError("API_KEY_INVALID", "这个 Key 看起来不完整，请重新检查。", 401)
    return key


def validate_image_data_url(image_data_url: str) -> str:
    matched = re.fullmatch(
        r"data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=\s]+)",
        image_data_url,
        flags=re.IGNORECASE,
    )
    if matched is None:
        raise AppError(
            "INVALID_IMAGE",
            "请上传真实的 JPG、PNG 或 WebP 图片。",
            400,
            False,
        )
    mime = matched.group(1).lower()
    try:
        payload = base64.b64decode(
            re.sub(r"\s+", "", matched.group(2)),
            validate=True,
        )
    except (binascii.Error, ValueError) as exc:
        raise AppError(
            "INVALID_IMAGE",
            "图片内容损坏，请重新选择。",
            400,
            False,
        ) from exc
    if not payload or len(payload) > MAX_IMAGE_BYTES:
        raise AppError(
            "INVALID_IMAGE",
            "图片为空或过大，请重新选择。",
            400,
            False,
        )
    detected: Optional[str] = None
    if payload.startswith(b"\xff\xd8\xff"):
        detected = "image/jpeg"
    elif payload.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "image/png"
    elif (
        len(payload) >= 12
        and payload.startswith(b"RIFF")
        and payload[8:12] == b"WEBP"
    ):
        detected = "image/webp"
    if detected != mime:
        raise AppError(
            "INVALID_IMAGE",
            "图片格式与内容不一致，请重新选择。",
            400,
            False,
        )
    return detected


def extract_json(content: str) -> Dict[str, Any]:
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AppError(
            "AI_BAD_RESPONSE",
            "耄耋听懂了食材，但没整理好格式，请再试一次。",
            502,
            True,
        ) from exc
    if not isinstance(parsed, dict):
        raise AppError(
            "AI_BAD_RESPONSE",
            "耄耋返回的结果格式不正确，请重试。",
            502,
            True,
        )
    return parsed


def structured_response_format(
    response_model: Type[BaseModel], schema_name: str
) -> Dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name,
            "strict": True,
            "schema": kimi_mfjs_schema(response_model),
        },
    }


def build_format_repair_prompt(
    *,
    raw: str,
    model: Type[BaseModel],
    error_paths: Optional[List[str]] = None,
) -> str:
    if len(raw) > 80_000:
        raise AppError(
            "AI_OUTPUT_TRUNCATED",
            "耄耋的结果过长，无法安全修复，请重新生成。",
            502,
            True,
        )
    errors = error_paths or []
    error_summary = "\n".join(
        "- {}".format(item[:300])
        for item in errors[:20]
    ) or "- 未提供"
    return (
        "契约版本：{version}\n"
        "紧凑骨架：{skeleton}\n"
        "原始输出：{raw}\n"
        "错误路径：\n{errors}"
    ).format(
        version=MODEL_CONTRACT_VERSION,
        skeleton=compact_contract_skeleton(model),
        raw=raw,
        errors=error_summary,
    )


def _map_kimi_http_error(
    response: httpx.Response,
) -> Optional[AppError]:
    status = response.status_code
    if status in {401, 403}:
        return AppError(
            "API_KEY_INVALID",
            "耄耋服务认证失败，请联系管理员。",
            401,
            False,
        )
    if status == 429:
        return AppError(
            "AI_RATE_LIMITED",
            "耄耋今天有点忙，请稍等一会儿再试。",
            429,
            True,
        )
    if status in {400, 404, 422}:
        return AppError(
            "AI_REQUEST_REJECTED",
            "耄耋请求格式没有被模型服务接受，请稍后重试。",
            502,
            False,
        )
    if 400 <= status < 500:
        return AppError(
            "AI_REQUEST_REJECTED",
            "耄耋请求没有被模型服务接受，请稍后重试。",
            502,
            False,
        )
    if 500 <= status:
        return AppError(
            "AI_UNAVAILABLE",
            "耄耋暂时没接住这次请求，请重试。",
            502,
            True,
        )
    return None


def _decode_chat_message(response: httpx.Response) -> Dict[str, Any]:
    try:
        payload = response.json()
    except (ValueError, UnicodeDecodeError) as exc:
        raise AppError(
            "AI_BAD_RESPONSE",
            "耄耋收到了无法解析的模型响应，请重试。",
            502,
            True,
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            "AI_BAD_RESPONSE",
            "耄耋返回的结果格式不正确，请重试。",
            502,
            True,
        )

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AppError(
            "AI_EMPTY_RESPONSE",
            "耄耋这次没有返回结果，请重试。",
            502,
            True,
        )
    choice = choices[0]
    if not isinstance(choice, dict):
        raise AppError(
            "AI_EMPTY_RESPONSE",
            "耄耋这次没有返回结果，请重试。",
            502,
            True,
        )
    if choice.get("finish_reason") == "length":
        raise AppError(
            "AI_OUTPUT_TRUNCATED",
            "耄耋的结果被截断了，请重新生成。",
            502,
            True,
        )

    message = choice.get("message")
    if not isinstance(message, dict):
        raise AppError(
            "AI_EMPTY_RESPONSE",
            "耄耋这次没有返回结果，请重试。",
            502,
            True,
        )
    return message


def _response_telemetry(
    response: httpx.Response,
    *,
    stage: str,
    model: str,
    elapsed_seconds: float,
) -> Dict[str, Any]:
    try:
        payload = response.json()
    except (ValueError, UnicodeDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    prompt_details = usage.get("prompt_tokens_details")
    if not isinstance(prompt_details, dict):
        prompt_details = {}
    choices = payload.get("choices")
    first_choice = (
        choices[0]
        if isinstance(choices, list)
        and choices
        and isinstance(choices[0], dict)
        else {}
    )

    def integer(name: str, fallback: int = 0) -> int:
        value = usage.get(name, fallback)
        return int(value) if isinstance(value, (int, float)) else fallback

    cached_value = prompt_details.get(
        "cached_tokens",
        usage.get("cached_tokens", 0),
    )
    cached_tokens = (
        int(cached_value)
        if isinstance(cached_value, (int, float))
        else 0
    )
    finish_reason = first_choice.get("finish_reason", "")
    return {
        "stage": stage,
        "model": model,
        "status": response.status_code,
        "elapsedSeconds": round(elapsed_seconds, 3),
        "inputTokens": integer("prompt_tokens"),
        "outputTokens": integer("completion_tokens"),
        "cachedTokens": cached_tokens,
        "totalTokens": integer("total_tokens"),
        "finishReason": (
            str(finish_reason) if finish_reason is not None else ""
        ),
        "contractVersion": MODEL_CONTRACT_VERSION,
    }


async def chat_completion(
    api_key: str,
    messages: List[Dict[str, Any]],
    max_completion_tokens: int,
    *,
    reasoning_effort: str = "low",
    response_model: Optional[Type[BaseModel]] = None,
    schema_name: str = "response",
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Any] = None,
) -> Dict[str, Any]:
    base_url = os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1").rstrip("/")
    model = kimi_model()
    started_at = time.monotonic()
    stage = schema_name if response_model else "tool-call"
    body = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": max_completion_tokens,
    }
    body.update(_reasoning_body(model, reasoning_effort))
    if response_model:
        body["response_format"] = structured_response_format(
            response_model, schema_name
        )
    if tools:
        body["tools"] = tools
    if tool_choice is not None:
        body["tool_choice"] = tool_choice

    logger.info(
        "Kimi request started: stage=%s reasoning=%s max_tokens=%s tool_choice=%s",
        stage,
        reasoning_effort,
        max_completion_tokens,
        tool_choice,
    )
    try:
        async with _KIMI_REQUEST_SEMAPHORE:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(_kimi_request_timeout())
            ) as client:
                for attempt in range(3):
                    async with _KIMI_RATE_LOCK:
                        await _wait_for_kimi_rate_slot(stage)
                    response = await client.post(
                        "{}/chat/completions".format(base_url),
                        headers={
                            "Authorization": "Bearer {}".format(api_key),
                            "Content-Type": "application/json",
                        },
                        json=body,
                    )
                    if response.status_code != 429 or attempt == 2:
                        break
                    retry_after = response.headers.get("retry-after", "").strip()
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        delay = 20.0 * (attempt + 1)
                    delay = min(60.0, max(5.0, delay))
                    logger.warning(
                        "Kimi rate limited: stage=%s retry=%s delay=%.1fs",
                        stage,
                        attempt + 1,
                        delay,
                    )
                    await asyncio.sleep(delay)
    except httpx.TimeoutException as exc:
        logger.warning(
            "Kimi request timed out: stage=%s elapsed=%.1fs",
            stage,
            time.monotonic() - started_at,
        )
        raise AppError(
            "AI_TIMEOUT",
            (
                "耄耋看图超时了，换张更清楚的照片再试。"
                if stage == "recognized_ingredients"
                else "耄耋这次想菜超时了，请再试一次。"
            ),
            504,
            True,
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning(
            "Kimi request failed: stage=%s elapsed=%.1fs error=%s",
            stage,
            time.monotonic() - started_at,
            type(exc).__name__,
        )
        raise AppError(
            "AI_UNAVAILABLE",
            "暂时连不上耄耋，请检查网络后重试。",
            503,
            True,
        ) from exc

    mapped_error = _map_kimi_http_error(response)
    if mapped_error is not None:
        raise mapped_error
    message = _decode_chat_message(response)
    elapsed_seconds = time.monotonic() - started_at
    telemetry = _response_telemetry(
        response,
        stage=stage,
        model=model,
        elapsed_seconds=elapsed_seconds,
    )
    logger.info(
        (
            "Kimi request completed: stage=%s model=%s status=%s "
            "elapsed=%.1fs input_tokens=%s output_tokens=%s "
            "cached_tokens=%s finish_reason=%s contract=%s"
        ),
        stage,
        model,
        response.status_code,
        elapsed_seconds,
        telemetry["inputTokens"],
        telemetry["outputTokens"],
        telemetry["cachedTokens"],
        telemetry["finishReason"],
        MODEL_CONTRACT_VERSION,
        extra={"kimi_event": telemetry},
    )
    return message


def parse_structured_message(
    message: Dict[str, Any], response_model: Type[BaseModel], error_message: str
) -> BaseModel:
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise AppError("AI_EMPTY_RESPONSE", error_message, 502, True)
    try:
        return response_model.model_validate(extract_json(content))
    except ValidationError as exc:
        raise AppError("AI_BAD_RESPONSE", error_message, 502, True) from exc


def _validation_error_paths(exc: AppError) -> List[str]:
    cause = exc.__cause__
    if not isinstance(cause, ValidationError):
        return []
    paths: List[str] = []
    for item in cause.errors()[:20]:
        location = ".".join(str(part) for part in item.get("loc", ()))
        message = str(item.get("msg", "校验失败"))
        paths.append("{}: {}".format(location or "$", message))
    return paths


async def parse_or_repair_structured_message(
    *,
    api_key: str,
    message: Dict[str, Any],
    response_model: Type[BaseModel],
    schema_name: str,
    error_message: str,
    max_completion_tokens: int,
) -> BaseModel:
    error_paths: List[str] = []
    try:
        return parse_structured_message(
            message,
            response_model,
            error_message,
        )
    except AppError as first_error:
        if first_error.code != "AI_BAD_RESPONSE":
            raise
        error_paths = _validation_error_paths(first_error)

    raw = message.get("content", "")
    if not isinstance(raw, str):
        raw = ""
    repair_message = await chat_completion(
        api_key,
        [
            {
                "role": "system",
                "content": (
                    "只修复 JSON 字段、类型和层级；不得改变菜名、"
                    "食材、克数、步骤或含义。"
                ),
            },
            {
                "role": "user",
                "content": build_format_repair_prompt(
                    raw=raw,
                    model=response_model,
                    error_paths=error_paths,
                ),
            },
        ],
        max_completion_tokens,
        reasoning_effort="low",
        response_model=response_model,
        schema_name="{}_format_repair".format(schema_name),
    )
    try:
        return parse_structured_message(
            repair_message,
            response_model,
            error_message,
        )
    except AppError as second_error:
        raise AppError(
            "AI_SCHEMA_MISMATCH",
            error_message,
            502,
            True,
        ) from second_error


async def recognize_ingredients(
    image_data_url: str, api_key: str
) -> RecognizeModelResult:
    from .prompts import recognition_user_prompt

    validate_image_data_url(image_data_url)

    message = await chat_completion(
        api_key,
        [
            {
                "role": "system",
                "content": load_skill("ingredient-vision"),
            },
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                    {"type": "text", "text": recognition_user_prompt()},
                ],
            }
        ],
        2500,
        response_model=RecognizeModelResult,
        schema_name="recognized_ingredients",
    )
    return await parse_or_repair_structured_message(
        api_key=api_key,
        message=message,
        response_model=RecognizeModelResult,
        schema_name="recognized_ingredients",
        error_message="食材已经看到了，但识别结果不完整，请重试。",
        max_completion_tokens=2500,
    )
