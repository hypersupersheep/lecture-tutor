Adapter: Moodle. Documentation only: slides and other files on a Moodle course page, read in the browser. It needs an agent with browser tools (see [claude-code](../agents/claude-code.md), [codex](../agents/codex.md), [generic](../agents/generic.md)). `<moodle_url>` is the institution's Moodle address (the profile's `platforms`, or ask the learner).

## Platform

Moodle, a learning platform where courses post slides, notes and exercise sheets, and link lecture recordings. This adapter only hands files to `tutor-any-lecture slides --pdf F --unit DIR [--images]`, then `tutor-any-lecture slides suspects --unit DIR`. Recordings linked from Moodle go through the [panopto](panopto.md) adapter.

## URL patterns

- Course page: `<moodle_url>/course/view.php?id=<course_id>`.
- A file activity: `<moodle_url>/mod/resource/view.php?id=<cmid>`; a folder: `<moodle_url>/mod/folder/view.php?id=<cmid>`; an HTML page: `<moodle_url>/mod/page/view.php?id=<cmid>`.
- The files themselves: `<moodle_url>/pluginfile.php/…`.

## Where transcripts/captions live

Not on Moodle itself: recordings are External tool (LTI) activities that open Panopto or another capture platform; follow that platform's adapter. Moodle holds the slides, usually as file or folder activities in the week's section.

## Read-only steps

1. Use the browser's existing login. At a sign-in page, stop and ask the learner to sign in; never type credentials. At a "Verify you are human" check, stop and hand it to the learner.
2. Open the course page and find the unit's week. Note each file's name and type; an HTML page may duplicate a PDF or hold content of its own, so compare before you skip it.
3. Download a file only as the profile's `downloads` allows: with ask (the default), ask the learner before each download; with allow, take only files Moodle itself offers for download. Save them where the learner keeps course files.
4. Run `tutor-any-lecture slides --pdf F --unit DIR` on the slide PDF. On a run it printed `{"status": "ok", "pages": N, "labelled": M}` (M: pages with a footer number) and exited 0. It writes `sources/slides/pages.json` and, when the unit has no `sources/source.json`, a slides-only `source.json` (`"kind": "slides-only"`); an existing source.json is left alone. Slides alone make a slides-only unit: its note cites slides only, never times.
5. After a transcript is in, run `tutor-any-lecture slides suspects --unit DIR`. On a run it printed `{"status": "ok", "suspects": N}`, exited 0 and wrote `sources/suspects.json`; without a transcript it exited 1 with `transcript not found: …; run an acquisition first` on stderr.

Read-only throughout: no submissions, forum posts, quiz attempts, bookings or messages, ever.

## Downloads offered?

The files that Moodle shows as links (slides, notes, sheets), subject to the profile's `downloads` setting. Recordings are not Moodle downloads; see [panopto](panopto.md).

## Known pitfalls

- Activity names differ between courses; read the whole week's section rather than searching for one word.
- Blocks in the side column load after the page; a block in a collapsed drawer has empty `innerText` but readable `textContent`.
- A sign-in usually lasts about two days; when pages start redirecting to sign-in, stop and ask the learner.
- Slides are sometimes replaced during term; when two versions exist, ask which one the lecture used.

## Verified by (name/date) or "experimental"

experimental
