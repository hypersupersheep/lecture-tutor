#!/usr/bin/env python3
"""Mermaid 流程图 → Excalidraw 手绘总览图(Obsidian 可编辑的 .excalidraw.md + PNG 预览)。

用法:
  python render_excalidraw.py map.mmd --md out.excalidraw.md --png out.png \
      [--title "标题"] [--subtitle "副标题"] [--excalidraw out.excalidraw] [--font-size 20]

原理: Excalidraw 官方的 mermaid-to-excalidraw 负责自动排版, 再把文字换成手写体、线条换成手绘,
用临时 profile 的无头 Chrome 跑完后导出。库从 CDN(esm.sh / jsdelivr)加载, 需要联网。
"""
import argparse, base64, functools, os, http.server, json, re, shutil, socket, subprocess, tempfile, threading, time, urllib.request
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

# 固定配色: 节点用 :::名字 套用; Mermaid 里没自己定义的才自动补上
PALETTE = {
    "key":      "fill:#ffec99,stroke:#1e1e1e",                          # 核心概念 / 起点(黄)
    "concept":  "fill:#a5d8ff,stroke:#1e1e1e",                          # 方法 / 推导(蓝)
    "result":   "fill:#b2f2bb,stroke:#1e1e1e",                          # 结论 / 公式(绿)
    "contrast": "fill:#ffc9c9,stroke:#1e1e1e",                          # 反向 / 对照(红)
    "example":  "fill:#e7f5ff,stroke:#495057,stroke-dasharray:6 4",     # 例题 / 课堂讨论(虚线)
    "warn":     "fill:#ffd8a8,stroke:#e03131,color:#e03131",            # 易错(橙底红字)
    "note":     "fill:#f1f3f5,stroke:#868e96,color:#495057",            # 补充 / 非课堂(灰)
}
WARNING = ("==⚠  Switch to EXCALIDRAW VIEW in the MORE OPTIONS menu of this document. ⚠== You can decompress Drawing data "
           "with the command palette: 'Decompress current Excalidraw file'. For more info check in plugin settings under 'Saving'")


def add_palette(mmd: str) -> str:
    used = set(re.findall(r":::(\w+)", mmd)) | set(re.findall(r"^\s*class\s+[\w,\s]+?\s+(\w+)\s*;?\s*$", mmd, re.M))
    defined = set(re.findall(r"^\s*classDef\s+(\w+)", mmd, re.M))
    extra = [f"  classDef {k} {v}" for k, v in PALETTE.items() if k in used and k not in defined]
    return mmd.rstrip() + ("\n" + "\n".join(extra) if extra else "") + "\n"


def obsidian_md(scene: dict) -> str:
    """按 Obsidian Excalidraw 插件 2.x 的文件格式写: 头部 + Text Elements(标题下不能空行) + json 绘图区。"""
    lines = ["---", "", "excalidraw-plugin: parsed", "tags: [excalidraw]", "", "---", WARNING, "", "",
             "# Excalidraw Data", "", "## Text Elements"]
    for e in scene["elements"]:
        if e["type"] == "text" and not e.get("isDeleted"):
            lines += [f'{e.get("originalText") or e["text"]} ^{e["id"]}', ""]
    lines += ["%%", "## Drawing", "```json", json.dumps(scene, ensure_ascii=False, indent="\t"), "```", "%%", ""]
    return "\n".join(lines)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def run_page(html_path: Path, png: Path | None, timeout=240):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(html_path.parent)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    prof, port = tempfile.mkdtemp(prefix="exc-chrome-"), free_port()
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
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == n[0]:
                    if "error" in msg:
                        raise RuntimeError(f"{method}: {msg['error']}")
                    return msg["result"]

        def ev(js):
            return call("Runtime.evaluate", expression=js, returnByValue=True)["result"].get("value")

        call("Page.enable"); call("Runtime.enable")
        call("Emulation.setDeviceMetricsOverride", width=1800, height=1200, deviceScaleFactor=1.5, mobile=False)
        call("Page.navigate", url=f"http://127.0.0.1:{srv.server_address[1]}/{html_path.name}")
        t0 = time.time()
        while True:
            st = str(ev("(document.getElementById('status')||{textContent:''}).textContent"))
            if st.startswith("done"):
                break
            if st == "error":
                raise SystemExit("渲染失败: " + str(ev("document.getElementById('err').textContent"))[:1500])
            if time.time() - t0 > timeout:
                raise SystemExit("渲染超时(CDN 没加载完? 检查网络)")
            time.sleep(0.5)
        scene = json.loads(ev("document.getElementById('scene').textContent"))
        if png:
            x, y, w, h = ev("(() => { const b = document.querySelector('#out svg').getBoundingClientRect(); return [b.x, b.y, b.width, b.height]; })()")
            call("Emulation.setDeviceMetricsOverride", width=int(x + w + 2), height=int(y + h + 2), deviceScaleFactor=1.5, mobile=False)
            shot = call("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                        clip={"x": x, "y": y, "width": w, "height": h, "scale": 1})
            png.write_bytes(base64.b64decode(shot["data"]))
        return st, scene
    finally:
        proc.terminate(); proc.wait(timeout=15); srv.shutdown(); shutil.rmtree(prof, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description="Mermaid → Excalidraw 手绘总览图")
    ap.add_argument("mermaid", type=Path)
    ap.add_argument("--md", type=Path, required=True, help="Obsidian 用的 .excalidraw.md")
    ap.add_argument("--png", type=Path, help="PNG 预览")
    ap.add_argument("--excalidraw", type=Path, help="可选: 纯 JSON .excalidraw(拖进 excalidraw.com)")
    ap.add_argument("--title", default=""); ap.add_argument("--subtitle", default="")
    ap.add_argument("--font-size", type=int, default=20)
    a = ap.parse_args()
    if not a.md.name.endswith(".excalidraw.md"):
        raise SystemExit("--md 文件名要以 .excalidraw.md 结尾, Obsidian 插件才认")
    cfg = {"mermaid": add_palette(a.mermaid.read_text(encoding="utf-8")), "title": a.title,
           "subtitle": a.subtitle, "fontSize": a.font_size}
    page = (HERE / "excalidraw_template.html").read_text(encoding="utf-8").replace(
        "__CFG__", json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/"))
    work = Path(tempfile.mkdtemp(prefix="exc-page-"))
    try:
        (work / "page.html").write_text(page, encoding="utf-8")
        for attempt in range(3):  # CDN 偶尔取不到模块("Failed to fetch"), 整页重来最多 3 次
            try:
                status, scene = run_page(work / "page.html", a.png.resolve() if a.png else None)
                break
            except SystemExit as e:
                if "Failed to fetch" not in str(e) or attempt == 2:
                    raise
                print(f"CDN 加载失败, 第 {attempt + 2} 次重试…"); time.sleep(3)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    a.md.write_text(obsidian_md(scene), encoding="utf-8")
    if a.excalidraw:
        a.excalidraw.write_text(json.dumps(scene, ensure_ascii=False), encoding="utf-8")
    print(status, "->", a.md)


if __name__ == "__main__":
    main()
