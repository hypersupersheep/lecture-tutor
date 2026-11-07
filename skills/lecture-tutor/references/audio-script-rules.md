# 语音版:从讲解笔记到可以听的音频

语音版是**从讲解笔记派生的单人讲解稿**再合成,不是把笔记直接念出来,也不是两个人闲聊。依据:对话式讲解的好处来自苏格拉底式提问和暴露误解,不来自闲聊本身(Chi, Kang & Yaghmourian 2017);口头信息是瞬时的,长段复杂推理在音频里比文字更难消化(Leahy & Sweller 2011),所以段要短、公式要锚定到纸面(冗余原则对数学公式的例外,Clark & Mayer)。

## 1. 文件

- 语音稿:`weekN/笔记/源文件/<课次>_语音稿.md`,按段落分块,每块开头一行 `## 第 k 段 · <笔记对应的 H2 标题>`。
- 音频:`weekN/笔记/lecture_wN/<课次>_语音.m4a`(多段 ffmpeg 拼接,段间 0.5 s 静音),再复制一份到 Obsidian vault 讲解笔记同目录(`lecture_wN/`),命名为 `<课次>-语音.m4a`,笔记开头加一行 `![[<课次>-语音.m4a]]`。
- 每段音频 3–6 分钟,一节课总长 25–40 分钟。

## 2. 讲解稿怎么写

1. 一个声音从头讲到尾。需要"提问"时用同一个声音自问,停 2–3 秒再答;不设第二个主持人。
2. 每段对应笔记的一个 H2。段首一句"这一段讲 X",段尾一句话收束;整节课结尾用 60 秒把 3–5 个要点再说一遍。
3. 为耳朵写:单句尽量在 25 字以内,超过 35 字一定拆开(`tts_synthesize.py` 合成前会把超过 35 字的句子报出来);一句只说一件事;口头路标代替视觉层级——"第一""第二""重点来了""常见的错法是"。
4. 公式按意思读,不按符号读。超过两层嵌套的式子不念全,说"看笔记公式三",只讲它表达的意思和要注意的项。常用读法:

   | 写法 | 读法 |
   |---|---|
   | $a/b$ | b 分之 a |
   | $x^2$、$x^n$ | x 的平方、x 的 n 次方 |
   | $e^{rt}$ | e 的 r t 次方 |
   | $(1+r/m)^{nm}$ | 括号 1 加 m 分之 r,括号的 n m 次方 |
   | $\sum_{i=1}^{n}$ | 对 i 从 1 到 n 求和 |
   | $\int_a^b f(x)\,dx$ | 从 a 到 b 对 x 积分 |
   | $\log P$ | log P |
   | $P(A\mid B)$ | 在 B 条件下 A 的概率 |
   | $\hat\theta$ | theta hat,也就是 theta 的估计 |
   | $dM/dt = rM$ | M 对 t 的导数等于 r 乘 M |

   原始 LaTeX 永远不进 TTS。
5. 英文术语保留英文,不音译;缩写按字母拆开写(A E R、M L E),或者用后端的发音词典固定读音。每个后端第一次用之前,拿 20 句含高频术语的句子试听一遍。
6. 数字写成读法:百分之五、零点零五、十的负五次方、二零二六年十一月十七日;不用 1e-5、不用破折号表示区间。
7. 显式停顿:公式前后 0.6–1 秒,提问之后 2–3 秒;后端支持的停顿标记写进稿子(MiniMax `<#0.8#>`,Gemini `[short pause]`),本地模型用标点和分段控制。
8. 关键定义说两遍:先说老师的形式化说法,再用一句直觉重说一遍。
9. 不用"如上图""下面这张表"这类视觉指代,改说"笔记第几节的表"。
10. 补充框的内容可以讲,但要说明"这是我补的,老师没讲";存疑框只在影响理解时提一句。
11. 讲解稿写完先自己读一遍,读不顺的句子就是太长。

## 2b. 已验证的写法细节(2026-10-13,Qwen3-TTS 实测)

- 公式里的数字 1 写成"一"("一加 R""等于一""趋于一"),否则模型可能把 1 读成字母;其他阿拉伯数字也写成中文读法。
- **单独的字母符号按意思读,不念字母**:中文语境下模型把 r / R 读成"二"(大小写、温度、`lang_code=Auto` 都救不了,每次生成还随机),y 有时读成"歪",whisper 回转分别听成 2 和"外"。写法:$r$ → "利率",$1+r$ → "一加利率",$r/m$ → "m 分之利率",$e^{rt}$ → "e 的,利率乘时间,次方",$y$ → "收益率",$e^{-y(T-t)}$ → "e 的负,收益率乘剩余期限,次方"。只在介绍记号时念一次字母,写成"记作字母 阿尔"("阿尔"稳定读成 R)。字母串如 "A E R" 读得对,不用改。m、n、t、e、P、N 这些单独出现时能正确读。
- 改完稿子后删掉工作目录里对应的 wav 再跑 `tts_synthesize.py`,它按"段号_段落号"缓存,不看内容。
- 带所有格撇号的专有名词会被逐字母拼读,写成 "L'Hôpital rule" 而不是 "L'Hôpital's rule";人名、术语保留英文,缩写拆成 "A E R"。
- 英文术语(maximum likelihood estimator、consistent、yield to maturity、spot rate、gross rate)在 Serena 和 Uncle_Fu 两个中文音色下都能清楚读出,whisper 回转能认出来。
- 合成后用 mlx-whisper 把音频转回文字,只看英文术语和公式读法是否还原;中文同音错字(终值→中值)是 whisper 的问题,不用管。

## 3. 合成后端

| 方案 | 适用 | 要点 |
|---|---|---|
| **本地 Qwen3-TTS-12Hz-1.7B via mlx-audio**(Apache-2.0) | 默认 | `pip install mlx-audio`(实测 0.5.8),模型 `mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit` 第一次运行时自动下载(约 2 GB,缓存在 `~/.cache/huggingface`)。M5 Max 上实测生成速度约为实时的 5 倍(484 字符 → 1.8 分钟音频,20 秒)。中文预置音色:Serena(女,温和,约 150 字符/27 秒)、Vivian(女,亮)、Uncle_Fu(男,低沉,比 Serena 慢约 45%)、Dylan(京腔)、Eric(川味);默认 Serena,`lang_code` 用 Chinese,英文术语混读没问题 |
| **MiniMax speech-2.8-hd**(platform.minimax.io) | 要更好的音质时 | 中文最强梯队;`latex_read` 可直接读 LaTeX;`pronunciation_dict` 固定术语读音;`<#0.8#>` 停顿;单次 10k 字符,长文本走异步接口;约 $10/月。需要你自己的 API key,不要写进仓库 |
| Qwen3-TTS 云端(阿里 Model Studio 新加坡)、Gemini TTS | 备选 | 前者约 $1/月;后者适合双人稿,本 skill 不用双人 |

不选:ElevenLabs(中文榜缺席)、OpenAI TTS(中文无评测、单次 2000 token)、IndexTTS-2(MLX 版慢于实时)、VibeVoice(已下架)、macOS `say`(音质不够)。

## 4. 合成流程

本地后端用 `scripts/tts_synthesize.py` 一步完成(解析语音稿 → 每个段落合成一次 → 段落间 0.6 s、段间 1.2 s 静音 → ffmpeg 拼成 m4a):

```bash
<python> <本 skill 目录>/scripts/tts_synthesize.py \
  "<课程文件夹>/weekN/笔记/源文件/<课次>_语音稿.md" \
  "<课程文件夹>/weekN/笔记/lecture_wN/<课次>_语音.m4a" \
  --voice Serena --workdir <临时目录>/tts-full        # 调试单段加 --only 3
```

中间 wav 放临时目录,已合成的段落会被缓存,改了某一段只重跑那一段(删掉对应 wav 即可)。合成完:
1. `ffprobe` 看总时长是否在 25–40 分钟;
2. 用 mlx-whisper(`mlx-community/whisper-large-v3-turbo`,第一次运行时自动下载)把一个公式密集段和结尾段转回文字,核对术语和公式读法。先用 ffmpeg 截一段,再转(40 秒的片段约 2 秒转完):
   ```bash
   ffmpeg -y -loglevel error -ss 00:17:30 -t 60 -i <课次>_语音.m4a <临时目录>/clip.wav
   mlx_whisper <临时目录>/clip.wav --model mlx-community/whisper-large-v3-turbo --language zh --output-format txt --output-dir <临时目录>
   ```
3. m4a 复制一份到 Obsidian vault 讲解笔记同目录(`<vault_root>/<folder>/weekN/lecture_wN/`),改名 `<课次>-语音.m4a`,笔记"怎么读"段之后加一行 `![[<课次>-语音.m4a]]`;
4. 删掉中间 wav,只留 m4a 和语音稿。

云端后端(MiniMax)的流程未实测,需要时按其 API 文档另写脚本。
