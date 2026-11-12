// 在 Panopto Viewer 页面(<你的学校>.cloud.panopto.eu/Panopto/Pages/Viewer.aspx?id=...)里执行。
// 只读:从 DOM 取转写、章节目录、AI 摘要、详情;不点任何按钮,不碰 edit*/Cuts/Streams 面板。
// 在真实课程录像上验证过:一节约 1.5 小时的课取到约 700 句转写、14 个章节。
await new Promise(r => setTimeout(r, 4000));   // 等 React 把各个 tab pane 渲染完
const clean = s => (s || '').replace(/\s+/g, ' ').replace(/^Retry Cancel /, '').trim();
const lines = [...document.querySelectorAll('#transcriptTabPane li.index-event')].map(li => {
  const t = (li.querySelector('.index-time, .event-time') || {}).innerText;
  const x = (li.querySelector('.index-event-text, .event-text') || li).innerText;
  return `[${t}] ${clean(x)}`;
});
const contents = [...document.querySelectorAll('#contentsTabPane li')].map(li => clean(li.innerText));
const ai = [...document.querySelectorAll('#aiSummaryTabPane li, #aiSummaryTabPane p')].map(e => clean(e.innerText));
const details = clean(document.querySelector('#detailsTabPane')?.innerText).slice(0, 800);
const duration = document.querySelector('.duration-display, #timeRemaining, .time-display')?.innerText;
({ url: location.href, title: document.title, details, duration, n: lines.length, contents, ai, transcript: lines.join('\n') })
