"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

from typing import Any

from app.seed import SEED_ROWS


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }
        # 需要按阶段分开存放的模块（如门到门配送）把记录放进各自的分段里
        self._segments: dict[str, dict[str, list[dict[str, Any]]]] = {}

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def segment_rows(self, module: str, segment: str) -> list[dict[str, Any]]:
        """取分段模块里的某一段；段不存在时给一份空列表，方便直接追加。"""
        return self._segments.setdefault(module, {}).setdefault(segment, [])

    def all_rows(self, module: str) -> list[dict[str, Any]]:
        """分段模块合并各段记录；未分段的模块返回原表。"""
        if module in self._segments:
            merged: list[dict[str, Any]] = []
            for segment in self._segments[module].values():
                merged.extend(segment)
            return merged
        return self.rows(module)

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.all_rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.all_rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
