#!/usr/bin/env python
"""把语音稿(Markdown)合成为一个 m4a。本地 Qwen3-TTS via mlx-audio(模型第一次运行时自动下载,之后不联网)。

用法:
    python tts_synthesize.py <语音稿.md> <输出.m4a> [--voice Serena] [--lang Chinese]
                             [--model mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit]
                             [--workdir <中间 wav 目录>] [--only 3]   # 只合成第 3 段,调试用

语音稿格式(见 references/audio-script-rules.md):
    # 标题                      ← 忽略
    说明段落                    ← 第一个 "## 第" 之前的内容全部忽略
    ## 第 1 段 · xxx            ← 一段 = 一个合成单位的集合
    段落一                      ← 每个空行分隔的段落单独合成一次
    段落二
合成后:段落之间插 0.6 s 静音,段与段之间插 1.2 s,ffmpeg 拼成 AAC m4a。
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

import numpy as np


def parse_script(md: str):
    """返回 [(段号, 段标题, [段落文本...]), ...]。"""
    segs, cur = [], None
    for line in md.split("\n"):
        m = re.match(r"^## 第\s*(\d+)\s*段\s*[·:：-]?\s*(.*)$", line)
        if m:
            cur = (int(m.group(1)), m.group(2).strip(), [])
            segs.append(cur)
            continue
        if cur is None or line.startswith("#"):
            continue
        cur[2].append(line)
    out = []
    for n, title, lines in segs:
        paras, buf = [], []
        for l in lines:
            if l.strip():
                buf.append(l.strip())
            elif buf:
                paras.append(" ".join(buf)); buf = []
        if buf:
            paras.append(" ".join(buf))
        out.append((n, title, paras))
    return out


def write_wav(path: Path, audio: np.ndarray, sr: int):
    """用标准库 wave 写 16-bit 单声道 PCM,不引入 soundfile 依赖。"""
    import wave
    pcm = np.clip(audio, -1.0, 1.0)
    pcm = (pcm * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def read_sr(path: Path) -> int:
    import wave
    with wave.open(str(path), "rb") as w:
        return w.getframerate()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script"); ap.add_argument("out")
    ap.add_argument("--voice", default="Serena")
    ap.add_argument("--lang", default="Chinese")
    ap.add_argument("--model", default="mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--only", type=int, default=None)
    ap.add_argument("--para_gap", type=float, default=0.6)
    ap.add_argument("--seg_gap", type=float, default=1.2)
    a = ap.parse_args()

    script = Path(a.script); out = Path(a.out)
    import tempfile
    work = Path(a.workdir) if a.workdir else Path(tempfile.gettempdir()) / "lecture-tts" / out.stem   # 中间 wav 不放进课程文件夹
    work.mkdir(parents=True, exist_ok=True)
    text_all = script.read_text(encoding="utf-8")
    segs = parse_script(text_all)
    # 句长提醒(audio-script-rules §2):超过 35 个中文字的句子听起来会吃力,先报出来再合成
    long_s = [s for s in re.split(r"[。?？!！]", text_all.split("## 第", 1)[-1]) if len(re.findall(r"[\u4e00-\u9fff]", s)) > 35]
    if long_s:
        print(f"提醒:{len(long_s)} 句超过 35 个中文字,建议拆短(前 3 句):", [s.strip()[:40] for s in long_s[:3]])
    if a.only:
        segs = [s for s in segs if s[0] == a.only]
    if not segs:
        sys.exit("语音稿里没有 '## 第 N 段' 标题")

    from mlx_audio.tts.utils import load_model
    model = load_model(a.model)

    pieces = []  # (wav 路径, 之后的静音秒数)
    sr = None
    total_chars = 0
    for n, title, paras in segs:
        print(f"== 第 {n} 段 {title}: {len(paras)} 个段落, {sum(len(p) for p in paras)} 字符")
        for i, text in enumerate(paras, 1):
            wav = work / f"seg{n:02d}_p{i:02d}.wav"
            total_chars += len(text)
            if not wav.exists():
                chunks = []
                for r in model.generate(text, voice=a.voice, lang_code=a.lang):
                    chunks.append(np.array(r.audio, dtype=np.float32))
                    sr = getattr(r, "sample_rate", sr) or sr
                if sr is None:
                    sys.exit("模型没有返回采样率")
                write_wav(wav, np.concatenate(chunks), sr)
            pieces.append((wav, a.para_gap))
        pieces[-1] = (pieces[-1][0], a.seg_gap)

    if sr is None:  # 全部命中缓存时从文件读
        sr = read_sr(pieces[0][0])

    # 静音文件 + concat 列表
    sil = {}
    for _, gap in pieces:
        if gap not in sil:
            p = work / f"silence_{gap}.wav"
            write_wav(p, np.zeros(int(sr * gap), dtype=np.float32), sr)
            sil[gap] = p
    lst = work / "concat.txt"
    with lst.open("w") as f:
        for wav, gap in pieces:
            f.write(f"file '{wav.resolve()}'\nfile '{sil[gap].resolve()}'\n")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
           "-c:a", "aac", "-b:a", "96k", str(out)]
    subprocess.run(cmd, check=True)
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                         capture_output=True, text=True).stdout.strip()
    print(f"完成: {out}  时长 {float(dur)/60:.1f} 分钟, 文本 {total_chars} 字符, 中间文件在 {work}")


if __name__ == "__main__":
    main()
