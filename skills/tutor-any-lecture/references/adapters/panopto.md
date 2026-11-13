Adapter: Panopto. A lecture recording hosted on Panopto, usually reached from a Moodle course page. It needs an agent with browser tools (see the agent notes: [claude-code](../agents/claude-code.md), [codex](../agents/codex.md), [generic](../agents/generic.md)). Below, `<moodle_url>` and `<panopto_url>` are the institution's addresses (the profile's `platforms`, or ask the learner).

## Platform

Panopto lecture capture inside a learning platform. The transcript is read from the Panopto viewer page by `scripts/panopto_extract.js` (in this skill's folder) and imported with `tutor-any-lecture acquire panopto --extract JSON --unit DIR [--force]`.

## URL patterns

- Course page: `<moodle_url>/course/view.php?id=<course_id>`.
- Recording activity (an External tool, LTI): `<moodle_url>/mod/lti/view.php?id=<cmid>`.
- LTI launch in the top-level tab: `<moodle_url>/mod/lti/launch.php?id=<cmid>&triggerview=0`, which lands on `<panopto_url>/Panopto/Pages/Embed.aspx?id=<sessionId>&…`.
- Viewer: `<panopto_url>/Panopto/Pages/Viewer.aspx?id=<sessionId>&autoplay=false`.

## Where transcripts/captions live

In the viewer's side tabs. The extract script reads only these nodes:

| node | content |
|---|---|
| `#transcriptTabPane li.index-event` | the automatic transcript, one line per sentence with its time (`.index-time`) and text (`.index-event-text`) |
| `#contentsTabPane li` | Panopto's automatic chapter titles and times; a hidden-button prefix "Retry Cancel" is removed |
| `#aiSummaryTabPane` | Panopto's AI summary, a few points, for cross-checking the main line only |
| `#detailsTabPane` | title, folder and the lecture date, written like `(2026-10-06 16:00+01:00)` |

When `#transcriptTabPane` is empty there are three possible reasons: speech recognition has not finished (the recording is new; look again a day later), captions are switched off for this recording, or the video is not a lecture capture but an upload. Check `#contentsTabPane` first: chapters mean recognition has run. Then ask the learner whether to use another source (a transcript export through [import](import.md), or a downloaded file through [local](local.md) if downloads are offered).

## Read-only steps

1. **Login.** The pages use the institution's single sign-on, in the browser the agent already has. If a username, password or MFA field appears, stop and ask the learner to sign in in that browser; never type any credential. If the page only asks to pick an account that is already signed in, pick it. If a "Verify you are human" check appears, stop and hand it to the learner; do not click it or work around it.
2. **Find the recording.** Open the course page. Recordings are External tool (LTI) activities, usually in the week's section, and their names vary by course ("Session N Recording", "Lecture N Recording", "Lecture N Video"); pre-lecture videos and assignment tools may also be LTI activities. So list every LTI activity instead of searching for one word, with a read-only page script:

   ```js
   [...document.querySelectorAll('li.activity.modtype_lti')]
     .map(li => li.id.replace('module-', '') + ' ' + li.querySelector('.instancename').innerText.trim())
   ```

   The Panopto block in the side column (`.block_panopto`) is filled in by the browser after load; it lists every completed recording of the course, including ones that are not linked as activities, or says "No completed recordings". When the block sits in a collapsed drawer its `innerText` is empty: read `textContent`. Its links look like `Viewer.aspx?id=<sessionId>`; that sessionId can be used directly, skipping step 3.
3. **Get the sessionId.** The activity page does not contain it (the launch is an LTI 1.3 sign-in hand-off). Let the launch finish in a top-level tab: open `<moodle_url>/mod/lti/launch.php?id=<cmid>&triggerview=0`; it posts to Panopto and lands on `Embed.aspx?id=<sessionId>&…`. Take the id from the address. That address also carries an `access_token=…` parameter: never read, copy or record it. To check only whether a recording exists, the activity page's embedded player is enough (it shows the real title and states such as "This video isn't available").
4. **Open the viewer** at `<panopto_url>/Panopto/Pages/Viewer.aspx?id=<sessionId>&autoplay=false`. Always add `autoplay=false`: without it even a background tab plays sound and moves the resume position. The page title shows the folder name and `#detailsTabPane` the lecture date; use them to confirm it is the right session.
5. **Extract.** Wait about 4 seconds for the tabs to render (the script waits too), then run the content of `scripts/panopto_extract.js` in the page. It returns one object: `url`, `title`, `details`, `duration`, `n`, `contents`, `ai` and `transcript` (the whole transcript as `[m:ss] text` lines).
6. **Save** the return value, unchanged, to a JSON file (for example `extract.json` next to the unit folder). A large result that your agent stores as a tool-results file (a list like `[{"type": "text", "text": "<json>"}]`) can be passed as it is. Never retype or paste the transcript by hand.
7. **Import:** `tutor-any-lecture acquire panopto --extract extract.json --unit DIR`. Outcome, one JSON object on stdout:
   - `{"status": "ok", "health": {…}}`, exit 0: `sources/transcript.json`, `sources/chapters.json` and `sources/source.json` (`"kind": "platform"`, `"platform": "panopto"`, the lecture date when the details show one) are written. The duration is the last transcript time;
   - `{"status": "unhealthy", "health": {…}}`, exit 1: the files are written, but read `status`, show the health numbers and tell the learner before planning on that transcript;
   - `{"status": "error", "message": …}`, exit 1, nothing written: the extract held no timed transcript lines (`no timed segments found`), or the file is not a Panopto extract. Show `message` to the learner;
   - exit 3, one line on stderr: the unit already has a transcript; rerun with `--force` to replace it.
8. Run `tutor-any-lecture slides suspects --unit DIR` once the slides are in (see [moodle](moodle.md)).

The viewer also has edit, Cuts, Streams, Download, Share and Discussion panels and buttons: never touch them, and never open the advanced editor.

## Downloads offered?

Only when the recording's owner enabled Download. Use it only when the profile's `downloads` allows it and the learner agrees, then transcribe the file with [local](local.md). If Download is greyed out or missing, tell the learner: never capture the stream yourself, never circumvent DRM.

The audio switch (`public_video_audio`, see [url](url.md)) is the learner's decision: once they have switched it on, downloading a recording's audio through `acquire url` is their choice and their responsibility, and the tool does not check the platform's terms. The tool never uses the learner's login, so a recording behind a sign-in is not reachable that way: there the learner uses the captions above, or a file they downloaded themselves.

## Known pitfalls

- Recordings appear with a delay: usually not on the day of the lecture, a day or two later. Some lecturers open recordings only from a given week; the course page is the authority.
- The page's own `duration` field is the player's remaining time (it can be negative); the import ignores it and uses the last transcript time.
- Run the script on the Viewer address, not the Embed address: the page address is saved in source.json, and the Embed address carries a token.
- Sign-in usually lasts about two days and is shared by the browser's tabs; the Panopto session itself is created by the LTI launch.
- Older recordings on Echo360: the transcript sits behind the transcript icon in the player's top bar, with a download button left of its search box; older recordings may have none.

## Verified by (name/date) or "experimental"

The v1 extraction path (page script and these steps) was used on real lecture recordings at one institution from 2026-10. The v2 import, `acquire panopto`, is covered by tests only: experimental until a real run.
