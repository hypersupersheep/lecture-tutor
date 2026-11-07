#!/usr/bin/env python3
"""手写风复习笔记: 把简化标记写的 .md 渲染成网格纸 A4 PDF(可直接导入 Notability)。

用法:
  python render_handwritten.py notes.md --pdf out.pdf [--preview page1.png] [--grid 5]

原理: 标记 → HTML(模板 handwritten_template.html) → 本地起一个临时 HTTP 服务 →
用临时 profile 的无头 Chrome 打开(DevTools 协议实时等页面里的公式/字体/分页做完) → 打印 PDF。
字体和 KaTeX 从 CDN 加载, 需要联网。不碰用户自己的 Chrome 资料。
"""
import argparse, base64, functools, os, html, http.server, json, re, shutil, socket, subprocess, tempfile, threading, time, urllib.request
from pathlib import Path

import websocket  # pip install websocket-client

HERE = Path(__file__).resolve().parent
def _find_chrome():
    """Chrome 的位置:先看环境变量 CHROME_PATH,再找 macOS 默认位置和 PATH 里的 chrome / chromium。"""
    cands = [os.environ.get("CHROME_PATH"), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    cands += [shutil.which(n) for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")]
    for c in cands:
        if c and Path(c).exists():
            return c
    raise SystemExit("找不到 Chrome:装 Google Chrome,或者用环境变量 CHROME_PATH 指向它")


CHROME = _find_chrome()


# ---------- 1. 标记 → HTML 块 ----------
def inline(s: str) -> str:
    """行内: 先把 $公式$ 换成占位符保护起来, 转义并做荧光笔/强调替换后再放回(荧光笔可以包住公式)。"""
    maths = []

    def keep(m):
        maths.append(html.escape(m.group(0), quote=False))  # KaTeX 读 textContent, 转义不影响公式
        return f"\x00{len(maths) - 1}\x00"

    # 公式 = 没被反斜杠转义的一对 $ 之间(公式里可以有 \$); 公式外的 \$ 是真的美元符号
    t = html.escape(re.sub(r"(?<!\\)\$(?:\\\$|[^$\n])+?(?<!\\)\$", keep, s), quote=False)
    t = t.replace("\\$", '<i class="lat nomath">$</i>')
    t = re.sub(r"(£|&lt;|&gt;|–)", r'<i class="lat">\1</i>', t)  # 小赖体的 £ < > – 字形难认, 换英文手写体
    t = re.sub(r"==(.+?)==", r'<span class="hl">\1</span>', t)
    t = re.sub(r"\+\+(.+?)\+\+", r'<span class="hl2">\1</span>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r'<span class="em">\1</span>', t)
    return re.sub(r"\x00(\d+)\x00", lambda m: maths[int(m.group(1))], t)


def parse(text: str):
    blocks, tag, box = [], "", None
    title_done = False
    for lineno, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        star = s.startswith("★")
        if star:
            s = s[1:].strip()
        sc = " star" if star else ""
        if s.startswith("@tag "):
            tag = s[5:].strip(); continue
        if s.startswith("# ") and not title_done:
            blocks.append(f'<div class="title{sc}">{inline(s[2:].strip())}</div>'); title_done = True; continue
        if s == "===":
            blocks.append('<div class="pagebreak"></div>'); continue
        if s.startswith(":::"):
            if box is None:
                box = {"title": s[3:].strip(), "rows": [], "sc": sc}
            else:
                head = f'<div class="row boxtitle">{inline(box["title"])}</div>' if box["title"] else ""
                blocks.append(f'<div class="dash{box["sc"]}">{head}{"".join(box["rows"])}</div>'); box = None
            continue
        target = box["rows"] if box is not None else blocks
        if s == "":
            target.append('<div class="row"></div>')
        elif s.startswith("## "):
            target.append(f'<div class="row h2{sc}">{inline(s[3:])}</div>')
        elif s.startswith("$$"):
            m = re.match(r"^\$\$(.+?)\$\$\s*(?:<<\s*(.*))?$", s)
            if not m:
                raise SystemExit(f"第 {lineno} 行: 展示公式要写成一行 $$...$$, 可选 << 批注")
            formula = html.escape(m.group(1).strip(), quote=False)
            anno = f'<span class="anno">{inline(m.group(2).strip())}</span>' if m.group(2) else ""
            target.append(f'<div class="fbox{sc}"><span class="box">$\\displaystyle {formula}$</span>{anno}</div>')
        elif s.startswith("!! "):
            target.append(f'<div class="sticky-row{sc}"><span class="sticky">{inline(s[3:])}</span></div>')
        elif s.startswith(">> "):
            target.append(f'<div class="row red{sc}">{inline(s[3:])}</div>')
        elif s.startswith("> "):
            target.append(f'<div class="row pencil{sc}">{inline(s[2:])}</div>')
        elif s.startswith("- "):
            target.append(f'<div class="row li{sc}">{inline(s[2:])}</div>')
        else:
            target.append(f'<div class="row{sc}">{inline(s)}</div>')
    if box is not None:
        raise SystemExit("::: 虚线框没有闭合")
    return blocks, tag


# ---------- 2. 无头 Chrome(DevTools 协议) ----------
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def render(html_path: Path, pdf: Path, preview: Path | None, preview_dir: Path | None = None, timeout=180):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(html_path.parent)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    prof, port = tempfile.mkdtemp(prefix="hw-chrome-"), free_port()
    proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", f"--user-data-dir={prof}", "--no-first-run",
                             f"--remote-debugging-port={port}", "--remote-debugging-address=127.0.0.1",
                             "--remote-allow-origins=http://127.0.0.1", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        tabs = None
        for _ in range(100):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")); break
            except Exception:
                time.sleep(0.2)
        ws = websocket.create_connection([t for t in tabs if t["type"] == "page"][0]["webSocketDebuggerUrl"],
                                         origin="http://127.0.0.1", timeout=300)
        n = [0]

        def call(method, **params):
            n[0] += 1
            ws.send(json.dumps({"id": n[0], "method": method, "params": params}))
            while True:  # 跳过事件, 只取本次调用的返回
                msg = json.loads(ws.recv())
                if msg.get("id") == n[0]:
                    if "error" in msg:
                        raise RuntimeError(f"{method}: {msg['error']}")
                    return msg["result"]

        def ev(js):
            return call("Runtime.evaluate", expression=js, returnByValue=True)["result"].get("value")

        call("Page.enable"); call("Runtime.enable")
        call("Emulation.setDeviceMetricsOverride", width=900, height=1200, deviceScaleFactor=2, mobile=False)
        call("Page.navigate", url=f"http://127.0.0.1:{srv.server_address[1]}/{html_path.name}")
        t0 = time.time()
        while not str(ev("(document.getElementById('status')||{textContent:''}).textContent")).startswith("done"):
            if time.time() - t0 > timeout:
                raise SystemExit("渲染超时(字体/KaTeX 没加载完? 检查网络)")
            time.sleep(0.5)
        status = ev("document.getElementById('status').textContent")
        r = call("Page.printToPDF", printBackground=True, preferCSSPageSize=True, displayHeaderFooter=False)
        pdf.write_bytes(base64.b64decode(r["data"]))
        rects = ev("[...document.querySelectorAll('.page')].map(p => { const b = p.getBoundingClientRect(); return [b.x, b.y + window.scrollY, b.width, b.height]; })")
        targets = [(0, preview)] if preview else []
        if preview_dir:
            preview_dir.mkdir(parents=True, exist_ok=True)
            targets += [(i, preview_dir / f"page-{i + 1}.png") for i in range(len(rects))]
        for i, path in targets:  # 每页截一张: 交付前逐页检查用
            x, y, w, h = rects[i]
            shot = call("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                        clip={"x": x, "y": y, "width": w, "height": h, "scale": 1})
            path.write_bytes(base64.b64decode(shot["data"]))
        return status
    finally:
        proc.terminate(); proc.wait(timeout=15); srv.shutdown(); shutil.rmtree(prof, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description="手写风网格纸复习笔记 → A4 PDF")
    ap.add_argument("notes", type=Path); ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--preview", type=Path, help="第一页 PNG 预览")
    ap.add_argument("--preview-dir", type=Path, help="每一页各存一张 page-N.png(逐页检查用)")
    ap.add_argument("--grid", type=float, default=5.0, help="网格边长 mm(默认 5)")
    a = ap.parse_args()
    blocks, tag = parse(a.notes.read_text(encoding="utf-8"))
    tpl = (HERE / "handwritten_template.html").read_text(encoding="utf-8")
    page = (tpl.replace("__GRID__", f"{a.grid:g}").replace("__TAG__", json.dumps(tag, ensure_ascii=False))
               .replace("__BLOCKS__", "\n".join(blocks)))
    work = Path(tempfile.mkdtemp(prefix="hw-page-"))
    try:
        (work / "page.html").write_text(page, encoding="utf-8")
        status = render(work / "page.html", a.pdf.resolve(), a.preview.resolve() if a.preview else None,
                        a.preview_dir.resolve() if a.preview_dir else None)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(status, "->", a.pdf)
    if "overflow=0" not in status:
        print("警告: 有公式缩到 60% 仍超宽或被挤成两行, 把它拆成两个 $$...$$")


if __name__ == "__main__":
    main()
