# 國小排課系統

涵蓋**教師配課**與**教室排課**的設計與可執行原型。

- 完整設計文件：**[docs/DESIGN.md](docs/DESIGN.md)**
- 可執行原型：`prototype/`（Python + Google OR-Tools CP-SAT）

## 解決的問題

- 同一間教室不會同時上兩門課
- 同一位老師不會同時教兩個班
- 同一個班不會同時排兩門課
- 吸收老師的個別需求：哪幾天不排課、只能排在哪些時段、一天不超過幾節、不要連上太多節⋯⋯
- 需求彼此打架時，給出**違反最少**的課表並說明犧牲了什麼，而不是丟一句「無解」
- 排完之後還能手動微調，且**自動連帶挪動受影響的課**（同一位科任老師在別班的課、
  被跨班共用的專科教室），全程不產生撞堂

## 排課流程

依實務做法分兩階段（詳見 [DESIGN.md §7](docs/DESIGN.md)）：

1. **配課**：設定每位老師要上哪些課，即時檢查鐘點有沒有超載
2. **Phase 1**：科任 + 兼行政教師先排（跨班跑、搶專科教室，最難排）
3. **Phase 2**：剩下的空格給導師 —— 導師只教自己班，所以各班完全獨立，
   可以自動排，也可以直接讓導師在介面上拖拉

關鍵：Phase 1 必須為 Phase 2 保留可用的空格形狀，否則導師會排不出來。
實測不做這件事，6 次有 6 次會有班級 `INFEASIBLE`。

## 快速開始

```bash
pip install ortools
cd prototype
python3 gen_sample.py                       # 產生 12 班的範例學校
python3 run.py --phased --class 502          # 分階段排課（實務流程）
python3 run.py --class 101 --teacher S_PE    # 全校一次求解
python3 compare_handoff.py                   # 交接品質對照實驗
```

## 實測

| 情境 | 規模 | 結果 |
|---|---|---|
| 範例國小 | 12 班 / 19 師 / 328 單元 | **OPTIMAL，1.7 秒**，硬衝突 0 件 |
| 大型國小 | 48 班 / 75 師 / 1312 單元 | **OPTIMAL，31.7 秒**，硬衝突 0 件 |
| 分階段排課 | Phase 1 100 單元 / Phase 2 228 單元 | Phase 1 **1.1 秒**、Phase 2 十二班合計 **0.3 秒** |

| Phase 1 策略 | Phase 2 失敗次數（6 次試驗） | Phase 2 懲罰 |
|---|---|---|
| 只顧科任方便 | **6 / 6** | 150 ~ 300 |
| 為導師保留空格 | **0 / 6** | **0** |

## 原型結構

| 檔案 | 內容 |
|---|---|
| `prototype/model.py` | 領域模型、統一約束結構、前置可行性檢查 |
| `prototype/solver.py` | CP-SAT 建模與求解 |
| `prototype/phased.py` | 分階段排課與交接品質評估 |
| `prototype/compare_handoff.py` | 交接品質對照實驗 |
| `prototype/render.py` | 班級／教師／教室三視角輸出與驗證 |
| `prototype/apply_teachers.py` | 把網站匯出的 teachers.json 套回學校資料 |
| `prototype/gen_sample.py` | 產生範例學校資料 |
| `prototype/run.py` | CLI 進入點 |
| `prototype/data/sample_school.json` | 範例資料（全部設定皆為資料驅動） |
| `ui/index.html` | 畫面原型，含瀏覽器端排課引擎 |
| `ui/build_site.py` | 產生 GitHub Pages 用的完整網頁 |

## 線上操作（GitHub Pages）

**https://znxuyz.github.io/Class-Scheduling-System/**

首次啟用：GitHub repo → **Settings → Pages → Source** 選 `Deploy from a branch`，
分支選 `claude/elementary-school-scheduling-38pupq`、資料夾選 **`/docs`**，按 Save。
之後每次推送 `docs/` 都會自動更新。

**排課求解直接在瀏覽器裡跑**，不需要後端、不需要帳號、不需要資料庫。
按右上角「重新排課」約 10 秒完成，過程中畫面不會凍住，隨時可以停 ——
停下來拿到的也是一份合法課表，因為三大衝堂全程都是不變量。

## 畫面原型

`ui/index.html` 是可互動的畫面原型，五個步驟對應實際作業流程，
資料全部來自 `prototype/` 的實際求解結果（由 `prototype/export_ui.py` 匯出）：

1. **基本設定** — 節次格線（一週幾天幾節、上午節次、連堂界線）、班級（含逐班的
   不上課時段）、教室、科目，以及整份資料的備份／還原
2. **老師設定** — 建立老師、身分、鐘點上限，以及每個人的個人需求
3. **配課** — 班級 × 科目的配課矩陣，可改任課老師與節數，即時檢查鐘點與容量
4. **科任／行政排課** — Phase 1 結果，可依教師或專科教室檢視
5. **交接檢查** — 各班留給導師的空格，含「有／沒有為導師著想」的對照
6. **導師自排** — 點一堂導師的課，可放的位置會亮起來，即時檢核
7. **課表檢視與調整** — 三視角，並可手動調整：點一堂課再點目標時段，
   系統會算出所有要跟著動的課（含**別班**的），先讓你確認再套用，可復原。
   另可**列印全部班級課表**或匯出 CSV

所有設定與課表都存在瀏覽器裡，重新整理不會不見。換電腦或清瀏覽器資料就會消失，
所以「基本設定 → 資料」有整份備份的下載與還原。

### 兩套求解器，同一個模型

| | `prototype/`（Python） | 網站（JavaScript） |
|---|---|---|
| 演算法 | CP-SAT，可證明最佳性 | 貪婪初始解 + 模擬退火 |
| 執行環境 | 本機 | 瀏覽器，零後端 |
| 12 班實測成本 | **8** | **8 ~ 12**（約 10 秒） |
| 硬約束 | 0 件 | 0 件 |

硬約束（三大不衝堂、節數守恆、連堂完整性、教室型態、教師日上限）在 JS 版
是**全程維持的不變量** —— 只在合法位置之間移動與對調，所以任何時刻中止，
拿到的都是一份可用的課表，只是軟性需求還沒壓到最低。

要用 Python 版求解（規模更大、或想要最佳性保證）：

```
網站「老師設定」→ 下載 JSON
python3 prototype/apply_teachers.py ~/Downloads/teachers.json
python3 prototype/run.py --phased
```

下載在嵌入式檢視器裡會被沙箱擋掉，那裡請改用旁邊的「複製 JSON」。

```bash
cd prototype && python3 export_ui.py    # 重新求解並匯出畫面用資料
python3 ui/build_site.py                # 由 ui/index.html 產生 docs/index.html
```

`ui/index.html` 是給 Artifact 用的片段（外殼由平台補上）；
`docs/index.html` 是 GitHub Pages 用的完整網頁，由 `ui/build_site.py` 產生，
會補上 `<meta charset>`、viewport、favicon 與自己的深淺色切換鈕。
**改樣式請改 `ui/index.html`，再重新建置**，不要直接改 `docs/index.html`。
