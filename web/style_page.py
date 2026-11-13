"""Причёсывает страницу, которую собрал pygbag: тёмный фон и свой текст вместо зелёной плашки.

Запускается в GitHub Actions после сборки:  python web/style_page.py yolka/build/web
Ничего не найдёт — ничего не сломает: страница просто останется стандартной.
"""
import shutil
import sys
from pathlib import Path

STYLE = """
<style>
  html, body { background: #06080f !important; }
  #infobox {
    background: transparent !important; color: #ffc860 !important;
    font: 16px Consolas, Menlo, "DejaVu Sans Mono", monospace !important;
    left: 50% !important; top: 50% !important; transform: translate(-50%, -50%);
    text-align: center; white-space: nowrap;
  }
  #status { color: #5c667e !important; font: 13px Consolas, Menlo, monospace !important; }
  progress { accent-color: #ffc860; }
</style>
"""
TEXTS = {
    "Loading, please wait ...": "ёлка загружается…",
    "Ready to start ! Please click/touch page": "кликни, чтобы начать",
    'f"installing {pkg}"': 'f"ставлю {pkg}…"',
    "Downloading...": "загрузка…",
}

web = Path(sys.argv[1])
page = web / "index.html"
html = page.read_text(encoding="utf-8")
for old, new in TEXTS.items():
    html = html.replace(old, new)
html = html.replace("</head>", STYLE + "</head>", 1)
page.write_text(html, encoding="utf-8")

icon = Path(__file__).with_name("favicon.png")
if icon.exists():
    shutil.copyfile(icon, web / "favicon.png")
print("page styled:", page)
