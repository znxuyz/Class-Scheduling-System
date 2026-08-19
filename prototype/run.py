"""CLI：載入學校資料 → 可行性檢查 → 排課 → 輸出三視角課表。

  python3 run.py [data/sample_school.json] [--time 60] [--class 501] [--teacher S_PE]
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import sys

from model import HANDOFF_KINDS, School, check_feasibility
from solver import Scheduler, Solution
from phased import leftover_report, run_phased, split_units
import render


def main() -> int:
    default_data = os.path.join(os.path.dirname(__file__), "data", "sample_school.json")
    ap = argparse.ArgumentParser()
    ap.add_argument("data", nargs="?", default=default_data)
    ap.add_argument("--time", type=float, default=60.0, help="求解時間上限（秒）")
    ap.add_argument("--class", dest="klass", action="append", default=[])
    ap.add_argument("--teacher", action="append", default=[])
    ap.add_argument("--room", action="append", default=[])
    ap.add_argument("--phased", action="store_true",
                    help="分階段排課：科任／行政先排，剩下的空格再給導師")
    ap.add_argument("--no-handoff-care", action="store_true",
                    help="（對照組）Phase 1 不管留給導師的空格好不好用")
    args = ap.parse_args()

    school = School.from_json(args.data)
    print(f"班級 {len(school.classes)}　教師 {len(school.teachers)}　"
          f"教室 {len(school.rooms)}　配課筆數 {len(school.requirements)}　"
          f"待排單元 {len(school.build_units())}")

    problems = check_feasibility(school)
    if problems:
        print("\n[可行性檢查未通過] 這些問題在排課前就注定無解，請先修正配課：")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print("可行性檢查：通過")

    if args.phased:
        p1, p2 = split_units(school, school.build_units())
        print(f"\n分階段排課：Phase 1 科任／行政 {len(p1)} 單元　"
              f"Phase 2 導師 {len(p2)} 單元")
        res = run_phased(
            school, handoff_aware=not args.no_handoff_care, time_limit=args.time
        )
        print(f"Phase 1：{res.phase1.status}　{res.phase1.wall_time:.1f}s　"
              f"懲罰 {res.phase1.penalty}")
        for v in res.phase1.violations:
            print(f"  ! {v}")

        print("\nPhase 1 排完後，各班留給導師的空格：")
        for cid, rp in leftover_report(school, res.phase1.placements).items():
            cap = school.hard_day_cap(f"HR_{cid}")
            flag = "  ✗ 有一天的空格多於導師日上限" if max(rp["per_day"]) > cap else ""
            print(f"  {school.classes[cid].name}: 空格 {rp['free']} / 需 {rp['need']}　"
                  f"每日 {rp['per_day']}　可放連堂 {rp['double_slots']}{flag}")

        ok = [c for c, s in res.phase2.items() if s.placements]
        print(f"\nPhase 2：{len(ok)}/{len(res.phase2)} 班排出　"
              f"懲罰合計 {sum(s.penalty for s in res.phase2.values() if s.placements)}")
        for cid in res.failed_classes:
            print(f"  ✗ {school.classes[cid].name} 排不出來：{res.phase2[cid].status}")
        sol = Solution(
            status=res.phase1.status, placements=res.placements,
            penalty=res.phase1.penalty
            + sum(s.penalty for s in res.phase2.values() if s.placements),
            violations=res.phase1.violations
            + [v for s in res.phase2.values() for v in s.violations],
            wall_time=res.phase1.wall_time
            + sum(s.wall_time for s in res.phase2.values()),
        )
    else:
        # 交接約束只在 Phase 1 有意義（見 model.HANDOFF_KINDS）
        single = dataclasses.replace(
            school,
            constraints=[c for c in school.constraints if c.kind not in HANDOFF_KINDS],
        )
        sol = Scheduler(single, time_limit=args.time).solve()

    if not sol.placements:
        print(f"\n求解失敗：{sol.status}")
        return 1

    render.summary(school, sol)
    for cid in args.klass:
        render.class_view(school, sol, cid)
    for tid in args.teacher:
        render.teacher_view(school, sol, tid)
    for rid in args.room:
        render.room_view(school, sol, rid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
