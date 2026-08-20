"""把 ui/index.html（為 Artifact 寫的片段）包成 GitHub Pages 用的完整網頁。

Artifact 會自動補上 <!doctype>/<head>/<body> 外殼與最小 CSS reset，所以原始檔
只寫頁面內容。GitHub Pages 不會做這件事 —— 少了 <meta charset> 中文會變亂碼，
少了 viewport 手機上會縮成一團。

另外，Artifact 由瀏覽器外殼決定深淺色（會在 <html> 蓋上 data-theme），
獨立網頁沒有這個外殼，所以這裡補一個自己的主題切換鈕。CSS 早已支援
data-theme="dark" / "light"，按鈕只要蓋上屬性就會生效。
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "ui" / "index.html"
OUT = ROOT / "docs" / "index.html"

TITLE = "國小排課系統"
DESC = "國小排課系統的畫面原型：配課鐘點檢查、科任先排、交接檢查、導師自排與三視角課表。"
SITE = "https://znxuyz.github.io/Class-Scheduling-System/"
FAVICON = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'"
    "%3E%3Ctext y='.9em' font-size='90'%3E%F0%9F%8F%AB%3C/text%3E%3C/svg%3E"
)

TOGGLE_HTML = '''<button id="theme" class="theme-btn" type="button"
   aria-label="切換淺色／深色" title="切換淺色／深色"><span aria-hidden="true">◐</span></button>'''

TOGGLE_CSS = '''
/* 獨立網頁自己的主題切換（Artifact 版本由外殼提供，不需要這個） */
.theme-btn{
  appearance:none; background:var(--surface); color:var(--ink-2);
  border:1px solid var(--line-2); border-radius:5px; width:32px; height:32px;
  font-size:15px; line-height:1; cursor:pointer; flex:none; align-self:center;
}
.theme-btn:hover{border-color:var(--accent); color:var(--accent)}
.theme-btn:focus-visible{outline:2px solid var(--accent); outline-offset:1px}
.head-right{display:flex; align-items:center; gap:16px; flex-wrap:wrap}
'''

TOGGLE_JS = '''
(function(){
  var root = document.documentElement, btn = document.getElementById('theme');
  var saved = null;
  try{ saved = localStorage.getItem('theme'); }catch(e){}
  if(saved) root.setAttribute('data-theme', saved);
  btn.addEventListener('click', function(){
    // 沒選過就以目前實際呈現的顏色為準，切到相反的那一邊
    var cur = root.getAttribute('data-theme');
    if(!cur) cur = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    var next = cur === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try{ localStorage.setItem('theme', next); }catch(e){}
  });
})();
'''


def build() -> None:
    src = SRC.read_text(encoding="utf-8")

    # 1. 主題切換鈕的樣式，接在既有 <style> 尾端
    src = src.replace("@media(prefers-reduced-motion:reduce)",
                      TOGGLE_CSS + "@media(prefers-reduced-motion:reduce)", 1)

    # 2. 把統計數字與切換鈕包成同一組，放在標題列右側
    src = src.replace(
        '  <div class="stats" id="stats"></div>\n',
        f'  <div class="head-right">\n   <div class="stats" id="stats"></div>\n   {TOGGLE_HTML}\n  </div>\n',
        1,
    )
    assert "head-right" in src, "找不到標題列，無法插入主題切換鈕"

    # 3. 主題切換的行為接在最後一段 script 尾端（此時 DOM 已建好）
    idx = src.rfind("</script>")
    assert idx != -1
    src = src[:idx] + TOGGLE_JS + src[idx:]

    head = f'''<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{DESC}">
<meta name="color-scheme" content="light dark">
<link rel="icon" href="{FAVICON}">
<meta property="og:type" content="website">
<meta property="og:title" content="{TITLE}">
<meta property="og:description" content="{DESC}">
<meta property="og:url" content="{SITE}">
</head>
<body>
'''
    # 原始檔的 <title> 與字型 <link> 屬於 head，搬進去
    m = re.match(r"(\s*<title>.*?</title>\s*(?:<link[^>]*>\s*)*)", src, re.S)
    assert m, "找不到 <title> 與字型連結"
    head_bits, rest = m.group(1).strip(), src[m.end():]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(head.replace("</head>", head_bits + "\n</head>") + rest + "\n</body>\n</html>\n",
                   encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}  ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    build()
