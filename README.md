# 國小排課系統

涵蓋**教師配課**與**教室排課**的設計與可執行原型。

- 完整設計文件：**[docs/DESIGN.md](docs/DESIGN.md)**
- 可執行原型：`prototype/`（Python + Google OR-Tools CP-SAT）

## 解決的問題

- 同一間教室不會同時上兩門課
- 同一位老師不會同時教兩個班
- 同一個班不會同時排兩門課
- 吸收老師的個別需求：哪幾天不排課、一天不超過幾節、不要連上太多節⋯⋯
- 需求彼此打架時，給出**違反最少**的課表並說明犧牲了什麼，而不是丟一句「無解」

## 快速開始

```bash
pip install ortools
cd prototype
python3 gen_sample.py                  # 產生 12 班的範例學校
python3 run.py --class 101 --teacher S_PE --room MUS1
```

## 實測

| 情境 | 規模 | 結果 |
|---|---|---|
| 範例國小 | 12 班 / 19 師 / 328 單元 | **OPTIMAL，1.7 秒**，硬衝突 0 件 |
| 大型國小 | 48 班 / 75 師 / 1312 單元 | **OPTIMAL，31.7 秒**，硬衝突 0 件 |

## 原型結構

| 檔案 | 內容 |
|---|---|
| `prototype/model.py` | 領域模型、統一約束結構、前置可行性檢查 |
| `prototype/solver.py` | CP-SAT 建模與求解 |
| `prototype/render.py` | 班級／教師／教室三視角輸出與驗證 |
| `prototype/gen_sample.py` | 產生範例學校資料 |
| `prototype/run.py` | CLI 進入點 |
| `prototype/data/sample_school.json` | 範例資料（全部設定皆為資料驅動） |
