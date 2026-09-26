"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。

门到门配送这类需要分段存放的模块，用「模块#阶段」作为子表名登记
（如 door#待配送、door#配送中、door#已签收），查询与概览统计时再归并回
主模块，保证各模块看板口径不变。
"""
from __future__ import annotations

from typing import Any

from app.seed import SEED_ROWS


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }

    @staticmethod
    def _base(name: str) -> str:
        """子表名归并到主模块：door#待配送 -> door。"""
        return name.split("#", 1)[0]

    def module_names(self) -> list[str]:
        return sorted({self._base(name) for name in self._tables})

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def stage_rows(self, module: str, stage: str) -> list[dict[str, Any]]:
        """按阶段拆开的子表：不同阶段的记录物理上分开存放，互不串写。"""
        return self._tables.setdefault(f"{module}#{stage}", [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for name, rows in self._tables.items():
            if self._base(name) != module:
                continue
            for row in rows:
                if int(row.get("id", 0)) == entry_id:
                    return row
        return None

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = [
                row
                for table, entries in self._tables.items()
                if self._base(table) == name
                for row in entries
            ]
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
