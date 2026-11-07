---
name: excalidraw-concept-map
description: Use when the user wants a hand-drawn Excalidraw overview or concept map (总览图, 概念图, 思维导图, 手绘图) of a lecture or topic to view and edit in Obsidian — including the default follow-up after a lecture-tutor 讲解 note, or any mention of Excalidraw.
---

# excalidraw-concept-map

## Overview

写一段 Mermaid 流程图,脚本用 Excalidraw 官方的 mermaid-to-excalidraw 自动排版,再把文字换成手写体、线条换成手绘风,输出 Obsidian 能直接编辑的 `.excalidraw.md` 和一张 PNG 预览。

**这张图是一节课的逻辑骨架:概念怎么一步步推到结论。它不是笔记的缩写版。**

## When to use

- lecture-tutor 的讲解定稿后,默认做一张(见该 skill 第 8 步)。
- 用户要某个话题的总览图、概念图,或者提到 Excalidraw。
- 不用于:精确的数据图表(那用 dataviz);需要排公式的推导页(那用 handwritten-notes-pdf)。

## 画什么

- **规模和方向**:8–12 个节点,用 `flowchart TD` 竖版,嵌进 Obsidian 字才不会太小。只有 3–4 个节点的直线链才用 `LR`。
- **节点**:一个节点放一个概念、方法或结论。最多 4 行,每行最多 16 个汉字,用 `<br>` 换行。
- **形状**:主链超过 6 层,就合并相邻节点,或者把旁支挂到主链两侧。PNG 宽高比保持在 1:2.5 到 2:1 之间。
- **边**:表示推出、放宽、反过来、对比。边标签最多 8 个字。边尽量只连相邻两层,跨层的长边会斜穿过别的框。
- **公式**:写纯文本,如 `e^(rt)`、`(1+r)^(−n)`。Excalidraw 不排 LaTeX,Unicode 上标字符太小,不要用。带帽子、横线的符号(R̂、x̄)手写体没有字形,写成 `R_hat`、`x_bar`,或者直接写中文名。
- **取材**:只用讲解笔记里的内容,数字逐个对照。

## 节点写法与配色

节点一律写成 `ID["文字"]:::类名`,文字必须加引号,括号、等号才不会被 Mermaid 当成语法。圆角胶囊形写成 `ID(["文字"])`。实线箭头写 `A -->|标签| B`,虚线关联写 `A -.- B`。

下面这些类名会自动配色,不用自己写 classDef:

| 类名 | 用途 | 样式 |
|---|---|---|
| `key` | 起点、核心概念 | 黄 |
| `concept` | 方法、推导 | 蓝 |
| `result` | 结论、关键公式 | 绿 |
| `contrast` | 反方向、对照 | 红 |
| `example` | 例题、课堂讨论 | 浅蓝虚线框 |
| `warn` | 易错点 | 橙底红字 |
| `note` | 非课堂的补充 | 灰 |

完整例子见 `examples/tvm-map.mmd`。

## 渲染

```bash
python3 <本 skill 目录>/scripts/render_excalidraw.py map.mmd --md <名>.excalidraw.md --png <名>.png --title "主标题" --subtitle "课程 · 课次 · 总览图"
```

- `<本 skill 目录>` 是加载 skill 时显示的 Base directory(手动安装时是 `~/.claude/skills/excalidraw-concept-map`)。
- 需要联网:库从 esm.sh 和 jsdelivr 加载。脚本用无头 Chrome 和临时 profile;Chrome 不在默认位置时,用环境变量 `CHROME_PATH` 指定。
- `.excalidraw.md` 要在装了 Excalidraw 插件的 Obsidian 里才显示成图(插件市场里搜 Excalidraw)。嵌进笔记写 `![[<名>.excalidraw]]`。
- 渲染后用 Read 打开 PNG 检查三件事:框里的字挤不挤;箭头标签有没有压到字;图是不是太宽(宽超过高的 2 倍,就改成 TD 或减少节点)。
- Mermaid 语法错误时,脚本会打印"渲染失败"和报错原文,按报错改。

## Common mistakes

- 节点文字没加引号,比如 `A[FV = PV(1+r)]`,Mermaid 会报语法错误。
- 一个节点塞一整段话,图就成了文字墙。
- 用 LR 排五层以上,图太宽,缩进笔记后字看不清。
