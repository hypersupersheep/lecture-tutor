---
name: handwritten-notes-pdf
description: Use when the user wants a handwritten-style (手写风 / 手写版) review PDF of lecture or course notes on grid paper, to read or annotate in Notability on iPad — including the default follow-up after a lecture-tutor 讲解 note, or requests like "手写版", "手写笔记", "网格纸笔记", "Notability 复习版".
---

# handwritten-notes-pdf

## Overview

把一节课的要点写成一份简化标记的 `.md`,脚本渲染成 A4 网格纸 PDF:小赖手写体,公式用 KaTeX 排版、蓝墨水颜色(保证不写错),配荧光笔、红笔批注、便利贴。PDF 可以直接导入 Notability、GoodNotes 这类 App,在上面继续用笔写。

**这是复习版,不是讲解笔记的手写誊抄。** 只挑老师强调的要点、关键公式、例题结论和易错点。

## When to use

- lecture-tutor 的讲解定稿后,默认做一份(见该 skill 第 8 步)。
- 用户要某份笔记的"手写版 / 网格纸版"。
- 不用于:要用户自己的笔迹(那是 iPad 备忘录的"粘贴为手写");要可编辑的 Word 或 Docs。

## 写内容

- **篇幅**:一节两小时的课写 2–4 页。每页大约 24 行,公式框占 2 行。
- **每个话题的结构**:编号要点一行 → 关键公式框 → 例子的结论 → 易错点。推导只留结论和最关键的一步。
- **取材**:只用讲解笔记里有的内容。数字、公式逐个对照讲解笔记,不重新算;记号跟课件一致。
- **标点**:中文句子用全角标点,公式内部用英文标点。不要对整个文件做标点替换,会把 `\,` 和 `:::` 改坏。

## 标记语法

| 写法 | 效果 |
|---|---|
| `@tag FIN101 · S01 · 2026-10-06` | 第一页右上角的小字 |
| `# 标题` | 第一页大标题,只用一次 |
| `## 小标题` | 蓝色小节标题 |
| 普通一行 | 黑笔写一行,可以夹 `$行内公式$` |
| `$$公式$$` | 手绘框里的展示公式,必须单独占一行 |
| `$$公式$$ << 批注` | 公式框右侧加一条斜写的红笔批注;批注不超过 15 个字,更长的单独写一行 `>>` |
| `==文字==` / `++文字++` | 黄色 / 粉色荧光笔,可以包住公式 |
| `**文字**` | 蓝笔强调 |
| `>> 文字` | 整行红笔 |
| `> 文字` | 灰色铅笔,用于补充、自问 |
| `- 文字` | 短横线列表 |
| `!! 文字` | 黄色便利贴,写易错点 |
| `::: 标题` … `:::` | 虚线框,用于课堂讨论、例题 |
| 行首加 `★` | 页边加一颗红星,标重点 |
| 空行 / `===` | 空一行 / 强制换页 |
| `\$` | 真正的美元符号,公式内外都这样写;单独的 `$` 会被当成公式开头 |

完整例子见 `examples/tvm-example.md`。

## 渲染

```bash
python3 <本 skill 目录>/scripts/render_handwritten.py notes.md --pdf out.pdf --preview-dir <临时目录>
```

- `<本 skill 目录>` 是加载 skill 时显示的 Base directory(手动安装时是 `~/.claude/skills/handwritten-notes-pdf`)。
- 需要联网:字体和 KaTeX 从 CDN 加载。脚本用本机 Chrome 的无头模式和一个临时 profile,不碰你自己的 Chrome 资料。Chrome 不在默认位置时,用环境变量 `CHROME_PATH` 指定。
- 正常输出 `done pages=N overflow=0`。`overflow>0` 表示有公式缩到 60% 还是超宽,或者在框里被挤成了两行,把它拆成两个 `$$`。
- `--grid` 改网格边长,默认 5mm。
- `--preview-dir` 把每一页存成 `page-N.png`。交付前用 Read 逐页看:有没有公式断行、最后一页是不是只剩一两行(删几个空行收回去)。

## Common mistakes

- 把讲解笔记整篇搬进来,结果变成 8 页:复习版要做取舍。
- `$$` 公式跨了行:必须写在同一行里。
- 普通文字太长、自动折成两行没关系;过宽的展示公式才需要拆。
- 想要更多空白,就多写空行。不要靠 `===` 把每节都分到新的一页。
