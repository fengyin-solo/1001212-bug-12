"""门到门配送接口：维护配送任务，覆盖开始配送、登记签收与批量签收。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, BatchPayload, EntryPayload, PageResult
from app.services.door import STAGES, DoorService

router = APIRouter(prefix="/api/door", tags=["门到门配送"])

service = DoorService()


@router.get("/summary")
def summary() -> dict[str, int]:
    """待配送、配送中、已签收三段各自的记录数。"""
    return service.summary()


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按任务编号检索"),
    status: str | None = Query(default=None, description="待配送、配送中、已签收"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按任务编号与状态过滤门到门配送列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status and status not in STAGES:
        raise HTTPException(status_code=400, detail=f"状态只能是：{'、'.join(STAGES)}")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出门到门配送清单：返回三段合并后的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "door", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条配送任务明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"配送任务 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条配送任务；缺字段或任务编号重复时说明原因，历史记录不会被覆盖。"""
    entry, reason = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=reason)
    return ActionResult(ok=True, message="配送任务已登记", entry=entry)


@router.put("/{entry_id}", response_model=ActionResult)
def update_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """复核/修正配送信息；已签收的任务不允许再改签收日期。"""
    entry, message = service.update_entry(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条配送任务执行开始配送、登记签收；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/batch-signoff")
def batch_signoff(payload: BatchPayload) -> dict[str, Any]:
    """批量登记签收：逐条独立处理，被阻断的任务编号连同原因一并返回，可只重试这些条目。"""
    if not payload.items:
        return {"ok": False, "message": "没有需要签收的条目", "signed": [], "blocked": []}
    signed, blocked = service.batch_signoff(payload.items)
    if blocked:
        codes = "、".join(str(item["任务编号"]) for item in blocked)
        message = f"{len(signed)} 条已签收，{len(blocked)} 条被阻断：{codes}"
    else:
        message = f"{len(signed)} 条已全部签收"
    return {"ok": not blocked, "message": message, "signed": signed, "blocked": blocked}
