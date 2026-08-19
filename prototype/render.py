"""課表輸出：班級視角 / 教師視角 / 教室視角。

三種視角是同一份 Placement 資料的三種投影 —— 這也是實際系統 UI 的核心，
教務組長改課表時看班級視角，老師看自己的，場地組看專科教室的使用率。
"""

from __future__ import annotations

from model import School
from solver import Placement, Solution

DAY_NAMES = ["一", "二", "三", "四", "五", "六", "日"]


def _empty_table(school: School) -> list[list[str]]:
    g = school.grid
    return [["" for _ in range(g.days)] for _ in range(g.periods)]


def _print_table(title: str, table: list[list[str]], school: School) -> None:
    g = school.grid
    width = max(10, max((len(c) for row in table for c in row), default=8) + 2)
    print(f"\n### {title}")
    header = "節次".ljust(6) + "".join(f"週{DAY_NAMES[d]}".ljust(width) for d in range(g.days))
    print(header)
    print("-" * len(header))
    for p in range(g.periods):
        line = f"第{p + 1}節".ljust(6)
        for d in range(g.days):
            line += (table[p][d] or "·").ljust(width)
        print(line)


def _fill(table, school, placements, cell_fn) -> None:
    g = school.grid
    for pl in placements:
        for s in pl.slots():
            table[g.period_of(s) - 1][g.day_of(s) - 1] = cell_fn(pl)


def class_view(school: School, sol: Solution, class_id: str) -> None:
    pls = [p for p in sol.placements if p.unit.class_id == class_id]
    table = _empty_table(school)
    _fill(table, school, pls, lambda p: (
        f"{school.subjects[p.unit.subject_id].name}"
        f"{'*' if p.unit.length == 2 else ''}"
    ))
    _print_table(f"班級課表 — {school.classes[class_id].name}（* = 連堂）", table, school)


def teacher_view(school: School, sol: Solution, teacher_id: str) -> None:
    pls = [p for p in sol.placements if p.unit.teacher_id == teacher_id]
    table = _empty_table(school)
    _fill(table, school, pls, lambda p: (
        f"{school.classes[p.unit.class_id].id}{school.subjects[p.unit.subject_id].name}"
    ))
    t = school.teachers[teacher_id]
    _print_table(f"教師課表 — {t.name}（共 {len(pls)} 個時段）", table, school)


def room_view(school: School, sol: Solution, room_id: str) -> None:
    pls = [p for p in sol.placements if p.room_id == room_id]
    table = _empty_table(school)
    _fill(table, school, pls, lambda p: school.classes[p.unit.class_id].id)
    r = school.rooms[room_id]
    _print_table(f"教室使用 — {r.name}", table, school)


def summary(school: School, sol: Solution) -> None:
    g = school.grid
    print("\n=== 求解結果 ===")
    print(f"狀態      : {sol.status}")
    print(f"耗時      : {sol.wall_time:.2f}s")
    print(f"已排時段  : {sum(p.unit.length for p in sol.placements)}")
    print(f"總懲罰成本: {sol.penalty}")
    if sol.violations:
        print("\n未能完全滿足的軟性需求：")
        for v in sol.violations:
            print(f"  - {v}")
    else:
        print("\n所有軟性需求都已滿足。")

    # 驗證三大硬約束確實沒有被違反
    print("\n--- 硬約束驗證 ---")
    for label, key in (("班級", lambda p: p.unit.class_id),
                       ("教師", lambda p: p.unit.teacher_id),
                       ("教室", lambda p: p.room_id)):
        seen: dict[tuple, str] = {}
        clashes = 0
        for pl in sol.placements:
            for s in pl.slots():
                k = (key(pl), s)
                if k in seen:
                    clashes += 1
                seen[k] = pl.unit.subject_id
        print(f"{label}衝堂：{clashes} 件")

    # 節數守恆
    got: dict[tuple[str, str], int] = {}
    for pl in sol.placements:
        k = (pl.unit.class_id, pl.unit.subject_id)
        got[k] = got.get(k, 0) + pl.unit.length
    bad = [
        f"{r.class_id}/{r.subject_id} 應 {r.periods} 實 {got.get((r.class_id, r.subject_id), 0)}"
        for r in school.requirements
        if got.get((r.class_id, r.subject_id), 0) != r.periods
    ]
    print(f"節數不符：{len(bad)} 件" + ("  " + "; ".join(bad) if bad else ""))

    # 班級不得有課排進封鎖時段
    illegal = sum(
        1 for pl in sol.placements for s in pl.slots()
        if s in school.classes[pl.unit.class_id].blocked
    )
    print(f"排進不上課時段：{illegal} 件")
