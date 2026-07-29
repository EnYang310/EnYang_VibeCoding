import asyncio
import logging
from typing import Callable, List, Optional, Tuple

from .audit import normalize_plan_inventory
from .channels import (
    build_initial_channel_drafts,
    calculate_channel_plan,
)
from .kimi import (
    AppError,
    chat_completion,
    parse_or_repair_structured_message,
)
from .models import (
    AgentTraceStep,
    GeneratePlanRequest,
    MealPlan,
    MealPlanDraft,
    PlanAuditResult,
)
from .prompts import (
    build_audit_messages,
    build_plan_messages,
    build_plan_repair_messages,
)
from .skills import skill_versions


logger = logging.getLogger("uvicorn.error")
ProgressCallback = Callable[[str, str], None]
MAX_PLAN_CANDIDATES = 3


def _trace(
    step_id: str,
    skill: str,
    title: str,
    detail: str,
    status: str = "completed",
) -> AgentTraceStep:
    return AgentTraceStep(
        id=step_id,
        skill=skill,
        title=title,
        detail=detail,
        status=status,
    )


async def _generate_plan_draft(
    request: GeneratePlanRequest,
    api_key: str,
) -> MealPlanDraft:
    message = await chat_completion(
        api_key,
        build_plan_messages(request),
        5200,
        reasoning_effort="low",
        response_model=MealPlanDraft,
        schema_name="meal_plan",
    )
    parsed = await parse_or_repair_structured_message(
        api_key=api_key,
        message=message,
        response_model=MealPlanDraft,
        schema_name="meal_plan",
        error_message="菜谱已经想好了，但结构不完整，请重新生成。",
        max_completion_tokens=5200,
    )
    return MealPlanDraft.model_validate(parsed)


async def _repair_plan(
    api_key: str,
    draft: MealPlanDraft,
    request: GeneratePlanRequest,
    violations: List[str],
) -> MealPlanDraft:
    message = await chat_completion(
        api_key,
        build_plan_repair_messages(request, draft, violations),
        5200,
        reasoning_effort="low",
        response_model=MealPlanDraft,
        schema_name="repaired_meal_plan",
    )
    parsed = await parse_or_repair_structured_message(
        api_key=api_key,
        message=message,
        response_model=MealPlanDraft,
        schema_name="repaired_meal_plan",
        error_message="菜单修复结果不完整，请重新生成。",
        max_completion_tokens=5200,
    )
    return MealPlanDraft.model_validate(parsed)


async def _run_llm_audit(
    api_key: str,
    draft: MealPlanDraft,
    request: GeneratePlanRequest,
) -> PlanAuditResult:
    message = await chat_completion(
        api_key,
        build_audit_messages(draft, request),
        500,
        reasoning_effort="low",
        response_model=PlanAuditResult,
        schema_name="plan_audit",
    )
    parsed = await parse_or_repair_structured_message(
        api_key=api_key,
        message=message,
        response_model=PlanAuditResult,
        schema_name="plan_audit",
        error_message="菜单合格检查结果不完整。",
        max_completion_tokens=500,
    )
    return PlanAuditResult.model_validate(parsed)


async def _build_delivery_plan(
    *,
    draft: MealPlanDraft,
    request: GeneratePlanRequest,
) -> MealPlan:
    channels = await build_initial_channel_drafts(
        draft=draft,
        source=request,
    )
    return await calculate_channel_plan(
        draft=draft,
        channels=channels,
        people=request.people,
        versions=skill_versions(),
    )


async def run_plan_pipeline(
    request: GeneratePlanRequest,
    api_key: str,
    progress: Optional[ProgressCallback] = None,
) -> MealPlan:
    report = progress or (lambda _phase, _message: None)
    trace: List[AgentTraceStep] = [
        _trace(
            "skills-loaded",
            "meal-planning",
            "装载精简规划 Skill",
            "只发送当前步骤必需规则和固定字段骨架。",
        )
    ]
    report("drafting", "耄耋正在设计完整菜品…")
    draft = await _generate_plan_draft(request, api_key)

    for candidate_index in range(MAX_PLAN_CANDIDATES):
        draft = normalize_plan_inventory(draft, request)
        report("checking", "耄耋正在做宽松合格审核并核算热量…")
        delivery_task = asyncio.create_task(
            _build_delivery_plan(
                draft=draft,
                request=request,
            )
        )
        audit_task = asyncio.create_task(
            _run_llm_audit(api_key, draft, request)
        )
        try:
            audit = await audit_task
        except BaseException:
            delivery_task.cancel()
            audit_task.cancel()
            await asyncio.gather(
                delivery_task,
                audit_task,
                return_exceptions=True,
            )
            raise

        violations = list(dict.fromkeys(audit.violations))
        if not audit.passed or violations:
            delivery_task.cancel()
            await asyncio.gather(delivery_task, return_exceptions=True)
            if candidate_index == MAX_PLAN_CANDIDATES - 1:
                raise AppError(
                    "PLAN_AUDIT_FAILED",
                    "菜单连续宽松审核后仍有明确基础错误，请重新生成。",
                    502,
                    True,
                )
            repair_items = violations or [audit.summary]
            report(
                "repairing",
                "发现 {} 项明确基础问题，耄耋正在定点修复…".format(
                    len(repair_items)
                ),
            )
            draft = await _repair_plan(
                api_key,
                draft,
                request,
                repair_items,
            )
            trace.append(
                _trace(
                    "plan-repair-{}".format(candidate_index + 1),
                    "plan-audit",
                    "完成第 {} 次定点修复".format(candidate_index + 1),
                    "只修复宽松 LLM 审核确认的基础问题。",
                    "repaired",
                )
            )
            continue

        try:
            plan = await delivery_task
        except BaseException:
            delivery_task.cancel()
            await asyncio.gather(delivery_task, return_exceptions=True)
            raise

        trace.extend(
            [
                _trace(
                    "channels-ready",
                    "meal-planning",
                    "每道菜已锁定独立食材预算",
                    "换菜时始终使用这个菜位最初分配的固定预算。",
                ),
                _trace(
                    "nutrition-grounded",
                    "nutrition-grounding",
                    "完成热量来源回填",
                    "优先使用随应用部署的 USDA 本地知识库，未命中项明确标记估算。",
                    "warning" if plan.warnings else "completed",
                ),
                _trace(
                    "audit-advisory",
                    "plan-audit",
                    "宽松最低合格审核完成",
                    audit.summary,
                ),
            ]
        )
        return plan.model_copy(
            update={
                "agentTrace": trace,
                "skillVersions": skill_versions(),
            }
        )

    raise AppError(
        "PLAN_AUDIT_FAILED",
        "菜单没有通过基础检查，请重新生成。",
        502,
        True,
    )
