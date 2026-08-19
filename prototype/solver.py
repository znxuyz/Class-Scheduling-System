"""CP-SAT 排課求解器。

建模方式
--------
決策變數  x[u, s, r] ∈ {0,1}
    教學單元 u 從 slot s 開始、使用教室 r。
    連堂（length=2）的單元會佔用 s 和 s+1 兩個 slot。
    把「時段」與「教室」合併成同一個變數，教室衝突就變成單純的線性不等式，
    不需要額外的乘積/channeling 變數。

covers(u, s) = 所有會佔用到 slot s 的 x 變數集合 —— 三大衝突約束都建立在它上面：
    班級不衝堂：同一班在同一 slot 的 covers 總和 ≤ 1
    教師不衝堂：同一師在同一 slot 的 covers 總和 ≤ 1
    教室不衝堂：同一室在同一 slot 的 covers 總和 ≤ 1

軟需求一律轉成懲罰變數進目標式，因此求解器永遠會給出「違反最少」的課表，
而不是丟一句「無解」。真正的物理衝突（三大不衝堂）才維持硬約束。
"""

from __future__ import annotations

from dataclasses import dataclass

from ortools.sat.python import cp_model

from model import School, Unit


@dataclass
class Placement:
    unit: Unit
    slot: int          # 起始 slot
    room_id: str

    def slots(self) -> list[int]:
        return [self.slot + i for i in range(self.unit.length)]


@dataclass
class Solution:
    status: str
    placements: list[Placement]
    penalty: int
    violations: list[str]          # 哪些軟需求被犧牲了，以及犧牲多少
    wall_time: float


# 各類軟需求的預設權重（可由 Constraint.weight 覆寫）。
# 數量級刻意拉開：老師「整天不排課」的承諾違反成本，遠高於一節課沒排在上午。
DEFAULT_WEIGHTS = {
    "TEACHER_DAY_OFF": 100,
    "TEACHER_UNAVAILABLE": 100,
    "TEACHER_MAX_PER_DAY": 40,
    "TEACHER_MAX_RUN": 20,
    "SUBJECT_SPREAD": 10,
    "TEACHER_COMPACT": 5,
    "SUBJECT_NOT_IN": 8,
    "CORE_IN_MORNING": 2,
}


class Scheduler:
    def __init__(self, school: School, *, time_limit: float = 60.0, workers: int = 8):
        self.school = school
        self.grid = school.grid
        self.units = school.build_units()
        self.time_limit = time_limit
        self.workers = workers

        self.m = cp_model.CpModel()
        self.x: dict[tuple[int, int, str], cp_model.IntVar] = {}
        self.penalties: list[tuple[cp_model.IntVar, int, str]] = []

    # ------------------------------------------------------------------
    # 變數
    # ------------------------------------------------------------------

    def _legal_starts(self, unit: Unit) -> list[int]:
        """單元的合法起始 slot：班級要有課、老師要能來、連堂不可跨日或跨午休。"""
        cls = self.school.classes[unit.class_id]
        blocked = set(cls.blocked) | self.school.teacher_blocked_slots(unit.teacher_id)
        blocked |= self._subject_hard_blocked(unit.subject_id)

        starts = []
        for s in self.grid.all_slots():
            occupied = [s + i for i in range(unit.length)]
            if unit.length == 2 and not self.grid.can_start_double(s):
                continue
            if any(o in blocked for o in occupied):
                continue
            starts.append(s)
        return starts

    def _subject_hard_blocked(self, subject_id: str) -> set[int]:
        blocked: set[int] = set()
        for c in self.school.constraints:
            if c.kind == "SUBJECT_NOT_IN" and c.is_hard and c.params.get("subject") == subject_id:
                periods = c.params.get("periods", [])
                blocked |= {
                    self.grid.slot(d, p)
                    for d in range(1, self.grid.days + 1)
                    for p in periods
                }
        return blocked

    def _build_vars(self) -> None:
        for u in self.units:
            starts = self._legal_starts(u)
            if u.pinned_slot is not None:
                starts = [u.pinned_slot] if u.pinned_slot in starts else []
            if not starts:
                raise ValueError(
                    f"{u.class_id}/{u.subject_id} 找不到任何合法時段 —— "
                    f"硬性限制彼此矛盾，請放寬其中一項"
                )
            for s in starts:
                for r in self.school.candidate_rooms(u):
                    self.x[(u.index, s, r)] = self.m.NewBoolVar(f"x_{u.index}_{s}_{r}")

    def _covers(self, unit_idx: int, slot: int) -> list[cp_model.IntVar]:
        """所有讓 unit 佔用到 slot 的變數（含連堂從前一節開始的情況）。"""
        u = self.units[unit_idx]
        out = []
        for offset in range(u.length):
            key_slot = slot - offset
            for r in self.school.candidate_rooms(u):
                v = self.x.get((unit_idx, key_slot, r))
                if v is not None:
                    out.append(v)
        return out

    def _covers_room(self, unit_idx: int, slot: int, room: str) -> list[cp_model.IntVar]:
        u = self.units[unit_idx]
        out = []
        for offset in range(u.length):
            v = self.x.get((unit_idx, slot - offset, room))
            if v is not None:
                out.append(v)
        return out

    # ------------------------------------------------------------------
    # 硬約束
    # ------------------------------------------------------------------

    def _build_hard(self) -> None:
        # 每個單元剛好被排一次（節數守恆）
        for u in self.units:
            vs = [v for (ui, _, _), v in self.x.items() if ui == u.index]
            self.m.AddExactlyOne(vs)

        by_class: dict[str, list[Unit]] = {}
        by_teacher: dict[str, list[Unit]] = {}
        for u in self.units:
            by_class.setdefault(u.class_id, []).append(u)
            by_teacher.setdefault(u.teacher_id, []).append(u)

        # 班級不衝堂：一個班同一時間只能上一門課
        for cid, units in by_class.items():
            for s in self.grid.all_slots():
                terms = [v for u in units for v in self._covers(u.index, s)]
                if terms:
                    self.m.AddAtMostOne(terms)

        # 教師不衝堂：一個老師同一時間只能教一個班
        for tid, units in by_teacher.items():
            for s in self.grid.all_slots():
                terms = [v for u in units for v in self._covers(u.index, s)]
                if terms:
                    self.m.AddAtMostOne(terms)

        # 教室不衝堂：一間教室同一時間只能有一堂課
        for room_id in self.school.rooms:
            for s in self.grid.all_slots():
                terms = [
                    v
                    for u in self.units
                    if room_id in self.school.candidate_rooms(u)
                    for v in self._covers_room(u.index, s, room_id)
                ]
                if terms:
                    self.m.AddAtMostOne(terms)

        # 教師一天硬上限
        for t in self.school.teachers.values():
            if t.max_per_day >= self.grid.periods:
                continue
            for d in range(1, self.grid.days + 1):
                terms = [
                    v
                    for u in by_teacher.get(t.id, [])
                    for s in self.grid.slots_of_day(d)
                    for v in self._covers(u.index, s)
                ]
                if terms:
                    self.m.Add(sum(terms) <= t.max_per_day)

        # 硬性的 TEACHER_MAX_PER_DAY 需求
        for c in self.school.constraints:
            if c.kind == "TEACHER_MAX_PER_DAY" and c.is_hard:
                tid = c.params["teacher"]
                for d in range(1, self.grid.days + 1):
                    terms = [
                        v
                        for u in by_teacher.get(tid, [])
                        for s in self.grid.slots_of_day(d)
                        for v in self._covers(u.index, s)
                    ]
                    if terms:
                        self.m.Add(sum(terms) <= c.params["max"])

    # ------------------------------------------------------------------
    # 軟約束 → 懲罰項
    # ------------------------------------------------------------------

    def _teacher_busy(self, teacher_id: str, slot: int) -> list[cp_model.IntVar]:
        return [
            v
            for u in self.units
            if u.teacher_id == teacher_id
            for v in self._covers(u.index, slot)
        ]

    def _add_penalty(self, var: cp_model.IntVar, weight: int, label: str) -> None:
        self.penalties.append((var, weight, label))

    def _build_soft(self) -> None:
        g = self.grid
        for c in self.school.constraints:
            if c.is_hard:
                continue
            w = c.weight if c.weight != 1 else DEFAULT_WEIGHTS.get(c.kind, 1)

            if c.kind in ("TEACHER_DAY_OFF", "TEACHER_UNAVAILABLE"):
                tid = c.params["teacher"]
                name = self.school.teachers[tid].name
                if c.kind == "TEACHER_DAY_OFF":
                    slots = g.slots_of_day(c.params["day"])
                    desc = f"{name} 希望週{'一二三四五'[c.params['day'] - 1]}不排課"
                else:
                    slots = sorted(self.school._resolve_slots(c.params))
                    desc = f"{name} 希望避開指定時段"
                terms = [v for s in slots for v in self._teacher_busy(tid, s)]
                if terms:
                    # 直接以「排在該時段的節數」計費，違反越多罰越重
                    cnt = self.m.NewIntVar(0, len(slots), f"viol_{tid}_{c.kind}")
                    self.m.Add(cnt == sum(terms))
                    self._add_penalty(cnt, w, desc)

            elif c.kind == "TEACHER_MAX_PER_DAY":
                tid = c.params["teacher"]
                cap = c.params["max"]
                name = self.school.teachers[tid].name
                for d in range(1, g.days + 1):
                    terms = [v for s in g.slots_of_day(d) for v in self._teacher_busy(tid, s)]
                    if not terms:
                        continue
                    over = self.m.NewIntVar(0, g.periods, f"over_{tid}_{d}")
                    self.m.Add(over >= sum(terms) - cap)
                    self._add_penalty(over, w, f"{name} 一天最多 {cap} 節（超出的節數）")

            elif c.kind == "TEACHER_MAX_RUN":
                tid = c.params["teacher"]
                run = c.params["max"]
                name = self.school.teachers[tid].name
                for d in range(1, g.days + 1):
                    day_slots = g.slots_of_day(d)
                    for i in range(len(day_slots) - run):
                        window = day_slots[i : i + run + 1]
                        terms = [v for s in window for v in self._teacher_busy(tid, s)]
                        if not terms:
                            continue
                        over = self.m.NewIntVar(0, run + 1, f"run_{tid}_{d}_{i}")
                        self.m.Add(over >= sum(terms) - run)
                        self._add_penalty(over, w, f"{name} 連續上課不超過 {run} 節")

            elif c.kind == "TEACHER_COMPACT":
                tid = c.params["teacher"]
                name = self.school.teachers[tid].name
                for d in range(1, g.days + 1):
                    day_slots = g.slots_of_day(d)
                    for i in range(len(day_slots) - 2):
                        a, b, cc = day_slots[i], day_slots[i + 1], day_slots[i + 2]
                        ba = self._bool_busy(tid, a)
                        bb = self._bool_busy(tid, b)
                        bc = self._bool_busy(tid, cc)
                        if ba is None or bb is None or bc is None:
                            continue
                        gap = self.m.NewBoolVar(f"gap_{tid}_{d}_{i}")
                        # 有課 / 空堂 / 有課 的形態 → gap = 1
                        self.m.Add(gap >= ba - bb + bc - 1)
                        self._add_penalty(gap, w, f"{name} 課表中的零星空堂")

            elif c.kind == "SUBJECT_SPREAD":
                sid = c.params["subject"]
                cap = c.params["max"]
                sname = self.school.subjects[sid].name
                for cls in self.school.classes.values():
                    units = [
                        u for u in self.units
                        if u.class_id == cls.id and u.subject_id == sid
                    ]
                    if not units:
                        continue
                    for d in range(1, g.days + 1):
                        terms = [
                            v for u in units for s in g.slots_of_day(d)
                            for v in self._covers(u.index, s)
                        ]
                        if not terms:
                            continue
                        over = self.m.NewIntVar(0, g.periods, f"sp_{cls.id}_{sid}_{d}")
                        self.m.Add(over >= sum(terms) - cap)
                        self._add_penalty(
                            over, w, f"{cls.name} 的{sname}一天不超過 {cap} 節"
                        )

            elif c.kind == "SUBJECT_NOT_IN":
                sid = c.params["subject"]
                periods = c.params["periods"]
                sname = self.school.subjects[sid].name
                slots = [
                    g.slot(d, p) for d in range(1, g.days + 1) for p in periods
                ]
                terms = [
                    v for u in self.units if u.subject_id == sid
                    for s in slots for v in self._covers(u.index, s)
                ]
                if terms:
                    cnt = self.m.NewIntVar(0, len(terms), f"ni_{sid}")
                    self.m.Add(cnt == sum(terms))
                    self._add_penalty(cnt, w, f"{sname}避開第 {periods} 節")

            elif c.kind == "CORE_IN_MORNING":
                core = [s.id for s in self.school.subjects.values() if s.is_core]
                afternoon = [
                    g.slot(d, p)
                    for d in range(1, g.days + 1)
                    for p in range(1, g.periods + 1)
                    if p not in g.morning
                ]
                terms = [
                    v for u in self.units if u.subject_id in core
                    for s in afternoon for v in self._covers(u.index, s)
                ]
                if terms:
                    cnt = self.m.NewIntVar(0, len(terms), "core_pm")
                    self.m.Add(cnt == sum(terms))
                    self._add_penalty(cnt, w, "主科盡量排在上午")

    def _bool_busy(self, teacher_id: str, slot: int) -> cp_model.IntVar | None:
        terms = self._teacher_busy(teacher_id, slot)
        if not terms:
            return None
        b = self.m.NewBoolVar(f"busy_{teacher_id}_{slot}")
        self.m.Add(b == sum(terms))   # 教師不衝堂已保證總和 ≤ 1
        return b

    # ------------------------------------------------------------------

    def solve(self) -> Solution:
        self._build_vars()
        self._build_hard()
        self._build_soft()

        if self.penalties:
            self.m.Minimize(sum(w * v for v, w, _ in self.penalties))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.time_limit
        solver.parameters.num_search_workers = self.workers
        status = solver.Solve(self.m)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return Solution(solver.StatusName(status), [], -1, [], solver.WallTime())

        placements = [
            Placement(self.units[ui], s, r)
            for (ui, s, r), v in self.x.items()
            if solver.Value(v)
        ]
        placements.sort(key=lambda p: (p.slot, p.unit.class_id))

        agg: dict[str, int] = {}
        for var, w, label in self.penalties:
            val = solver.Value(var)
            if val:
                agg[label] = agg.get(label, 0) + val * w
        violations = [f"{k}（成本 {v}）" for k, v in sorted(agg.items(), key=lambda kv: -kv[1])]

        return Solution(
            status=solver.StatusName(status),
            placements=placements,
            penalty=int(solver.ObjectiveValue()) if self.penalties else 0,
            violations=violations,
            wall_time=solver.WallTime(),
        )
