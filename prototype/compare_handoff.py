"""量化「Phase 1 有沒有為導師保留空格」的差別。

這是分階段排課唯一真正的風險：科任先排完，導師拿到的空格形狀已成定局。
"""
import statistics
from model import School, check_feasibility
from phased import run_phased, leftover_report, split_units

school = School.from_json("data/sample_school.json")
units = school.build_units()
p1, p2 = split_units(school, units)
print(f"單元總數 {len(units)}　→　Phase 1 科任/行政 {len(p1)}　Phase 2 導師 {len(p2)}")
print("可行性:", check_feasibility(school) or "通過")

for aware in (False, True):
    tag = "為導師保留空格" if aware else "只顧科任方便"
    print(f"\n{'='*62}\n【Phase 1 {tag}】")
    res = run_phased(school, handoff_aware=aware, time_limit=45)
    rep = leftover_report(school, res.phase1.placements)

    fits = sum(1 for r in rep.values() if r["core_fits_morning"])
    spread = [r["day_spread"] for r in rep.values()]
    doubles = [r["double_slots"] for r in rep.values()]
    print(f"Phase 1: {res.phase1.status}  {res.phase1.wall_time:.1f}s  懲罰 {res.phase1.penalty}")
    print(f"  主科排得下上午的班級      : {fits}/{len(rep)}")
    print(f"  各班空格日間落差(max-min) : 平均 {statistics.mean(spread):.1f}　最差 {max(spread)}")
    print(f"  可放連堂的空格            : 平均 {statistics.mean(doubles):.1f}")

    ok = [c for c, s in res.phase2.items() if s.placements]
    p2_pen = sum(s.penalty for s in res.phase2.values() if s.placements)
    p2_time = sum(s.wall_time for s in res.phase2.values())
    print(f"Phase 2: {len(ok)}/{len(res.phase2)} 班排出　合計 {p2_time:.1f}s　懲罰合計 {p2_pen}")
    if res.failed_classes:
        print(f"  ✗ 排不出來的班: {res.failed_classes}")
        for c in res.failed_classes[:2]:
            print(f"    {c}: {res.phase2[c].violations}")

    # 全域硬約束驗證
    seen, clash = set(), 0
    for pl in res.placements:
        for s in pl.slots():
            for k in ((pl.unit.class_id, s), ("T", pl.unit.teacher_id, s), ("R", pl.room_id, s)):
                if k in seen: clash += 1
                seen.add(k)
    print(f"全域硬衝突: {clash} 件　已排時段 {sum(p.unit.length for p in res.placements)}")

    worst = min(rep.items(), key=lambda kv: kv[1]["morning_free"] - kv[1]["core_need"])
    w = worst[1]
    print(f"最吃緊的班 {worst[0]}: 主科需 {w['core_need']} 節，上午只剩 {w['morning_free']} 格"
          f"　每日空格 {w['per_day']}")
