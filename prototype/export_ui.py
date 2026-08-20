"""把求解結果匯出成畫面原型要用的 JSON（真實資料，非假資料）。"""
import json
from model import School, check_feasibility
from phased import leftover_report, run_phased, split_units

school = School.from_json("data/sample_school.json")
g = school.grid
res = run_phased(school, handoff_aware=True, time_limit=60)
bad = run_phased(school, handoff_aware=False, time_limit=60)   # 對照組：交接沒顧好

def pl_json(p, phase):
    return {"c": p.unit.class_id, "s": p.unit.subject_id, "t": p.unit.teacher_id,
            "r": p.room_id, "slot": p.slot, "len": p.unit.length, "ph": phase}

placements = ([pl_json(p, 1) for p in res.phase1.placements] +
              [pl_json(p, 2) for s in res.phase2.values() for p in s.placements])

# 各教師的配課節數與上限（配課畫面用）
loads = []
for t in school.teachers.values():
    total = sum(r.periods for r in school.requirements if r.teacher_id == t.id)
    loads.append({"id": t.id, "name": t.name, "role": t.role,
                  "total": total, "max": t.max_per_week, "cap": school.hard_day_cap(t.id),
                  "classes": sorted({r.class_id for r in school.requirements if r.teacher_id == t.id}),
                  "subjects": sorted({r.subject_id for r in school.requirements if r.teacher_id == t.id})})

def handoff(r):
    rep = leftover_report(school, r.phase1.placements)
    out = {}
    for cid, v in rep.items():
        cap = school.hard_day_cap(f"HR_{cid}")
        out[cid] = {**v, "cap": cap,
                    "usable": sum(min(n, cap) for n in v["per_day"]),
                    "over": [n > cap for n in v["per_day"]]}
    return out

data = {
    "grid": {"days": g.days, "periods": g.periods, "morning": list(g.morning),
             "breaks": list(g.double_breaks)},
    "subjects": {s.id: {"name": s.name, "room": s.room_type, "core": s.is_core}
                 for s in school.subjects.values()},
    "rooms": {r.id: {"name": r.name, "type": r.type} for r in school.rooms.values()},
    "classes": {c.id: {"name": c.name, "grade": c.grade, "room": c.homeroom,
                       "blocked": c.blocked} for c in school.classes.values()},
    "teachers": {t.id: {"name": t.name, "role": t.role, "max": t.max_per_week,
                        "cap": school.hard_day_cap(t.id)} for t in school.teachers.values()},
    "requirements": [{"c": r.class_id, "s": r.subject_id, "n": r.periods,
                      "t": r.teacher_id, "d": r.doubles} for r in school.requirements],
    "constraints": [{"kind": c.kind, "params": c.params, "hard": c.is_hard,
                     "weight": c.weight} for c in school.constraints],
    "loads": loads,
    "placements": placements,
    "handoff": {"good": handoff(res), "bad": handoff(bad)},
    "solve": {
        "p1": {"status": res.phase1.status, "time": round(res.phase1.wall_time, 2),
               "penalty": res.phase1.penalty, "violations": res.phase1.violations},
        "p2": {cid: {"status": s.status, "penalty": s.penalty,
                     "time": round(s.wall_time, 3), "violations": s.violations}
               for cid, s in res.phase2.items()},
        "badFailed": bad.failed_classes,
    },
    "feasibility": check_feasibility(school),
}
json.dump(data, open("data/ui_data.json", "w"), ensure_ascii=False, separators=(",", ":"))
p1, p2 = split_units(school, school.build_units())
print(f"placements {len(placements)}　phase1 {len(p1)} 單元　phase2 {len(p2)} 單元")
print(f"對照組失敗班級 {bad.failed_classes}")
print("bytes", len(open("data/ui_data.json","rb").read()))
