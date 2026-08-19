"""產生範例學校資料：6 個年級 × 2 班 = 12 班的典型國小。

刻意把國小的幾個特徵放進來：
  - 包班制：導師教國語/數學/社會/綜合/健康，科任老師跑班教藝能與英語自然
  - 低年級週三下午不上課、每天不上第 7 節
  - 音樂/電腦/美術/體育需要專科教室，且全校只有一間
  - 綜合活動排連堂
"""

import json
import os

SUBJECTS = [
    {"id": "CH", "name": "國語",   "room_type": None,       "is_core": True},
    {"id": "MA", "name": "數學",   "room_type": None,       "is_core": True},
    {"id": "LI", "name": "生活",   "room_type": None,       "is_core": False},
    {"id": "SO", "name": "社會",   "room_type": None,       "is_core": False},
    {"id": "IN", "name": "綜合",   "room_type": None,       "is_core": False},
    {"id": "HE", "name": "健康",   "room_type": None,       "is_core": False},
    {"id": "FX", "name": "彈性",   "room_type": None,       "is_core": False},
    {"id": "SC", "name": "自然",   "room_type": "science",  "is_core": False},
    {"id": "EN", "name": "英語",   "room_type": None,       "is_core": False},
    {"id": "PE", "name": "體育",   "room_type": "pe",       "is_core": False},
    {"id": "MU", "name": "音樂",   "room_type": "music",    "is_core": False},
    {"id": "AR", "name": "美勞",   "room_type": "art",      "is_core": False},
    {"id": "CO", "name": "電腦",   "room_type": "computer", "is_core": False},
]

# 導師自任科目的節數配置（依年段）
HOMEROOM_PLAN = {
    "low":  [("CH", 8, 0), ("MA", 4, 0), ("LI", 4, 1), ("IN", 2, 1), ("HE", 1, 0)],
    "mid":  [("CH", 6, 0), ("MA", 4, 0), ("SO", 3, 0), ("IN", 3, 1), ("HE", 1, 0), ("FX", 3, 0)],
    "high": [("CH", 6, 0), ("MA", 4, 0), ("SO", 3, 0), ("IN", 3, 1), ("HE", 1, 0), ("FX", 5, 0)],
}
# 科任課程（依年段）
SPECIAL_PLAN = {
    "low":  [("MU", 1), ("PE", 2), ("AR", 1), ("CO", 1)],
    "mid":  [("MU", 1), ("PE", 2), ("AR", 1), ("CO", 1), ("EN", 2), ("SC", 3)],
    "high": [("MU", 1), ("PE", 2), ("AR", 1), ("CO", 1), ("EN", 2), ("SC", 3)],
}


def band(grade: int) -> str:
    return "low" if grade <= 2 else ("mid" if grade <= 4 else "high")


def blocked_slots(grade: int) -> list[list[int]]:
    """回傳 [day, period] 清單。低年級課少，下午空堂多。"""
    b = []
    if grade <= 2:
        b += [[d, 7] for d in range(1, 6)]          # 每天不上第 7 節
        b += [[3, 5], [3, 6]]                        # 週三下午完全不上課
    elif grade <= 4:
        b += [[3, 5], [3, 6], [3, 7]]                # 週三下午不上課
    else:
        b += [[3, 6], [3, 7]]
    return b


def build() -> dict:
    rooms = [{"id": "SCI1", "name": "自然教室", "type": "science"},
             {"id": "PE1",  "name": "活動中心", "type": "pe"},
             {"id": "MUS1", "name": "音樂教室", "type": "music"},
             {"id": "ART1", "name": "美勞教室", "type": "art"},
             {"id": "COM1", "name": "電腦教室", "type": "computer"}]

    classes, teachers, requirements = [], [], []

    # 科任教師
    # role: special = 科任跑班, admin = 兼行政（減課且有固定行政時段）
    sp = lambda i, n, w, d: {"id": i, "name": n, "max_per_week": w, "max_per_day": d,
                             "role": "special"}
    ad = lambda i, n, w, d: {"id": i, "name": n, "max_per_week": w, "max_per_day": d,
                             "role": "admin"}
    specials = {
        "MU": [sp("S_MU", "音樂老師", 20, 5)],
        # 美勞與電腦各由一位科任與一位兼行政的主任分擔
        "AR": [sp("S_AR", "美勞老師", 20, 5), ad("A_STU", "學務主任", 10, 3)],
        "CO": [sp("S_CO", "電腦老師", 20, 5), ad("A_ACA", "教務主任", 10, 3)],
        "PE": [sp("S_PE", "體育老師", 26, 6)],
        "SC": [sp("S_SC", "自然老師", 26, 6)],
        "EN": [sp("S_EN1", "英語老師甲", 20, 5), sp("S_EN2", "英語老師乙", 20, 5)],
    }
    for group in specials.values():
        teachers.extend(group)

    rr = {k: 0 for k in specials}
    for grade in range(1, 7):
        for seq in (1, 2):
            cid = f"{grade}0{seq}"
            room_id = f"R{cid}"
            rooms.append({"id": room_id, "name": f"{cid} 教室", "type": "homeroom"})
            classes.append({
                "id": cid, "name": f"{grade} 年 {seq} 班", "grade": grade,
                "homeroom": room_id, "blocked": blocked_slots(grade),
            })

            tid = f"HR_{cid}"
            teachers.append({
                "id": tid, "name": f"{cid} 導師", "max_per_week": 24, "max_per_day": 6,
                "role": "homeroom",
            })

            bnd = band(grade)
            for sid, periods, doubles in HOMEROOM_PLAN[bnd]:
                requirements.append({
                    "class_id": cid, "subject_id": sid, "periods": periods,
                    "teacher_id": tid, "doubles": doubles,
                })
            for sid, periods in SPECIAL_PLAN[bnd]:
                pool = specials[sid]
                teacher_id = pool[rr[sid] % len(pool)]["id"]
                rr[sid] += 1
                requirements.append({
                    "class_id": cid, "subject_id": sid, "periods": periods,
                    "teacher_id": teacher_id, "doubles": 0,
                })

    constraints = [
        # ---- 兼行政教師的固定行政時段（物理事實，設為硬約束）----
        {"kind": "TEACHER_UNAVAILABLE", "params": {"teacher": "A_ACA", "days": [1], "periods": [1, 2]},
         "hardness": "hard"},
        {"kind": "TEACHER_UNAVAILABLE", "params": {"teacher": "A_STU", "days": [1], "periods": [1, 2]},
         "hardness": "hard"},
        # ---- 交接品質：Phase 1 要為導師留下好用的空格 ----
        {"kind": "HOMEROOM_DAY_CAPACITY", "params": {}, "hardness": "soft"},
        {"kind": "HOMEROOM_DAY_OFF", "params": {}, "hardness": "soft"},
        {"kind": "RESERVE_MORNING", "params": {"max_per_class": 4}, "hardness": "soft"},
        {"kind": "SPECIAL_BALANCE", "params": {"max_per_day": 3}, "hardness": "soft"},
        # ---- 老師的個別需求 ----
        {"kind": "TEACHER_DAY_OFF", "params": {"teacher": "S_EN1", "day": 3},
         "hardness": "soft", "weight": 200},
        {"kind": "TEACHER_UNAVAILABLE", "params": {"teacher": "S_MU", "days": [5], "periods": [5, 6, 7]},
         "hardness": "hard"},
        {"kind": "TEACHER_DAY_OFF", "params": {"teacher": "HR_101", "day": 5},
         "hardness": "soft", "weight": 150},
        {"kind": "TEACHER_MAX_PER_DAY", "params": {"teacher": "S_PE", "max": 5}, "hardness": "soft"},
        {"kind": "TEACHER_MAX_PER_DAY", "params": {"teacher": "S_SC", "max": 5}, "hardness": "soft"},
        {"kind": "TEACHER_MAX_RUN", "params": {"teacher": "S_PE", "max": 3}, "hardness": "soft"},
        {"kind": "TEACHER_COMPACT", "params": {"teacher": "S_MU"}, "hardness": "soft"},
        {"kind": "TEACHER_COMPACT", "params": {"teacher": "S_CO"}, "hardness": "soft"},
        {"kind": "TEACHER_COMPACT", "params": {"teacher": "S_AR"}, "hardness": "soft"},
        # ---- 教學品質偏好 ----
        {"kind": "SUBJECT_SPREAD", "params": {"subject": "CH", "max": 2}, "hardness": "soft"},
        {"kind": "SUBJECT_SPREAD", "params": {"subject": "MA", "max": 1}, "hardness": "soft"},
        {"kind": "SUBJECT_SPREAD", "params": {"subject": "EN", "max": 1}, "hardness": "soft"},
        {"kind": "SUBJECT_NOT_IN", "params": {"subject": "PE", "periods": [5]}, "hardness": "soft"},
        {"kind": "CORE_IN_MORNING", "params": {}, "hardness": "soft"},
    ]

    return {
        "grid": {"days": 5, "periods": 7, "morning": [1, 2, 3, 4], "double_breaks": [4]},
        "subjects": SUBJECTS, "rooms": rooms, "classes": classes,
        "teachers": teachers, "requirements": requirements, "constraints": constraints,
    }


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "data", "sample_school.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(build(), fh, ensure_ascii=False, indent=2)
    print(f"wrote {out}")
