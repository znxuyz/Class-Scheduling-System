"""分階段排課：科任／行政先排，剩下的空格交給導師。

這是台灣國小實際的排課流程，也是模型上的正確拆法：

  Phase 1  科任 + 兼行政教師的課
           他們跨班跑、共用專科教室、有行政會議時段，是全校最稀缺的資源，
           衝突幾乎都發生在這裡。必須全校一起求解。

  Phase 2  導師的課
           導師只教自己班、只用原班教室，所以 **班與班之間完全解耦**：
           Phase 2 不是一個大問題，而是 N 個各自獨立的小問題。
           這正是「剩下來的給導師自己排」在數學上成立的原因。

關鍵風險：Phase 1 決定了留給導師的空格「形狀」。若 Phase 1 只顧科任老師方便，
可能把某個班的上午塞滿科任課，導師的國語數學就只能排下午。所以 Phase 1 的
目標式必須包含 RESERVE_MORNING / SPECIAL_BALANCE 這類「為下一階段著想」的項。
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from model import HANDOFF_KINDS, School, Unit
from solver import Placement, Scheduler, Solution


@dataclass
class PhasedResult:
    phase1: Solution
    phase2: dict[str, Solution]          # class_id -> 該班導師課的求解結果
    placements: list[Placement]
    failed_classes: list[str]


def split_units(school: School, units: list[Unit]) -> tuple[list[Unit], list[Unit]]:
    """依教師身分把待排單元切成兩階段。"""
    p1, p2 = [], []
    for u in units:
        role = school.teachers[u.teacher_id].role
        (p1 if role in ("special", "admin") else p2).append(u)
    return p1, p2


def leftover_report(school: School, phase1: list[Placement]) -> dict[str, dict]:
    """Phase 1 排完後，各班剩下什麼樣的空格給導師 —— 衡量交接品質。"""
    g = school.grid
    used: dict[str, set[int]] = {cid: set() for cid in school.classes}
    for pl in phase1:
        used[pl.unit.class_id].update(pl.slots())

    report = {}
    for cls in school.classes.values():
        free = [
            s for s in g.all_slots()
            if s not in cls.blocked and s not in used[cls.id]
        ]
        free_set = set(free)
        morning_free = [s for s in free if g.period_of(s) in g.morning]
        per_day = [
            len([s for s in free if g.day_of(s) == d]) for d in range(1, g.days + 1)
        ]
        doubles = sum(
            1 for s in free
            if g.can_start_double(s) and (s + 1) in free_set
        )
        # 導師實際需要的節數與主科節數
        need = sum(
            r.periods for r in school.requirements
            if r.class_id == cls.id
            and school.teachers[r.teacher_id].role == "homeroom"
        )
        core_need = sum(
            r.periods for r in school.requirements
            if r.class_id == cls.id
            and school.teachers[r.teacher_id].role == "homeroom"
            and school.subjects[r.subject_id].is_core
        )
        report[cls.id] = {
            "free": len(free),
            "need": need,
            "morning_free": len(morning_free),
            "core_need": core_need,
            "core_fits_morning": len(morning_free) >= core_need,
            "per_day": per_day,
            "day_spread": max(per_day) - min(per_day),
            "double_slots": doubles,
        }
    return report


def run_phased(
    school: School,
    *,
    handoff_aware: bool = True,
    time_limit: float = 60.0,
) -> PhasedResult:
    """跑完兩個階段。handoff_aware=False 用來對照「Phase 1 不管導師死活」的結果。"""

    units = school.build_units()
    p1_units, p2_units = split_units(school, units)

    s1 = school if handoff_aware else dataclasses.replace(
        school, constraints=[c for c in school.constraints if c.kind not in HANDOFF_KINDS]
    )
    sol1 = Scheduler(s1, units=p1_units, time_limit=time_limit).solve()
    if not sol1.placements:
        return PhasedResult(sol1, {}, [], list(school.classes))

    # Phase 2：每個班獨立求解。導師的課不跨班，所以這裡沒有任何跨班約束。
    # 交接條件只有一個：Phase 1 已佔用的時段。
    s2 = dataclasses.replace(
        school, constraints=[c for c in school.constraints if c.kind not in HANDOFF_KINDS]
    )
    phase2: dict[str, Solution] = {}
    all_pl = list(sol1.placements)
    failed = []
    for cid in school.classes:
        cls_units = [u for u in p2_units if u.class_id == cid]
        if not cls_units:
            continue
        try:
            sol = Scheduler(
                s2, units=cls_units, fixed=sol1.placements, time_limit=time_limit
            ).solve()
        except ValueError as exc:
            phase2[cid] = Solution("NO_SLOT", [], -1, [str(exc)], 0.0)
            failed.append(cid)
            continue
        phase2[cid] = sol
        if sol.placements:
            all_pl.extend(sol.placements)
        else:
            failed.append(cid)

    return PhasedResult(sol1, phase2, all_pl, failed)
