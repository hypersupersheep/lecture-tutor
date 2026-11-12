# 在 Cowork 里运行

流程、写作契约和铁律都和 SKILL.md 一样,只有下面这些差别。**这条流程还没有在 Cowork 里完整跑过**,和这里写的不一样时以实际为准,并告诉用户。

## 开工前:连接两个文件夹

Cowork 默认看不到用户的文件。用 `mcp__cowork__request_cowork_directory` 请求(已连接就跳过):

- 课程资料根目录:`config.yaml` 里的 `course_root`
- Obsidian 笔记文件夹:`config.yaml` 里的 `vault_root`(不用 Obsidian 就跳过)

Read、Write、Edit 用 Mac 上的路径。shell 在 Linux 虚拟机里,连接的文件夹在虚拟机里的路径不同(通常是 `/sessions/<会话名>/mnt/<文件夹名>/`),先 `ls` 确认再用。

## 工具对照

| SKILL.md 写的 | Cowork 里 |
|---|---|
| Bash | `mcp__workspace__bash`(虚拟机里的 shell;老版本叫 `Bash`) |
| `config.yaml` 里的 Python | `python3`,`-I` 照旧。缺 pdfplumber 就在虚拟机里 `pip install`,不影响 Mac 上的环境 |
| 把文件发给用户 | `mcp__cowork__present_files`,只能发 outputs、uploads 或已连接文件夹里的文件 |
| 浏览器工具、javascript_tool | 同名的 `mcp__Claude_Browser__*`,登录态和 Claude Code 共享 |
| 临时目录、工作目录 | outputs 文件夹 |

虚拟机的网络只放行 PyPI、npm、GitHub、Ubuntu 软件源和 Anthropic,shell 里连不上 Moodle 和 Panopto,这两个站只走浏览器工具。

## 脚本和大返回值

脚本路径以加载 skill 时显示的 Base directory 为准。shell 读不到那个路径时,用 Read 读出脚本内容,Write 到 outputs 文件夹再跑。`panopto_to_files.py` 和 `note_stats.sh` 只用标准库,`note_stats.sh` 默认用 `python3`。`panopto_extract.js` 是把内容贴进 javascript_tool,不经过 shell。

javascript_tool 超过约 50 KB 的返回值会存成 tool-results 文件。shell 读不到这个文件时,在页面里分段取:让脚本把结果存到 `window.__panopto`,再用 `JSON.stringify(window.__panopto).slice(i, i + 40000)` 每次取 40 KB,用 Write 逐段写到 outputs 再拼起来,最后核对总长度和页面返回的一致。拼好的 JSON 照常交给 `panopto_to_files.py`。

## 做不了的,回 Claude Code 做

这些依赖 Mac 本机,虚拟机里没有:

- **语音合成和回转抽查**(第 9 步):`tts_synthesize.py` 和 mlx-whisper 只能在 Apple Silicon 的 macOS 上跑。语音稿可以在这里写完,合成交给 Claude Code。
- **手写版和总览图**(第 8 步):渲染脚本要本机 Chrome,以及 jsdelivr、esm.sh、Google Fonts 上的字体和库。这一步跳过。
- **没有转写时的本地转写**(第 3 步):同样要 mlx-whisper。照常先问用户。

交付时说清楚哪些没做,让用户回 Claude Code 说"做手写版和总览图"或"做语音版"。
