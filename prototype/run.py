"""CLI：載入學校資料 → 可行性檢查 → 排課 → 輸出三視角課表。

  python3 run.py [data/sample_school.json] [--time 60] [--class 501] [--teacher S_PE]
"""

from __future__ import annotations

import argparse
import os
import sys

from model import School, check_feasibility
from solver import Scheduler
import render


def main() -> int:
    default_data = os.path.join(os.path.dirname(__file__), "data", "sample_school.json")
    ap = argparse.ArgumentParser()
    ap.add_argument("data", nargs="?", default=default_data)
    ap.add_argument("--time", type=float, default=60.0, help="求解時間上限（秒）")
    ap.add_argument("--class", dest="klass", action="append", default=[])
    ap.add_argument("--teacher", action="append", default=[])
    ap.add_argument("--room", action="append", default=[])
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

    sol = Scheduler(school, time_limit=args.time).solve()
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
