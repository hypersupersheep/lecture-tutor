# 在 Moodle / Panopto 上找录像并取转写

在一所英国大学的 Moodle + Panopto 上验证过(2026-10 起,多门课)。下文的 `<moodle_url>`、`<panopto_url>` 取自 `config.yaml`。还在用 Echo360 的旧录像见文末。

## 登录

录像页面走学校的单点登录(SSO)。浏览器工具的登录态通常在本机所有 Claude 会话之间**共享**,大约两天过期;Panopto 自己的会话由下面第 3 步的 LTI 启动建立,不用单独登录。页面出现账号、密码或 MFA 输入框就停下来,请用户在浏览器里登录 Moodle,不要尝试输入任何凭据;只是"选择账号"且账号显示已登录时,点那个账号继续。页面出现 Cloudflare 的 "Verify you are human" 勾选框时同样停下交给用户,不点、不绕过(这时页内 fetch/XHR 会拿到 403 "Just a moment...")。

## 找到那节课的录像

1. 开课程页 `<moodle_url>/course/view.php?id=<moodle_id>`。
2. 录像入口是课程页上的 External tool(LTI)活动,形如 `<moodle_url>/mod/lti/view.php?id=<cmid>`,通常挂在该周的 section 下。**各课叫法不同**:"Session N Recording"、"Lecture N Recording"、"Lecture N Video" 都见过;有的课把课前视频也挂成 LTI(有转写,但不是现场讲课录像),作业提交也可能是 LTI(Turnitin);有的课课程页上根本没有录像入口,录像只在右侧 Panopto 区块里。所以不要只搜 "Recording",用 javascript_tool 列出全部 LTI 活动再挑:

   ```js
   [...document.querySelectorAll('li.activity.modtype_lti')]
     .map(li => li.id.replace('module-', '') + ' ' + li.querySelector('.instancename').innerText.trim())
   ```
   右侧的 Panopto 区块(`.block_panopto`)是浏览器里再加载的(XHR 抓课程页 HTML 看不到它的内容),写着 "No completed recordings" 就是这门课还没有录像。它列出全部已完成的录像,老师没挂 LTI 的也在;区块在收起的抽屉里时 innerText 是空的,要读 textContent。链接形如 `Viewer.aspx?id=<sessionId>`,sessionId 可以直接用,跳过第 3 步的启动;Panopto 会话过期打不开时,点区块里的链接或走一次第 3 步。
3. 拿 sessionId:LTI 活动页本身不含 sessionId(LTI 1.3 的 OIDC 启动,Moodle 这边只有 client_id),要让启动在**顶层标签**里完成:navigate 到 `<moodle_url>/mod/lti/launch.php?id=<cmid>&triggerview=0`,页面会自动 POST 到 Panopto 并落在 `<panopto_url>/Panopto/Pages/Embed.aspx?id=<sessionId>&…`,从 `location.href` 里取那个 UUID(URL 里还带 `access_token=…`,**不要读、不要记录它**)。然后 navigate 到 viewer:`<panopto_url>/Panopto/Pages/Viewer.aspx?id=<sessionId>&autoplay=false`。**一定要带 `autoplay=false`**:不带的话隐藏标签也会有声音地自动播放,还会改续播位置;带上不影响取转写。只想确认录像状态时看 LTI 活动页就够:内嵌播放器会显示真实标题和 "This video isn't available" 之类的状态,不用顶层启动,URL 也不带 token。
4. 页面标题含课程代码和 Panopto 的 folder 名;`#detailsTabPane` 里有讲课日期,形如 `(2026-10-06 16:00+01:00)`。用它核对拿到的是哪一节。

录像上线有延迟:讲课当天通常没有,一两天后出现。有的老师会公告录像从某周起才开放,以课程页为准。

## 取转写

等页面渲染完(约 4 秒),执行 `scripts/panopto_extract.js` 的内容。它只读这几个节点:

| 节点 | 内容 |
|---|---|
| `#transcriptTabPane li.index-event` | 自动转写,每句带时间(`.index-time`)和文本(`.index-event-text`) |
| `#contentsTabPane li` | Panopto 自动生成的章节标题 + 时间,前缀 "Retry Cancel" 是隐藏按钮的文字,脚本会去掉 |
| `#aiSummaryTabPane` | Panopto 的 AI 摘要,三五条,只用来交叉核对主线 |
| `#detailsTabPane` | 标题、folder、讲课日期 |

返回值是一个对象(`transcript` 是整段文本)。超过约 50 KB 的返回值 javascript_tool 不会放进对话,而是存成文件并给出路径(形如 `…/tool-results/toolu_….json`),把那个路径直接交给 `scripts/panopto_to_files.py`,它能解析这种文件和纯 JSON 两种格式;**不要把转写手抄进 Write**。页面上的 `duration` 字段是播放器显示的剩余时间(可能是负数),真实时长看 `meta.txt` 里按最后一句时间算的 `duration_from_transcript`。

页面上还有 Edit*、Cuts、Streams、Download、Share、Discussion 这些面板和按钮,全部不碰。不开 "advanced editor"。

## 没有转写时

`#transcriptTabPane` 为空有三种原因:ASR 还没处理完(录像刚上线,等一天再看);老师没开字幕;录像是课外上传的视频。处理顺序:先看 `#contentsTabPane` 有没有章节(有章节说明 ASR 已经跑过);再问用户要不要下载录像本地转写。装了 mlx-whisper 时,1 小时音频在 Apple Silicon 上几分钟转完,转写时把课件里的术语列表放进 `initial_prompt` 能减少误听。下载只在老师开放了 Download 且用户同意时进行;Download 按钮灰掉或没有就止步,告诉用户。

Echo360(Lecturecast)的旧录像:转写在播放器顶栏的转写图标里,搜索框左边有下载按钮;较早的录像可能没有自动转写。
