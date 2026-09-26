"""分路不良复核测试概览接口：待复核/待补录/台账三个口径与复核、补录动作。"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.track_review import TrackReviewService

router = APIRouter(prefix="/api/track/review", tags=["分路不良复核"])

service = TrackReviewService()

SCOPES = {
    "pending": "待复核",
    "backfill": "待补录",
    "ledger": "复核台账",
}


@router.get("/overview")
def review_overview(
    scope: str = Query(default="pending", description="pending 待复核 / backfill 待补录 / ledger 台账"),
    keyword: str | None = Query(default=None, description="按设备编号或所属区段检索"),
    system: str | None = Query(default=None, description="按制式类型检索"),
) -> dict[str, object]:
    """概览首屏：分路不良统计与当前口径明细一次返回，明细随统计口径联动。"""
    if scope not in SCOPES:
        scope = "pending"
    items, total = service.list_overview(scope=scope, keyword=keyword, system=system)
    return {
        "scope": scope,
        "scopeLabel": SCOPES[scope],
        "stats": service.stats(),
        "items": items,
        "total": total,
    }


@router.post("/{entry_id}/submit", response_model=ActionResult)
def submit_review(entry_id: int, payload: EntryPayload) -> ActionResult:
    """提交复核结论；校验不过时在 errors 里逐字段标出，允许修正后重试。"""
    entry, message, errors, stats = service.submit_review(entry_id, payload.values)
    if errors:
        return ActionResult(ok=False, message=message, errors=errors, stats=stats)
    if entry is None:
        return ActionResult(ok=False, message=message, stats=stats)
    return ActionResult(ok=True, message=message, entry=entry, stats=stats)


@router.post("/{entry_id}/backfill", response_model=ActionResult)
def backfill_sensitivity(entry_id: int, payload: EntryPayload) -> ActionResult:
    """补录分路灵敏度；补录成功的设备从待补录移到待复核。"""
    entry, message, errors = service.backfill_sensitivity(entry_id, payload.values)
    if errors:
        return ActionResult(ok=False, message=message, errors=errors)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
