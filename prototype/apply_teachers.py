"""把畫面上匯出的 teachers.json 套回學校資料，然後就能重新排課。

畫面（GitHub Pages 上的靜態網站）只能編輯資料，跑不了求解器；求解在本機做。
這支腳本是兩者之間的橋：

    python3 apply_teachers.py ~/Downloads/teachers.json
    python3 run.py --phased

只覆蓋教師與教師相關的需求，班級／教室／科目／配課都保持原樣。
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("teachers", help="畫面匯出的 teachers.json")
    ap.add_argument("--school", default=os.path.join(here, "data", "sample_school.json"))
    ap.add_argument("--out", default=None, help="預設就地覆寫 --school")
    args = ap.parse_args()

    with open(args.teachers, encoding="utf-8") as fh:
        exported = json.load(fh)
    with open(args.school, encoding="utf-8") as fh:
        school = json.load(fh)

    if not isinstance(exported.get("teachers"), list):
        print("✗ 這不是教師設定檔：找不到 teachers 陣列", file=sys.stderr)
        return 1

    school["teachers"] = exported["teachers"]

    # 教師相關的需求整批換掉；班級／科目層級的需求（例如「主科排上午」）保留
    keep = [c for c in school.get("constraints", []) if "teacher" not in c.get("params", {})]
    school["constraints"] = keep + exported.get("constraints", [])

    # 配課若指到已被刪除的老師，先講清楚，不要等到求解才炸
    valid = {t["id"] for t in school["teachers"]}
    orphan = sorted({r["teacher_id"] for r in school["requirements"]
                     if r["teacher_id"] not in valid})
    if orphan:
        print(f"✗ 有配課指到不存在的老師：{'、'.join(orphan)}", file=sys.stderr)
        print("  請先在畫面上把這些課改派給其他人，或把老師加回來。", file=sys.stderr)
        return 1

    out = args.out or args.school
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(school, fh, ensure_ascii=False, indent=2)
    print(f"已套用 {len(school['teachers'])} 位教師、"
          f"{len(exported.get('constraints', []))} 條教師需求 → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
