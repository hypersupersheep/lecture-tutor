# The delivery gate

`tutor-any-lecture verify --unit DIR` checks one unit folder and writes verify.json there. Add `--json` to print the result as one JSON line instead of a table. Nothing is delivered until overall is PASS.

## Statuses

Each check is PASS, WARN or FAIL. **Overall is PASS iff no check is FAIL**; warnings do not block delivery, but read them and fix what is real. verify.json holds `checks` (each `{"name", "status", "details"}`), `overall`, `warnings` (the number of WARN checks), `measures` and `report`, which is exactly one of:
- `Automated checks passed; not visually reviewed.`
- `Automated checks failed.`

Exit 0 on PASS, 1 on FAIL.

**What was measured.** `measures` records, whether the checks passed or not: `minutes`; `length` (`unit`, `total`, `per_min` and its `window`); `time_citations` and `quotes` (`per_min` and the `min` for the goal); `quote_share` or `quote_ratio` (`value` and `window`; the other is null); `h2` (`count` and `max`). Per-minute values and limits are null when the duration is unknown. After its table, verify prints them on one line before the report line, for example `measures: length 52.3 words/min (26-53); time citations 0.8/min (>= 0.67); quotes 0.31/min (>= 0.22); quote share 0.18 (0.1-0.4); H2 12 (<= 16)`. Read it on PASS too: it shows how close the note is to each limit.

## The nine checks, in order

| check | what it catches | worst status |
|---|---|---|
| `citations` | a slide number above the last slide; a time more than 2 s past the duration; a time citation in a slides-only unit; a unit with no `sources/transcript.json` that is not slides-only; `quote_source`: a cited quote that is in neither the transcript nor the slides (FAIL), or that is there but not at the place it cites (WARN, naming where it was found); see [writing](writing.md), Faithful to the lecturer | FAIL |
| `coverage` | a slide that is neither cited anywhere in the note nor listed (`slide N` or `slides N–M`) in the `tal:not-covered` section | FAIL |
| `terms` | capitalised multi-word terms and words with an inner capital, in the lecture prose, that appear in neither the transcript nor the slides; the lines between the H1 and the first H2 and the callout type names are skipped | WARN |
| `numbers` | numbers with a unit (%, percent, bps, years, months, weeks, days, hours, minutes) or a currency sign that are in the sources but not in the lecture prose, or the other way round | WARN |
| `structure` | the note rules of [writing](writing.md): markers, H4, headings with an outline prefix (`1.`, `1.2`), callout types, TOC links, `<details>` answers, quotes per paragraph and their citations, uncited blockquotes (FAIL); length, time citations and quotes per minute, H2 count, thin sections, long paragraphs, bold, highlights, bullets, quote share or quote ratio (the ratio's window set by plan.json's `quote_density`) (WARN) | FAIL |
| `items` | items.json against plan.json and the note: `variants`, `apply_share`, `citation`, `prompt_overlap`, `tracked_leak`, `tracked_vs_practice` (FAIL); `pretest_complete` (WARN); a missing items.json or assignment.json (FAIL) | FAIL |
| `cards` | `count` over the cap, `duplicates`, an empty `citation` (FAIL); `back_length` over 350 characters (WARN) | FAIL |
| `map` | map.json schema, node types, edges without a verb or with an unknown end, views over 12 nodes, nodes in no view | FAIL |
| `banned_phrases` | stock phrases in the note, such as "delve", "it's worth noting", "in conclusion", "in summary" | WARN |

**Skipped checks.** `items` is skipped when neither "quiz" nor "pretest" is in plan.outputs, `cards` when "cards" is not, and `map` when "map" is not. A skipped check is PASS with the detail `skipped: not in plan.outputs`. A listed output whose file is missing is FAIL.

**Lecture prose.** `terms` and `numbers` read the lecture prose only: the note without its marker sections (pretest, checks, not covered, errata), NOTE callouts, code and math. A number that appears only in a pretest answer does not count as in the note.

**Unknown duration.** When neither plan.json nor source.json gives a duration, the per-minute checks are skipped and `structure` reports a WARN; time citations are not range-checked and `citations` reports a WARN. Unknown duration is never a FAIL on its own.

**Slides-only units.** Without `sources/transcript.json` a unit passes only when source.json's `kind` is "slides-only" (what `tutor-any-lecture slides --pdf F --unit DIR` writes into a unit that has no source.json), and then any time citation is a FAIL. Such a note cites slides only.

## The loop

1. For a unit from a link, run `tutor-any-lecture cite link --unit DIR` (it links the plain time citations; see [writing](writing.md), Citations). Run `tutor-any-lecture cards export --unit DIR` when "cards" is in plan.outputs and `tutor-any-lecture map mermaid --unit DIR` when "map" is.
2. Run `tutor-any-lecture verify --unit DIR`.
3. For each FAIL, read its details, fix the file they name (usually explanation.md, items.json, cards.json or map.json) and rerun. After an items.json change, keep assignment.json unless a tracked concept changed; then rerun `tutor-any-lecture items assign --unit DIR --force` and rewrite the pretest section.
4. Stop at PASS. Fix WARNs that point at a real problem; leave the rest and mention them.

**Visual check.** Only for showcase samples, or when a check reported a problem that only rendering can confirm: render once, look, fix one round, stop.

**Honest reporting.** Report the `report` line exactly as printed. Never say the note was reviewed visually, read by a person or checked against the recording when it was not. Name any WARN you left.

## Exit codes

| code | meaning |
|---|---|
| 0 | PASS or WARN, a healthy transcript, doctor ready |
| 1 | verify or validate FAIL; an unhealthy or empty transcript; selftest not ok; a missing file (plan.json, explanation.md, map.json, assignment.json for `items next`, a slide PDF, a transcript for `slides suspects`, a progress log for `progress render`, a materials folder for `acquire route`); a malformed file: plan.json, items.json, assignment.json, cards.json or map.json (one stderr line naming the file), or profile.yaml, and a value that `profile set` rejects (a `ProfileError` naming the key); an acquisition input that could not be read or parsed, or a tool or ASR backend that failed (an `error` object, below) |
| 2 | usage error (a wrong or missing flag, `slides` without `--pdf` and `--unit`, a bare `acquire`, `acquire url` with neither `--unit` nor `--info`, a `--date` not written YYYY-MM-DD), an unknown item id (`items get`, `progress log`), an unknown `--view` for `map mermaid` |
| 3 | needs the user: doctor not ready; consent required (`profile set public_video_audio on`); a file needed from the user (`needs_user_file`); ASR time budget exceeded (rerun with a larger `--budget-minutes`); speech recognition not installed (run the installer again with `--with-asr`, Windows `-WithAsr`); the output exists (rerun with `--force`); `selftest --keep` on a folder that exists and is not empty (pick a new or empty one) |
| 130 | interrupted with Ctrl+C |
| 143 | stopped by a signal, such as a shell timeout; the command cleaned up after itself and can be run again |

## Acquisition JSON

`acquire import`, `acquire panopto`, `acquire local`, `acquire url` and `transcribe` print exactly one JSON object on stdout:
- `{"status": "ok", "health": {…}}`, exit 0; for `acquire url` also `title` (the video's) and `acquisition` (the track used: "cc", "auto" or "asr"), here and in `unhealthy`;
- `{"status": "unhealthy", "health": {…}}`, exit 1: the transcript was written but failed a health check; for `acquire url` these are caption tracks, kept and reported when no healthy track exists and audio may not be used. Show the health numbers and tell the learner before planning on that transcript; a rerun needs `--force`;
- `{"status": "error", "message": …}`, exit 1, nothing written. The causes: the input file is missing or is a folder; the source had no timed text (`no timed segments found`); the input is not UTF-8 or could not be parsed; profile.yaml is malformed; a tool (ffmpeg, yt-dlp) or the ASR backend failed; the video page could not be read (private, removed, region- or login-locked); the URL is a playlist (one video per unit). Show `message` to the learner;
- `acquire url` only: `{"status": "needs_user_file", "message": …}`, exit 3: no usable captions, and audio may not or cannot be downloaded: the switch is off, or the audio could not be fetched without a login.

`health` has the keys `coverage` (share of the duration the segments span, healthy from 0.9), `repetition` (share of segments repeating the previous one, healthy up to 0.5), `spots_ok` (segments near 10%, 50% and 90% of the duration), `overrun` (a segment ends more than 2 s after the duration), `loop` (five or more identical segments in a row), `ok`, and `duration_known`. With an unknown duration, coverage and spots cannot be measured and count as fine.

`acquire url --url U --info` reads only the video page: it needs no `--unit`, writes nothing and prints `{"status": "ok", "title", "duration", "uploader", "manual_captions": [language codes], "automatic_captions": true|false}`, or the `error` object above (exit 1).

**Commands that write a file** end by printing one JSON object that names it: `{"path"}`, or `{"paths": […]}` for several (`map mermaid` on a map with views). `cards export`, `cards add-misses` (with `added`), `cite link` (with `linked`), `items assign` (the assignment, with `path`), `slides --pdf` and `slides suspects` (with their counts), `map mermaid` and `progress render` do so.

An existing `sources/transcript.json` without `--force` stops the command before any work (exit 3, one line on stderr). A budget or backend problem (exit 3) is also one stderr line, with no JSON on stdout.
