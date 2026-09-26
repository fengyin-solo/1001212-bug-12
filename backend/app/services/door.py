"""门到门配送业务规则：三段分存、签收登记与字段校验都收在这里。

存储约定：待配送、配送中、已签收三段数据分开存放，状态流转时整条记录在段之间移动，
每条记录只存在于一个段里，段名就是进度，避免“记录写着已签收、进度还挂在配送中”。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "door"
STAGES = ["待配送", "配送中", "已签收"]
REQUIRED_FIELDS = ["任务编号", "关联调度", "配送站点"]
INFO_FIELDS = ["关联调度", "配送站点", "配送地址", "配送人员", "计划时段"]
SIGN_FIELDS = ["签收方式", "签收日期"]
ACTION_RULES = {"开始配送": ("待配送", "配送中"), "登记签收": ("配送中", "已签收")}
# 旧数据里出现过的状态统一归并进三段：已送达但尚未签收的并入配送中
LEGACY_STAGE_MAP = {"已送达": "配送中"}


class DoorService:
    def __init__(self) -> None:
        self._partitioned = False

    # ---- 存储：三段分存 ----
    def _ensure_partitioned(self) -> None:
        """把扁平表里的存量记录按状态搬进三段，只搬一次。"""
        if self._partitioned:
            return
        legacy = store.rows(MODULE)
        for row in legacy:
            stage = LEGACY_STAGE_MAP.get(str(row.get("status") or ""), str(row.get("status") or ""))
            if stage not in STAGES:
                stage = STAGES[0]
            self._place(row, stage)
        legacy.clear()
        self._partitioned = True

    def _place(self, entry: dict[str, Any], stage: str) -> None:
        """把记录放进指定段，并让记录上的进度字段与段名保持一致。"""
        entry["status"] = stage
        entry["配送状态"] = stage
        entry["pending"] = stage != STAGES[-1]
        entry.setdefault("abnormal", False)
        store.segment_rows(MODULE, stage).append(entry)

    def _move(self, entry: dict[str, Any], source: str, target: str) -> None:
        store.segment_rows(MODULE, source).remove(entry)
        self._place(entry, target)

    def _all(self) -> list[dict[str, Any]]:
        self._ensure_partitioned()
        merged: list[dict[str, Any]] = []
        for stage in STAGES:
            merged.extend(store.segment_rows(MODULE, stage))
        return merged

    def _find(self, entry_id: int) -> dict[str, Any] | None:
        for row in self._all():
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def _find_by_code(self, code: str) -> dict[str, Any] | None:
        for row in self._all():
            if str(row.get("任务编号") or "") == code:
                return row
        return None

    # ---- 查询 ----
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._all()
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("任务编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def summary(self) -> dict[str, int]:
        """三段各自的记录数，给列表页的统计卡片用。"""
        self._ensure_partitioned()
        return {stage: len(store.segment_rows(MODULE, stage)) for stage in STAGES}

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return self._find(entry_id)

    # ---- 登记与修正 ----
    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """登记一条配送任务；只追加新记录，不改动任何历史记录。"""
        self._ensure_partitioned()
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            reason = f"缺少必填字段：{'、'.join(missing)}"
            if "配送站点" in missing:
                reason += "；配送站点为空时无法确定交付节点，不允许提交，请先补全站点"
            return None, reason
        code = str(values.get("任务编号") or "").strip()
        if self._find_by_code(code) is not None:
            return None, f"任务编号 {code} 已存在，为避免覆盖历史配送记录，本次登记未写入"
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in self._all()), default=0) + 1}
        entry["任务编号"] = code
        for field in INFO_FIELDS:
            entry[field] = values.get(field)
        entry["签收方式"] = None
        entry["签收日期"] = None
        entry["abnormal"] = False
        self._place(entry, STAGES[0])
        return entry, ""

    def update_entry(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """复核/修正配送信息：只合并可改字段，签收日期一旦写入就留在原任务编号上。"""
        entry = self._find(entry_id)
        if entry is None:
            return None, f"配送任务 {entry_id} 不存在或已归档"
        if entry.get("status") == STAGES[-1]:
            for field in SIGN_FIELDS:
                incoming = values.get(field)
                if incoming is not None and str(incoming) != str(entry.get(field)):
                    return None, f"配送任务 {entry.get('任务编号')} 已签收，不允许再改签收日期"
        station = values.get("配送站点")
        if station is not None and not str(station).strip():
            return None, "配送站点为空时无法确定交付节点，不允许提交，请先补全站点"
        for field in INFO_FIELDS:
            if field in values and values[field] is not None:
                entry[field] = values[field]
        return entry, "配送任务已复核保存"

    # ---- 状态流转 ----
    def run_action(self, entry_id: int, action: str, values: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str]:
        entry = self._find(entry_id)
        if entry is None:
            return None, f"配送任务 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于门到门配送可执行范围"
        source, target = ACTION_RULES[action]
        current = str(entry.get("status") or "")
        code = str(entry.get("任务编号") or entry_id)
        if action == "登记签收" and current == STAGES[-1]:
            return None, f"配送任务 {code} 已签收，不允许再改签收日期"
        if current != source:
            return None, f"配送任务 {code} 当前处于「{current}」，不能执行「{action}」"
        values = values or {}
        if action == "登记签收":
            if not str(entry.get("配送站点") or "").strip():
                return None, f"配送任务 {code} 的配送站点为空，无法确定交付节点，签收登记未提交"
            method = str(values.get("签收方式") or "").strip()
            sign_date = str(values.get("签收日期") or "").strip()
            if not method:
                return None, f"配送任务 {code} 未填写签收方式，签收登记未提交"
            if not sign_date:
                return None, f"配送任务 {code} 未填写签收日期，签收登记未提交"
            # 签收信息只写进当前这条记录，签收日期跟着任务编号走
            entry["签收方式"] = method
            entry["签收日期"] = sign_date
        self._move(entry, source, target)
        return entry, f"配送任务 {code} 已{action}"

    # ---- 批量签收 ----
    def batch_signoff(self, items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """批量登记签收：逐条独立校验、独立落库，被阻断的连任务编号带原因一起列出。"""
        signed: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        for item in items:
            code = str(item.get("任务编号") or "").strip()
            if not code:
                blocked.append({"任务编号": "（未填写）", "原因": "任务编号为空，签收日期没有落点"})
                continue
            entry = self._find_by_code(code)
            if entry is None:
                blocked.append({"任务编号": code, "原因": "任务编号不存在，签收日期没有落点"})
                continue
            updated, message = self.run_action(int(entry["id"]), "登记签收", item)
            if updated is None:
                blocked.append({"任务编号": code, "原因": message})
            else:
                signed.append({"任务编号": code, "签收日期": updated.get("签收日期")})
        return signed, blocked
