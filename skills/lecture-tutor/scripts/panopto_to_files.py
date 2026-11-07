#!/usr/bin/env python
"""把 panopto_extract.js 的返回值(JSON)拆成工作文件。

用法:
    python -I panopto_to_files.py <extract.json> <out_dir>

<extract.json> 是浏览器 javascript_tool 返回的对象,可以是:
  - 纯 JSON 对象({"transcript": ..., "contents": [...], ...});
  - Claude Code 的 tool-results 文件(外层是 [{"type":"text","text":"<json>"}],后面可能还跟着别的东西)。
两种都能解析。输出:
  transcript.raw.txt   每行 "[m:ss] 句子"
  contents.txt         Panopto 自动章节(标题 + 时间)
  meta.txt             URL、标题、详情(含讲课日期)、时长、AI 摘要
"""
import json
import re
import sys
from pathlib import Path


def first_json(text: str):
    """从可能带尾巴的文本里取出第一个完整 JSON 值(raw_decode 会忽略尾部多余内容)。"""
    obj, _ = json.JSONDecoder().raw_decode(text.lstrip())
    return obj


def load(path: Path) -> dict:
    obj = first_json(path.read_text(encoding="utf-8"))
    # tool-results 文件:[{"type": "text", "text": "<json string>"}]
    if isinstance(obj, list) and obj and isinstance(obj[0], dict) and "text" in obj[0]:
        obj = first_json(obj[0]["text"])
    if not isinstance(obj, dict) or "transcript" not in obj:
        sys.exit("没有找到 transcript 字段:检查输入文件是不是 panopto_extract.js 的返回值")
    return obj


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    d = load(src)

    contents = [re.sub(r"^Retry Cancel ", "", c).strip() for c in d.get("contents", [])]
    (out / "contents.txt").write_text("\n".join(contents) + "\n", encoding="utf-8")
    (out / "transcript.raw.txt").write_text(d["transcript"].rstrip("\n") + "\n", encoding="utf-8")
    # 页面上的 duration 是播放器显示的剩余时间(可能是负数),真实时长按最后一句的时间算
    stamps = re.findall(r"^\[(\d+:\d\d(?::\d\d)?)\]", d["transcript"], flags=re.M)
    meta = [
        f"url: {d.get('url', '')}",
        f"title: {d.get('title', '')}",
        f"details: {d.get('details', '')}",
        f"duration_display: {d.get('duration', '')}",
        f"duration_from_transcript: {stamps[-1] if stamps else ''}",
        "ai_summary: " + " | ".join(d.get("ai", [])),
    ]
    (out / "meta.txt").write_text("\n".join(meta) + "\n", encoding="utf-8")

    n = d["transcript"].count("\n") + 1
    print(f"transcript {n} 句, 章节 {len(contents)} 个 -> {out}")
    # 讲课日期藏在 details 里,形如 (2026-10-06 16:00+01:00)
    m = re.search(r"\((\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})", d.get("details", ""))
    if m:
        print(f"lecture_date: {m.group(1)} {m.group(2)}")


if __name__ == "__main__":
    main()
