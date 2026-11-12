// Run this inside a Panopto Viewer page (<your-school>.cloud.panopto.eu/Panopto/Pages/Viewer.aspx?id=...).
// Read-only: it takes the transcript, the chapter list, the AI summary and the details from the DOM; it clicks no button and does not touch the edit*/Cuts/Streams panels.
// Checked on real lecture recordings: a lecture of about 1.5 hours gave about 700 transcript lines and 14 chapters.
await new Promise(r => setTimeout(r, 4000));   // wait for React to render every tab pane
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
