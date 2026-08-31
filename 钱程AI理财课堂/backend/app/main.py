import asyncio
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.course_data import list_courses
from app.interaction_tools import next_unit_after, present_interaction_card
from app.learning_gates import infer_observed_criteria, passes_gate
from app.lesson_chat import personalized_lesson_chat
from app.lesson_runtime import COURSE_FOCUS, get_lesson
from app.rate_limit import SlidingWindowLimiter
from app.request_lifecycle import ClientDisconnected, await_while_connected
from app.schemas import ChatRequest, ChatResponse, InteractionCardRequest, InteractionCardResponse, InteractionTurnRequest, InteractionTurnResponse, VoiceSynthesisRequest, VoiceSynthesisResponse
from app.teaching_flow import should_present_next_card
from app.voice import TencentVoiceService, VoiceUnavailableError


ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")
FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", str(ROOT_DIR / "client" / "dist" / "h5")))
VOICE_CACHE_DIR = Path(os.getenv("VOICE_CACHE_DIR", str(ROOT_DIR / "data" / "voice-cache")))

app = FastAPI(title="钱程 · 理财第一课", version="1.0.0")
logger = logging.getLogger(__name__)
chat_limiter = SlidingWindowLimiter(limit=int(os.getenv("CHAT_RATE_LIMIT_PER_MINUTE", "30")), window_seconds=60)
voice_limiter = SlidingWindowLimiter(limit=int(os.getenv("VOICE_RATE_LIMIT_PER_MINUTE", "20")), window_seconds=60)
voice_service = TencentVoiceService(VOICE_CACHE_DIR)
allowed_origins = [item.strip() for item in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:10086,http://127.0.0.1:10086").split(",") if item.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


def gate_checked_response(response: ChatResponse, *, unit_id: str, learner_text: str) -> ChatResponse:
    if passes_gate(unit_id, response.teaching_decision, response.observed_criteria):
        return response
    inferred = infer_observed_criteria(unit_id, learner_text)
    if inferred:
        return response.model_copy(update={
            "teaching_decision": "advance",
            "advance_recommendation": "continue",
            "observed_criteria": inferred,
            "missing_criterion": None,
        })
    return response


@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    if request.method == "POST" and request.url.path == "/api/v1/lessons/chat":
        # A global per-instance budget cannot be bypassed with forged proxy
        # headers and provides a deterministic ceiling for the paid model API.
        if not chat_limiter.allow("paid-model-global", now=time.monotonic()):
            return JSONResponse(
                status_code=429,
                content={"detail": "老师正在处理很多问题，请稍后再试。"},
                headers={"Retry-After": "60"},
            )
    if request.method == "POST" and request.url.path == "/api/v1/voice/synthesize" and not voice_limiter.allow("tts-global", now=time.monotonic()):
        return JSONResponse(status_code=429, content={"detail": "朗读请求较多，请稍后再试。"}, headers={"Retry-After": "60"})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # H5 bundles have stable filenames. During local iteration, avoid the
    # browser keeping an older JS bundle that expects the pre-subtitle voice
    # response format.
    if request.url.path == "/" or request.url.path.endswith((".html", ".js", ".css")):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    return {"status": "ready"}


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/courses")
async def courses() -> dict[str, list[dict]]:
    return {"courses": list_courses()}


@app.get("/api/v1/courses/{course_id}")
async def course_detail(course_id: str) -> dict:
    lesson = get_lesson(course_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    return lesson


@app.post("/api/v1/lessons/chat", response_model=ChatResponse)
async def lesson_chat(request: ChatRequest, http_request: Request) -> ChatResponse:
    try:
        response = gate_checked_response(
            await await_while_connected(http_request, personalized_lesson_chat(request)), unit_id=request.unit_id, learner_text=request.message
        )
        # A card appears when the learner has completed the current card and
        # the teaching gate is actually met.  It is not keyed off wording such
        # as “continue” or “next”.
        gate_passed = passes_gate(request.unit_id, response.teaching_decision, response.observed_criteria)
        if (
            request.context.next_unit_id == next_unit_after(request.unit_id)
            and should_present_next_card(
                current_card_completed=request.context.current_card_completed,
                course_finished=request.context.course_finished or request.context.free_chat_mode,
                next_unit_id=request.context.next_unit_id,
                assistant_replies_since_card=request.context.assistant_replies_since_card,
                gate_passed=gate_passed,
            )
        ):
            response = response.model_copy(update={
                "tool_call": InteractionCardResponse(**present_interaction_card(request.course_id, request.context.next_unit_id))
            })
        return response
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="课程或回合不存在") from exc
    except ClientDisconnected as exc:
        raise HTTPException(status_code=499, detail="课程已离开，已取消本次讲解") from exc


@app.post("/api/v1/lessons/interaction-card", response_model=InteractionCardResponse)
async def interaction_card(request: InteractionCardRequest) -> InteractionCardResponse:
    if request.course_id not in COURSE_FOCUS:
        raise HTTPException(status_code=422, detail="课程或回合不存在")
    try:
        # This explicit call is the agent's presentation tool: the client never
        # invents a card on its own; it only renders this returned tool result.
        return InteractionCardResponse(**present_interaction_card(request.course_id, request.unit_id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="课程或回合不存在") from exc


@app.post("/api/v1/lessons/interaction-turn", response_model=InteractionTurnResponse)
async def interaction_turn(request: InteractionTurnRequest, http_request: Request) -> InteractionTurnResponse:
    if request.course_id not in COURSE_FOCUS:
        raise HTTPException(status_code=422, detail="课程或回合不存在")
    started_at = time.perf_counter()
    try:
        # Do not trust the client to skip cards. The tool may only present the
        # direct successor of the card whose work was just submitted.
        if request.next_unit_id != next_unit_after(request.unit_id):
            raise ValueError("invalid next unit")
        enriched = request.model_copy(
            update={
                "message": f"我完成了这张互动卡。我的回答是：{request.submitted_answer}",
                "context": request.context.model_copy(
                    update={
                        "answer_summaries": [*request.context.answer_summaries, f"本回合回答：{request.submitted_answer}"][-8:],
                        "current_card_completed": True,
                        "current_card_answer": request.submitted_answer,
                    }
                ),
            }
        )
        feedback = gate_checked_response(
            await await_while_connected(http_request, personalized_lesson_chat(enriched)), unit_id=request.unit_id, learner_text=request.submitted_answer
        )
        tool_call = None
        gate_passed = passes_gate(request.unit_id, feedback.teaching_decision, feedback.observed_criteria)
        if should_present_next_card(
            current_card_completed=True,
            course_finished=request.context.course_finished or request.context.free_chat_mode,
            next_unit_id=request.next_unit_id,
            assistant_replies_since_card=request.context.assistant_replies_since_card,
            gate_passed=gate_passed,
        ):
            tool_call = InteractionCardResponse(**present_interaction_card(request.course_id, request.next_unit_id))
        logger.info(
            "interaction_turn elapsed_ms=%s source=%s card_ready=%s",
            int((time.perf_counter() - started_at) * 1000),
            feedback.source,
            tool_call is not None,
        )
        return InteractionTurnResponse(assistant_reply=feedback, tool_call=tool_call)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="课程或回合不存在") from exc
    except ClientDisconnected as exc:
        raise HTTPException(status_code=499, detail="课程已离开，已取消本次讲解") from exc


@app.post("/api/v1/voice/synthesize", response_model=VoiceSynthesisResponse)
async def synthesize_voice(request: VoiceSynthesisRequest, http_request: Request) -> VoiceSynthesisResponse:
    try:
        # Tencent's SDK is synchronous.  Running it in the event loop made one
        # long narration block every chat/card request behind it.  Keep the
        # API async so a first-paragraph request can start playing while the
        # client fetches the remaining paragraphs in parallel.
        segments = await await_while_connected(
            http_request,
            asyncio.to_thread(voice_service.synthesize_paragraphs, request.paragraphs),
        )
        return VoiceSynthesisResponse(segments=segments)
    except VoiceUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ClientDisconnected as exc:
        raise HTTPException(status_code=499, detail="课程已离开，已取消本次朗读") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="朗读音频暂时生成失败") from exc


app.mount("/media/voice", StaticFiles(directory=str(VOICE_CACHE_DIR)), name="voice-cache")
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
