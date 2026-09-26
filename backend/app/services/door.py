"""门到门配送业务规则：状态流转、字段校验与筛选口径都收在这里。

待配送、配送中、已签收三段数据分开存放（store 里的 door#阶段 子表）：
- 签收方式、签收日期只会在「完成签收」时写进对应任务编号自己的记录，
  已签收的记录不允许再改签收日期；
- 新增（含补录）只往「待配送」段追加，任务编号重复直接阻断，
  历史配送记录不会被覆盖。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "door"
STAGES = ["待配送", "配送中", "已签收"]
REQUIRED_FIELDS = ["任务编号", "关联调度", "配送站点"]
PROFILE_FIELDS = ["任务编号", "关联调度", "配送站点", "配送地址", "配送人员", "计划时段"]
SIGN_FIELDS = ["签收方式", "签收日期"]
ACTIONS = ["开始配送", "完成签收"]


class DoorService:
    # ------------------------------------------------------------------
    # 分段存放：每条记录只存在于自己阶段对应的子表里
    # ------------------------------------------------------------------
    def _bucket(self, stage: str) -> list[dict[str, Any]]:
        return store.stage_rows(MODULE, stage)

    def _all_rows(self) -> list[dict[str, Any]]:
        return [row for stage in STAGES for row in self._bucket(stage)]

    def _locate(self, entry_id: int) -> tuple[str | None, dict[str, Any] | None]:
        for stage in STAGES:
            for row in self._bucket(stage):
                if int(row.get("id", 0)) == entry_id:
                    return stage, row
        return None, None

    def _move(self, entry: dict[str, Any], source: str, target: str) -> None:
        """把记录从当前阶段搬到目标阶段，三段数据因此始终保持分开存放。"""
        self._bucket(source).remove(entry)
        entry["status"] = target
        entry["配送状态"] = target
        entry["pending"] = target != STAGES[-1]
        self._bucket(target).append(entry)

    # ------------------------------------------------------------------
    # 查询：列表、详情、三段进度统计共用同一份数据，口径一致
    # ------------------------------------------------------------------
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = list(self._bucket(status)) if status in STAGES else self._all_rows()
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("任务编号", ""))]
        rows = sorted(rows, key=lambda row: int(row.get("id", 0)))
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def summary(self) -> dict[str, int]:
        """三段各自的数量：列表页、详情页、签收弹窗看到的进度都以这里为准。"""
        return {stage: len(self._bucket(stage)) for stage in STAGES}

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    # ------------------------------------------------------------------
    # 登记 / 补录：逐条校验，被阻断的带任务编号和原因返回，可单独重试
    # ------------------------------------------------------------------
    def create_entries(
        self, items: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        created: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        existing = {str(row.get("任务编号", "")).strip() for row in self._all_rows()}
        next_id = max((int(row.get("id", 0)) for row in self._all_rows()), default=0) + 1
        for index, raw in enumerate(items):
            task_no = str(raw.get("任务编号") or "").strip()
            missing = [field for field in REQUIRED_FIELDS if not str(raw.get(field) or "").strip()]
            if missing:
                blocked.append({
                    "index": index,
                    "任务编号": task_no or "（未填写任务编号）",
                    "reason": f"{'、'.join(missing)}为空，不允许提交",
                })
                continue
            if task_no in existing:
                blocked.append({
                    "index": index,
                    "任务编号": task_no,
                    "reason": "任务编号已存在，为避免覆盖历史配送记录，本条未写入",
                })
                continue
            entry: dict[str, Any] = {"id": next_id}
            next_id += 1
            for field in PROFILE_FIELDS:
                entry[field] = str(raw.get(field) or "").strip()
            entry["签收方式"] = ""
            entry["签收日期"] = ""
            entry["status"] = STAGES[0]
            entry["配送状态"] = STAGES[0]
            entry["pending"] = True
            entry["abnormal"] = False
            self._bucket(STAGES[0]).append(entry)
            existing.add(task_no)
            created.append(entry)
        return created, blocked

    # ------------------------------------------------------------------
    # 状态流转：开始配送、完成签收
    # ------------------------------------------------------------------
    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        stage, entry = self._locate(entry_id)
        if entry is None:
            return None, f"配送任务 {entry_id} 不存在或已归档"
        task_no = str(entry.get("任务编号", ""))

        if action == "开始配送":
            if stage != STAGES[0]:
                return None, f"任务 {task_no} 当前为「{stage}」，只有待配送任务才能开始配送"
            self._move(entry, STAGES[0], STAGES[1])
            return entry, f"任务 {task_no} 已开始配送"

        if action == "完成签收":
            if stage == STAGES[2]:
                return None, f"任务 {task_no} 已签收，签收日期不允许再修改"
            if stage != STAGES[1]:
                return None, f"任务 {task_no} 仍是待配送，需先开始配送再登记签收"
            payload_no = str(values.get("任务编号") or "").strip()
            if payload_no and payload_no != task_no:
                return None, (
                    f"签收信息属于任务 {payload_no}，与当前任务 {task_no} 不一致，"
                    "已拦截，签收日期只能落在对应的任务编号上"
                )
            missing = [field for field in SIGN_FIELDS if not str(values.get(field) or "").strip()]
            if missing:
                return None, f"签收登记缺少：{'、'.join(missing)}"
            entry["签收方式"] = str(values["签收方式"]).strip()
            entry["签收日期"] = str(values["签收日期"]).strip()
            self._move(entry, STAGES[1], STAGES[2])
            return entry, f"任务 {task_no} 已完成签收，签收日期 {entry['签收日期']}"

        return None, f"动作「{action}」不属于门到门配送可执行范围"
