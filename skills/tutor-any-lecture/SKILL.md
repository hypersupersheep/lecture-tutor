---
name: lecture-tutor
description: Use when the user asks for a lecture recording to be explained, turned into study notes, a self-test, or an audio lesson (e.g. "讲一下 COURSE101 第 4 周", "把这节课的录像整理成讲解", "做个语音版"), or when an agent must locate a Panopto / Moodle recording and read its transcript.
---

# lecture-tutor

## Overview

把一节课(Panopto 录像 + 课件)变成一份**忠于老师原话、段落为主、标题很少**的中文讲解笔记,附自测题,按需做语音版。核心原则:**正文只写老师讲过的,我加的和存疑的分开标;写出来的是文章,不是提纲。** 已在金融、随机过程、统计机器学习几门课的真实录像上跑通。

讲解笔记和预习笔记是两种文体:预习笔记要让人不上课也能高效自学,所以体系化、覆盖全;讲解笔记跟随课堂节奏,抓老师的要点和精辟之处。本 skill 只产出后者——不把讲解写成教科书,不按课件重排老师的顺序去"补全体系"。

## When to use

- 用户要"讲一下 / 整理 / 复盘"某门课的某节课、某个录像;要自测题;要语音版。
- 另一个 agent 需要找到某节课的录像并拿到转写。
- 不用于:交作业、答 quiz、发帖、写邮件;处理用户无权访问的录像。

**在 Cowork 里运行时,开工前先读 [references/cowork.md](references/cowork.md)**:文件夹要先连接,shell 在 Linux 虚拟机里,语音合成、手写版和总览图要回 Claude Code 做。在 Claude Code 里不用看。

## 配置(第一次用之前)

读 `~/.config/lecture-tutor/config.yaml`。没有这个文件就停下,请用户把本 skill 目录下的 `config.example.yaml` 复制过去并填好(放在 skill 目录外面,更新 skill 时不会被覆盖):

| 字段 | 含义 |
|---|---|
| `course_root` | 课程资料根目录;每门课一个文件夹,课件按周放在 `<folder>/weekN/` |
| `vault_root` | Obsidian vault 里放课程笔记的文件夹;不用 Obsidian 就留空,只存课程文件夹 |
| `python` | 装好 `requirements.txt` 的 Python 解释器 |
| `moodle_url`、`panopto_url` | 学校 Moodle 和 Panopto 的地址 |
| `courses` | 每门课的 `code`、`moodle_id`、`folder`、`numbering`:`week` 是一周几节合成一份(编号 `W04`),`session` 是每节一份(编号 `S01`) |

下文的 `<course_root>`、`<vault_root>`、`<python>`、`<课次>` 都按这里的值替换。

## 流程

1. **定位课程**:课程代码 → `config.yaml` 里该科的 `moodle_id` 和 `folder`。课件在 `<course_root>/<folder>/weekN/`,这些文件只读。`weekN/` 里没有这节课的 slides 或讲义时**不要自己去 Moodle 下**,告诉用户先把课件放进去。
2. **找录像**:浏览器工具开 Moodle 课程页,找录像入口(LTI 活动)或 Panopto 区块,进 viewer。遇到登录页就停下请用户登录,不输密码或 MFA。细节、选择器、各种异常见 [references/panopto.md](references/panopto.md)。
3. **取转写**:在 viewer 页用 javascript_tool 执行 `scripts/panopto_extract.js`(只读 DOM),把返回值存成 JSON,再跑 `<python> -I scripts/panopto_to_files.py <json> <workdir>` 得到 `transcript.raw.txt`、`contents.txt`、`meta.txt`。页面没有转写时,先问用户要不要下载录像本地转写(mlx-whisper),每次都问。
4. **读材料**:全文读转写、课件文本(pdfplumber)、课程信息。整理四样东西再动笔:老师的话题切换点(参考 `contents.txt`)、课件逐页清单、转写误听清单(对照课件)、课件里没讲到的页。
5. **写讲解**:按 [references/writing-rules.md](references/writing-rules.md) 的契约写。先把要引用的老师原话抽到工作目录的 `quotes.md`(带出处),再围绕引文写正文;引文是证据,讲解是主体。
6. **自检**:`bash scripts/note_stats.sh <讲解.md>` 看形态红线;按课件逐页回查每个定义、公式、例子落在笔记哪里;归于老师的每句话都要有 `(slide N)` 或 `(mm:ss)`。
7. **交付(按周存放)**:
   - **先定周次 N**:就是这节课课件所在的 `weekN/`。
   - **结构**:预习和基于录像、课后复习的产出分开,图不和笔记混放。
     ```
     Obsidian:<vault_root>/<folder>/weekN/
     ├── 预习/                              预习笔记,不是本 skill 的产出
     ├── lecture_wN/                        基于录像和课后复习的成品都放这里
     │   ├── <课次>-讲解-<英文主题>.md
     │   ├── <课次>-习题.md                 习题讲解单独成文时才有
     │   ├── <课次>-语音.m4a
     │   ├── <课次>-手写版.pdf
     │   ├── <课次>-总览图.excalidraw.md
     │   └── <课次>-思维导图.excalidraw.md
     └── 截图/                              笔记里嵌入的所有图

     课程文件夹:<course_root>/<folder>/weekN/笔记/
     ├── 预习/
     ├── lecture_wN/                        <课次>_讲解.md、_习题.md、_语音.m4a、_手写版.pdf、_总览图.png、_思维导图.png
     └── 源文件/                            转写、章节表、meta、语音稿、标记稿、Mermaid、脚本、截图对照表
     ```
   - **命名**:
     - 文件名不带课程代码,否则太长;要分享时再加。
     - `<课次>` 按 `numbering` 写成 `W04` 或 `S01`。这个前缀要留:标签页和反向链接只显示文件名,没有它分不清是哪一周。英文主题取老师这节课的标题。
     - 老师讲题的视频整理成的笔记叫"习题",m4a 叫"语音"。
     - 截图按内容命名,如 `Theorem2.2-1-陈述与唯一性.jpg`、`Ex1.10-2-接受拒绝算法.jpg`,同一主题多张时用序号排好。不带课程和周次;来源和时间戳记进 `源文件/<课次>_截图对照.tsv`。
     - 新文件写入前全库查重。跨课重名(两门课都有 S01)时,链接写从库根开始的完整路径并加别名,如 `[[Courses/course101/week1/lecture_w1/S01-总览图.excalidraw|总览图]]`。
   - 讲解存两处,内容一致。`weekN/` 根目录只放课件,生成物一律进 `笔记/`。原始转写、章节表、meta 的文件名:`<课次>_transcript_panopto_raw.txt`、`<课次>_panopto_chapters.txt`、`<课次>_panopto_meta.txt`。
   - 把成品发给用户,等验收再定稿。
8. **手写复习版 + 总览图**(讲解定稿后默认做):**REQUIRED SUB-SKILL:** handwritten-notes-pdf 和 excalidraw-concept-map。
   - 取材:都从讲解笔记来。源文件写进 `weekN/笔记/源文件/`:`<课次>_手写版.md`(标记语法)和 `<课次>_总览图.mmd`(Mermaid)。渲染出的 `<课次>_总览图.excalidraw.md` 也放这里。
   - 存放:按第 7 步的结构。Obsidian `lecture_wN/` 放 `<课次>-手写版.pdf`、`<课次>-总览图.excalidraw.md`;课程文件夹 `笔记/lecture_wN/` 放 `<课次>_手写版.pdf`、`<课次>_总览图.png`。
   - 嵌入:两份讲解(Obsidian 和课程文件夹)都加,保持两份一致。位置在开头说明块(和音频)之后、`## 目录` 之前:
     ```
     手写复习版(网格纸 PDF,可导入 Notability):[[<课次>-手写版.pdf]]

     ![[<课次>-总览图.excalidraw]]
     ```
   - 思维导图(可选):和总览图分工,总览图讲讲课的逻辑顺序,思维导图讲概念的层级和关系。节点多、要画跨列关系线时自己算坐标,不走 Mermaid 自动排版。每个节点的链接写进 `.excalidraw.md` 的 `## Element Links`(在 `%%` 之外才进反向链接),形如 `<8位id>: [[文件名#小节]]`。
   - 把 PDF 和总览图 PNG 发给用户。
9. **语音版**(用户要时):按 [references/audio-script-rules.md](references/audio-script-rules.md) 先写 `weekN/笔记/源文件/<课次>_语音稿.md`,再 `<python> scripts/tts_synthesize.py <语音稿> <输出.m4a> --voice Serena --workdir <临时目录>/tts` 本地合成(Qwen3-TTS),按该文件 §4 用 mlx-whisper 回转抽查。m4a 放 `weekN/笔记/lecture_wN/<课次>_语音.m4a`,再复制一份到 Obsidian 的 `lecture_wN/`,命名为 `<课次>-语音.m4a`,在笔记里用 `![[<课次>-语音.m4a]]` 嵌入。

## 铁律

- 不输密码/MFA,不抓 token 或 cookie;Moodle 只读;Panopto 页面只读 DOM,不点 Edit、Cuts、Streams、Download 之类按钮。
- 下载录像文件每次先问用户;老师关了下载的录像不绕过去抓流。
- 录像、转写、笔记只供用户个人学习,不外传。
- Python 用 `config.yaml` 里的解释器;读取从网上拿到的文件时加 `-I`。
- 课程文件夹里的文件只增不删。成品放 `weekN/笔记/lecture_wN/`,原始材料放 `weekN/笔记/源文件/`;`weekN/` 根目录留给课件。

## Quick reference

| 环节 | 用什么 |
|---|---|
| 课程代码 → Moodle id、文件夹 | `config.yaml` |
| 录像入口 | Moodle 课程页的 LTI 活动或 Panopto 区块 → `<panopto_url>/Panopto/Pages/Viewer.aspx?id=…` |
| 转写、章节、AI 摘要、讲课日期 | `scripts/panopto_extract.js` → `scripts/panopto_to_files.py` |
| 课件文本 | `pdfplumber` |
| 笔记形态自检 | `scripts/note_stats.sh` |
| 写作契约 | `references/writing-rules.md` |
| 语音稿与合成 | `references/audio-script-rules.md` |
| 手写复习版 PDF(网格纸) | handwritten-notes-pdf skill |
| 手绘总览图(Excalidraw) | excalidraw-concept-map skill |
| 在 Cowork 里运行 | `references/cowork.md` |

## Common mistakes

对照实验(同样材料、不给规则)里出现过的毛病,写之前先看一遍:

- 写成提纲:标题带编号(1.1、3.4)、每段开头一个加粗引导词、推理过程用列表承载。契约里规定了每一节由什么组成,照契约写。
- 改老师的记号(把本金 $P$ 改成 $F$ 以免和价格 $P(t,T)$ 冲突)。记号跟课件走;冲突写进存疑框,正文不改。
- 加老师没讲的板块:"速览""面试向问答""下周待办"。课件里没讲到的页只在"没讲到的部分"一节提一句。
- 老师只点名了一种推导,笔记补了三种。补老师那一种,放在补充框里。
- 转写误听照抄("40 years"、"80%")。数字和专有名词一律对照课件,误听进纠错表。
