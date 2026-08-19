"""國小排課系統 — 領域模型與前置可行性檢查。

核心觀念：
  1. 「配課」(Assignment) 與「排課」(Timetabling) 是兩個階段，但配課結果直接
     決定排課是否可行，所以在進入求解器之前先做一次可行性檢查 (check_feasibility)。
  2. 每一筆課程需求 (Requirement) 會展開成若干「教學單元」(Unit)。單元是排課的
     最小單位，長度 1 = 單節，長度 2 = 連堂。
  3. 所有老師的個別需求都用統一的 Constraint 結構表達，不寫死在程式裡。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


# --------------------------------------------------------------------------
# 時間格線
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Grid:
    """一週的時間格線。slot 以 0-based 整數編號，day/period 皆為 1-based。"""

    days: int = 5
    periods: int = 7
    # 上午節次（用於「主科排上午」這類偏好）
    morning: tuple[int, ...] = (1, 2, 3, 4)
    # 連堂不可跨越的節次界線：值為 p 代表第 p 節與第 p+1 節之間有斷點（午休）
    double_breaks: tuple[int, ...] = (4,)

    @property
    def n_slots(self) -> int:
        return self.days * self.periods

    def slot(self, day: int, period: int) -> int:
        return (day - 1) * self.periods + (period - 1)

    def day_of(self, slot: int) -> int:
        return slot // self.periods + 1

    def period_of(self, slot: int) -> int:
        return slot % self.periods + 1

    def slots_of_day(self, day: int) -> list[int]:
        return [self.slot(day, p) for p in range(1, self.periods + 1)]

    def all_slots(self) -> list[int]:
        return list(range(self.n_slots))

    def can_start_double(self, slot: int) -> bool:
        """該 slot 是否可以作為連堂的起點（不跨日、不跨午休）。"""
        p = self.period_of(slot)
        return p < self.periods and p not in self.double_breaks

    def label(self, slot: int) -> str:
        return f"{'一二三四五六日'[self.day_of(slot) - 1]}{self.period_of(slot)}"


# --------------------------------------------------------------------------
# 基本實體
# --------------------------------------------------------------------------

@dataclass
class Subject:
    id: str
    name: str
    room_type: str | None = None   # None = 在原班教室上；否則需要該類型的專科教室
    is_core: bool = False          # 主科（國語/數學），會有「盡量排上午」的偏好


@dataclass
class Room:
    id: str
    name: str
    type: str                      # "homeroom" | "music" | "computer" | "pe" | "art" | ...


@dataclass
class SchoolClass:
    id: str
    name: str
    grade: int
    homeroom: str                  # 原班教室 room id
    blocked: list[int] = field(default_factory=list)  # 不上課的 slot（如低年級週三下午）


@dataclass
class Teacher:
    id: str
    name: str
    max_per_week: int = 99
    max_per_day: int = 99          # 硬上限；「希望一天不超過幾節」用 soft constraint 表達
    role: str = "homeroom"         # "homeroom" 導師 | "special" 科任 | "admin" 兼行政


@dataclass
class Requirement:
    """某班某科目一週要上幾節，由誰教。這就是「配課」的結果。"""

    class_id: str
    subject_id: str
    periods: int
    teacher_id: str
    doubles: int = 0               # 其中要安排幾個「連堂」（各佔 2 節）

    def unit_lengths(self) -> list[int]:
        singles = self.periods - 2 * self.doubles
        if singles < 0:
            raise ValueError(
                f"{self.class_id}/{self.subject_id}: 連堂數 {self.doubles} 超過總節數 {self.periods}"
            )
        return [2] * self.doubles + [1] * singles


@dataclass
class Constraint:
    """統一的需求表達式。新增一種老師需求 = 新增一個 kind，不必改資料表結構。

    kind:
      TEACHER_UNAVAILABLE   老師某些時段不能排課       params: {teacher, slots|days|periods}
      TEACHER_DAY_OFF       老師希望某天完全沒課       params: {teacher, day}
      TEACHER_MAX_PER_DAY   老師一天最多幾節           params: {teacher, max}
      TEACHER_MAX_RUN       老師最多連續幾節           params: {teacher, max}
      TEACHER_COMPACT       老師的課盡量不要有空堂     params: {teacher}
      SUBJECT_SPREAD        同科目一天最多幾節（分散） params: {subject, max}
      SUBJECT_NOT_IN        某科不排在某些節次         params: {subject, periods}
      CORE_IN_MORNING       主科盡量排上午             params: {}
      RESERVE_MORNING       本階段課程少佔各班上午     params: {max_per_class}
      SPECIAL_BALANCE       各班每天的本階段課程節數   params: {max_per_day}
      HOMEROOM_DAY_CAPACITY 每班每天留給導師的空格數   params: {}
                            不得超過導師的日上限（分階段排課的可行性前提）
      HOMEROOM_DAY_OFF      導師想休的那天，該班要被   params: {}
                            科任課填滿（否則導師必須來上課）
    hardness: "hard" | "soft"
    """

    kind: str
    params: dict[str, Any] = field(default_factory=dict)
    hardness: str = "soft"
    weight: int = 1

    @property
    def is_hard(self) -> bool:
        return self.hardness == "hard"


# 這幾種約束描述的是「本階段課程佔用了什麼、留下了什麼」，只有在分階段排課的
# Phase 1（self.units 是科任／行政的真子集）才有意義。全校一次求解時 self.units
# 包含導師的課，套用它們會把導師自己的課也算成「佔用」，必須排除。
HANDOFF_KINDS = frozenset({
    "HOMEROOM_DAY_CAPACITY", "HOMEROOM_DAY_OFF",
    "RESERVE_MORNING", "SPECIAL_BALANCE",
})


@dataclass
class Unit:
    """排課的最小單位：一個要被放到格線上的教學時段。"""

    index: int
    class_id: str
    subject_id: str
    teacher_id: str
    length: int                    # 1 = 單節, 2 = 連堂
    pinned_slot: int | None = None # 人工鎖定（手動微調後重排時使用）


# --------------------------------------------------------------------------
# 學校（聚合根）
# --------------------------------------------------------------------------

@dataclass
class School:
    grid: Grid
    subjects: dict[str, Subject]
    rooms: dict[str, Room]
    classes: dict[str, SchoolClass]
    teachers: dict[str, Teacher]
    requirements: list[Requirement]
    constraints: list[Constraint]

    # ---- 衍生資料 ----

    def build_units(self) -> list[Unit]:
        units: list[Unit] = []
        for req in self.requirements:
            for length in req.unit_lengths():
                units.append(
                    Unit(
                        index=len(units),
                        class_id=req.class_id,
                        subject_id=req.subject_id,
                        teacher_id=req.teacher_id,
                        length=length,
                    )
                )
        return units

    def homeroom_teacher_of(self, class_id: str) -> Teacher | None:
        """該班的導師 —— 帶這個班、且身分為 homeroom 的教師。"""
        for r in self.requirements:
            t = self.teachers.get(r.teacher_id)
            if r.class_id == class_id and t and t.role == "homeroom":
                return t
        return None

    def teachable_slots(self, class_id: str, day: int) -> list[int]:
        """該班某天真正要上課的時段（扣掉不上課的節次）。"""
        blocked = set(self.classes[class_id].blocked)
        return [s for s in self.grid.slots_of_day(day) if s not in blocked]

    def hard_day_cap(self, teacher_id: str) -> int:
        """教師的日節數硬上限，含 Teacher.max_per_day 與硬性的 TEACHER_MAX_PER_DAY。"""
        caps = [self.teachers[teacher_id].max_per_day]
        caps += [
            c.params["max"] for c in self.constraints
            if c.kind == "TEACHER_MAX_PER_DAY" and c.is_hard
            and c.params.get("teacher") == teacher_id
        ]
        return min(caps)

    def rooms_of_type(self, room_type: str) -> list[str]:
        return [r.id for r in self.rooms.values() if r.type == room_type]

    def candidate_rooms(self, unit: Unit) -> list[str]:
        """單元可用的教室。一般科目綁原班教室，專科課程才需要在專科教室之間選。"""
        subject = self.subjects[unit.subject_id]
        if subject.room_type is None:
            return [self.classes[unit.class_id].homeroom]
        return self.rooms_of_type(subject.room_type)

    def teacher_blocked_slots(self, teacher_id: str) -> set[int]:
        """老師的硬性不可用時段（TEACHER_UNAVAILABLE + 硬性的 TEACHER_DAY_OFF）。"""
        blocked: set[int] = set()
        for c in self.constraints:
            if c.params.get("teacher") != teacher_id or not c.is_hard:
                continue
            if c.kind == "TEACHER_UNAVAILABLE":
                blocked |= self._resolve_slots(c.params)
            elif c.kind == "TEACHER_DAY_OFF":
                blocked |= set(self.grid.slots_of_day(c.params["day"]))
        return blocked

    def _resolve_slots(self, params: dict[str, Any]) -> set[int]:
        """把 {slots} 或 {days, periods} 展開成 slot 集合。"""
        if "slots" in params:
            return {self.grid.slot(d, p) for d, p in params["slots"]}
        days = params.get("days") or list(range(1, self.grid.days + 1))
        periods = params.get("periods") or list(range(1, self.grid.periods + 1))
        return {self.grid.slot(d, p) for d in days for p in periods}

    # ---- 載入 ----

    @staticmethod
    def from_json(path: str) -> "School":
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)

        g = raw.get("grid", {})
        grid = Grid(
            days=g.get("days", 5),
            periods=g.get("periods", 7),
            morning=tuple(g.get("morning", [1, 2, 3, 4])),
            double_breaks=tuple(g.get("double_breaks", [4])),
        )

        classes = {}
        for c in raw["classes"]:
            blocked = [grid.slot(d, p) for d, p in c.get("blocked", [])]
            classes[c["id"]] = SchoolClass(
                id=c["id"], name=c["name"], grade=c["grade"],
                homeroom=c["homeroom"], blocked=blocked,
            )

        return School(
            grid=grid,
            subjects={s["id"]: Subject(**s) for s in raw["subjects"]},
            rooms={r["id"]: Room(**r) for r in raw["rooms"]},
            classes=classes,
            teachers={t["id"]: Teacher(**t) for t in raw["teachers"]},
            requirements=[Requirement(**r) for r in raw["requirements"]],
            constraints=[Constraint(**c) for c in raw.get("constraints", [])],
        )


# --------------------------------------------------------------------------
# 前置可行性檢查
# --------------------------------------------------------------------------
# 排課求解器回報「無解」對使用者毫無幫助。絕大多數的無解其實是配課階段就已經
# 注定的資源超載，這些用簡單的計數就能抓出來，而且能明確指出是誰的問題。

def check_feasibility(school: School) -> list[str]:
    """回傳問題清單；空清單代表通過基本檢查（必要條件，非充分條件）。"""

    errors: list[str] = []
    grid = school.grid

    # 1. 參照完整性
    for req in school.requirements:
        if req.class_id not in school.classes:
            errors.append(f"需求參照到不存在的班級：{req.class_id}")
        if req.subject_id not in school.subjects:
            errors.append(f"需求參照到不存在的科目：{req.subject_id}")
        if req.teacher_id not in school.teachers:
            errors.append(f"需求參照到不存在的教師：{req.teacher_id}")

    if errors:
        return errors

    # 2. 班級：總節數不可超過該班可用時段
    for cls in school.classes.values():
        total = sum(r.periods for r in school.requirements if r.class_id == cls.id)
        capacity = grid.n_slots - len(cls.blocked)
        if total > capacity:
            errors.append(
                f"班級 {cls.name} 配課 {total} 節，但一週只有 {capacity} 個可上課時段"
            )

    # 3. 教師：總節數 vs 週上限、vs 可用時段
    for t in school.teachers.values():
        total = sum(r.periods for r in school.requirements if r.teacher_id == t.id)
        if total > t.max_per_week:
            errors.append(
                f"教師 {t.name} 配課 {total} 節，超過週上限 {t.max_per_week} 節"
            )
        available = grid.n_slots - len(school.teacher_blocked_slots(t.id))
        if total > available:
            errors.append(
                f"教師 {t.name} 配課 {total} 節，但扣掉不可排課時段後只剩 {available} 個時段"
            )
        # 一天上限 × 天數 的總量檢查
        hard_day_caps = [
            c.params["max"] for c in school.constraints
            if c.kind == "TEACHER_MAX_PER_DAY" and c.is_hard and c.params.get("teacher") == t.id
        ]
        cap = min([t.max_per_day, *hard_day_caps])
        if cap < 99:
            free_days = {
                grid.day_of(s) for s in grid.all_slots()
                if s not in school.teacher_blocked_slots(t.id)
            }
            if total > cap * len(free_days):
                errors.append(
                    f"教師 {t.name} 配課 {total} 節，但一天最多 {cap} 節 × "
                    f"{len(free_days)} 個可上課日 = {cap * len(free_days)} 節"
                )

    # 4. 專科教室：該類型教室的總容量是否吃得下所有需求
    demand: dict[str, int] = {}
    for req in school.requirements:
        rt = school.subjects[req.subject_id].room_type
        if rt:
            demand[rt] = demand.get(rt, 0) + req.periods
    for rt, need in demand.items():
        n_rooms = len(school.rooms_of_type(rt))
        if n_rooms == 0:
            errors.append(f"科目需要 {rt} 類型的教室，但學校沒有這種教室")
            continue
        capacity = n_rooms * grid.n_slots
        if need > capacity:
            errors.append(
                f"{rt} 類型教室需求 {need} 節，但 {n_rooms} 間 × {grid.n_slots} 節 "
                f"= {capacity} 節，容量不足"
            )

    # 5. 同一老師在同一時段只能教一班 → 老師教的所有班若都被同一天鎖住會衝突，
    #    這裡做較弱但實用的檢查：老師教的班級數不可超過可用時段
    for t in school.teachers.values():
        classes_taught = {r.class_id for r in school.requirements if r.teacher_id == t.id}
        if len(classes_taught) > grid.n_slots:
            errors.append(f"教師 {t.name} 被配了 {len(classes_taught)} 個班，超過一週總節數")

    return errors
