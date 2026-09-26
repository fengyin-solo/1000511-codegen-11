"""分路不良复核测试概览接口：待复核/待补录台账、复测结论与补录动作。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.track_review import CONCLUSIONS, TrackReviewService

router = APIRouter(prefix="/api/track-reviews", tags=["分路不良复核"])

service = TrackReviewService()

GROUPS = ["pending", "missing", "ledger"]


@router.get("/stats")
def review_stats() -> dict[str, int]:
    """复核前后分路不良量等统计，复核提交后随台账一起变化。"""
    return service.stats()


@router.get("", response_model=PageResult[dict])
def list_reviews(
    group: str = Query(default="pending", description="pending=待复核、missing=待补录、ledger=复核台账"),
    keyword: str | None = Query(default=None, description="按设备编号或所属区段检索"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """待复核按分路灵敏度与制式类型排列；缺分路灵敏度的设备归入待补录。"""
    if group not in GROUPS:
        raise HTTPException(status_code=400, detail=f"分组只支持：{'、'.join(GROUPS)}")
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(group=group, keyword=keyword, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/{entry_id}/recheck", response_model=ActionResult)
def submit_recheck(entry_id: int, payload: EntryPayload) -> ActionResult:
    """提交复测结论；同一设备重复复核只保留最新一次，校验不通过时逐字段标出并允许重试。"""
    entry, message, errors = service.recheck(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message, entry={"errors": errors} if errors else None)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/supplement", response_model=ActionResult)
def submit_supplement(entry_id: int, payload: EntryPayload) -> ActionResult:
    """补录分路灵敏度：补录后该设备从待补录转入待复核。"""
    entry, message, errors = service.supplement(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message, entry={"errors": errors} if errors else None)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/conclusions")
def list_conclusions() -> dict[str, list[str]]:
    """允许的复测结论取值，供前端下拉直接渲染。"""
    return {"items": list(CONCLUSIONS)}
