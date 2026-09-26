"""门到门配送接口：维护配送任务，覆盖开始配送、完成签收等动作。

待配送、配送中、已签收三段数据分开存放；登记（含补录）时配送站点为空
会被阻断并说明原因，被阻断的任务编号会一并在响应里列出来。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.door import DoorService

router = APIRouter(prefix="/api/door", tags=["门到门配送"])

service = DoorService()

LIST_FIELDS = ["任务编号", "关联调度", "配送站点", "配送地址", "配送人员", "计划时段", "签收方式", "签收日期", "配送状态"]
STATUSES = ["待配送", "配送中", "已签收"]


class DoorBatchPayload(BaseModel):
    """批量登记/补录：每行是一条配送任务，被阻断的行带原因返回，可单独重试。"""

    rows: list[dict[str, Any]] = Field(default_factory=list)


def _blocked_message(blocked: list[dict[str, Any]]) -> str:
    """把被阻断的任务编号和原因一并列出来。"""
    detail = "；".join(f"{item['任务编号']}（{item['reason']}）" for item in blocked)
    return f"以下任务编号被阻断：{detail}"


@router.get("/summary")
def summary() -> dict[str, int]:
    """三段进度各自的数量：列表页、详情页、签收弹窗共用这一套口径。"""
    return service.summary()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出门到门配送清单：返回三段合起来的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "door", "total": total, "items": items}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按任务编号检索"),
    status: str | None = Query(default=None, description="待配送、配送中、已签收"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按任务编号与进度过滤门到门配送列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条配送任务明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"配送任务 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条配送任务，缺字段或任务编号重复时说明原因而不是静默丢弃。"""
    created, blocked = service.create_entries([payload.values])
    if blocked:
        return ActionResult(ok=False, message=_blocked_message(blocked))
    return ActionResult(ok=True, message="配送任务已登记", entry=created[0])


@router.post("/batch")
def create_batch(payload: DoorBatchPayload) -> dict[str, Any]:
    """批量登记/补录：成功的立即写入，被阻断的带任务编号与原因返回，前端可只重试失败行。"""
    if not payload.rows:
        return {"ok": False, "message": "没有需要登记的配送任务", "created": [], "blocked": []}
    created, blocked = service.create_entries(payload.rows)
    if blocked:
        message = _blocked_message(blocked)
        if created:
            message = f"已登记 {len(created)} 条；{message}"
    else:
        message = f"已登记 {len(created)} 条配送任务"
    return {"ok": not blocked, "message": message, "created": created, "blocked": blocked}


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条配送任务执行开始配送、完成签收；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
