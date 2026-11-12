#!/usr/bin/env bash
# 讲解笔记的形态自检。用法: bash note_stats.sh <讲解.md>
# 只报数,不改文件。交付前跑一次,红线亮了就回去改(契约见 references/writing-rules.md)。
# 口径: "字"= 中文字符数; 引文 = 成对英文直引号里 ≥15 个字符的片段(近似,不验证是否逐字);
#       段 = 空行分隔的正文块(行间公式 $$…$$ 不切段; 标题、表格、callout、列表不算段)。
set -u
f="${1:-}"
[ -n "$f" ] && [ -f "$f" ] || { echo "用法: bash note_stats.sh <讲解.md>"; exit 1; }

PY="${PYTHON:-python3}"   # 想用别的解释器: PYTHON=/path/to/python bash note_stats.sh 讲解.md

"$PY" -I - "$f" <<'EOF'
import re, sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
lines = s.split("\n")
ZH = re.compile(r"[\u4e00-\u9fff]")
Q = re.compile(r'"[A-Za-z][^"\n]{15,}"')

h2 = [l[3:].strip() for l in lines if l.startswith("## ")]
h3 = [l for l in lines if l.startswith("### ")]
h4 = [l for l in lines if l.startswith("#### ")]
numbered = [l for l in lines if re.match(r"^#+ *\d+(\.\d+)* ", l)]
toc = set(re.findall(r"\[\[#([^\]|]*)", s))
bullets = [l for l in lines if re.match(r"^\s*[-*] ", l) and not re.match(r"^\s*- \[\[#", l)]
zh = len(ZH.findall(s))
quotes = Q.findall(s)
qchars = sum(len(q) for q in quotes)
bold = re.findall(r"\*\*[^*\n]+\*\*", s)
highlights = re.findall(r"==[^=\n]+==", s)
timestamps = re.findall(r"(?<![\d:])\d{1,2}:\d{2}(?::\d{2})?(?![\d:])", s)
slide_refs = re.findall(r"slides?\s*\d+", s, flags=re.I)
supplements = sum(1 for l in lines if l.startswith("> [!note] 补充"))
warnings = sum(1 for l in lines if l.startswith("> [!warning]"))
answers = sum(1 for l in lines if l.startswith("> [!note]- 答案"))
tags = len(re.findall(r"\\tag\{", s))
anchors = sum(1 for l in lines if re.match(r"^\*录像 ", l))
ratio = qchars / zh if zh else 0

# 段落:按空行切块,跳过标题/表格/callout/列表/锚点/公式块,公式块并入前一段
paras, cur, in_math = [], [], False
def flush():
    global cur
    if cur: paras.append("\n".join(cur)); cur = []
for l in lines:
    if l.strip().startswith("$$"):
        in_math = not in_math if l.strip() == "$$" else in_math  # 单行 $$…$$ 不改状态
        cur.append(l); continue
    if in_math: cur.append(l); continue
    if not l.strip():
        flush(); continue
    if re.match(r"^(#|\||>|\s*[-*] |\s*\d+\. |\*录像 |---)", l):
        flush(); continue
    cur.append(l)
flush()
para_q = [(len(Q.findall(x)), len(ZH.findall(x))) for x in paras]
over_q = [q for q, z in para_q if q > 3]
long_p = [z for q, z in para_q if z > 300]

# 每个 H2 下的中文字数(目录、公式速查不计)
sec, cur_h, buf = {}, None, []
for l in lines:
    if l.startswith("## "):
        if cur_h: sec[cur_h] = len(ZH.findall("\n".join(buf)))
        cur_h, buf = l[3:].strip(), []
    elif l.startswith("# "): continue
    else: buf.append(l)
if cur_h: sec[cur_h] = len(ZH.findall("\n".join(buf)))
thin = [h for h, n in sec.items() if n < 150 and h not in ("目录", "公式速查")]

print(f"行数 {len(lines)} | 中文字 {zh} | H2 {len(h2)} | H3 {len(h3)} | H4 {len(h4)} | 带编号的标题 {len(numbered)} | 锚点行 {anchors}")
print(f"列表项(不含目录) {len(bullets)} | 加粗 {len(bold)} | 高亮 {len(highlights)} | 英文逐字引用 {len(quotes)} 处/{qchars} 字符 (引文字符÷中文字 = {ratio:.2f}) | 时间戳 {len(timestamps)} | slide 引用 {len(slide_refs)}")
print(f"段落 {len(paras)} 段, 引文>3 处的段 {len(over_q)}, 中文>300 字的段 {len(long_p)} | 补充框 {supplements} | 存疑框 {warnings} | 折叠答案 {answers} | 编号公式 {tags}")

missing = sorted(t for t in toc if t not in set(h2))
print("目录链接找不到对应 H2: " + "; ".join(missing) if missing else "目录链接与 H2 一致")

flags = []
if h4: flags.append("出现 H4")
if numbered: flags.append("标题带编号(1.1 / 2.3 这类)")
if len(bullets) * 10 > len(lines): flags.append("列表项超过行数的 10%(列表只放公式表、纠错表、题目)")
if len(bold) > 15: flags.append("加粗超过 15 处(每节至多一句结论加粗)")
if len(highlights) > 8: flags.append("高亮超过 8 处(只给老师明说的考试口径和习题直接用的公式)")
if len(quotes) < 20: flags.append("老师原话逐字引用少于 20 处")
if ratio > 2.0: flags.append(f"引文字符是中文字的 {ratio:.2f} 倍(上限 2):在抄转写,改成转述+少量引证")
if ratio < 1.0 and zh > 2000: flags.append(f"引文字符只有中文字的 {ratio:.2f} 倍(下限 1):定义和关键结论要逐字引")
if over_q: flags.append(f"有 {len(over_q)} 段引文超过 3 处(每段最多 3 处)")
if long_p: flags.append(f"有 {len(long_p)} 段中文超过 300 字(每段 60–250 字,一段一个推理单元)")
if thin: flags.append("这些 H2 下不足 150 字,并进上一节: " + "; ".join(thin))
if len(timestamps) < 60: flags.append("时间戳少于 60 处")
if len(slide_refs) < 10: flags.append("slide 引用少于 10 处(写法: slide 15 / slides 14–16)")
if zh > 8000: flags.append(f"中文 {zh} 字,超过 8,000:检查是否加了老师没讲的东西")
if 0 < zh < 4000: flags.append(f"中文 {zh} 字,少于 4,000:按课件逐页清单查漏")
for x in flags: print("红线:", x)
if not flags: print("形态红线全部通过")
EOF
