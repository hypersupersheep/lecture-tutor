# The delivery gate

`tutor-any-lecture verify --unit DIR` checks one unit folder and writes verify.json there. Add `--json` to print the result as one JSON line instead of a table. Nothing is delivered until overall is PASS.

## Statuses

Each check is PASS, WARN or FAIL. **Overall is PASS iff no check is FAIL**; warnings do not block delivery, but read them and fix what is real. verify.json holds `checks` (each `{"name", "status", "details"}`), `overall`, `warnings` (the number of WARN checks) and `report`, which is exactly one of:
- `Automated checks passed; not visually reviewed.`
- `Automated checks failed.`

Exit 0 on PASS, 1 on FAIL.

## The nine checks, in order

| check | what it catches | worst status |
|---|---|---|
| `citations` | a slide number above the last slide; a time more than 2 s past the duration; a time citation in a slides-only unit; a unit with no `sources/transcript.json` that is not slides-only | FAIL |
| `coverage` | a slide that is neither cited anywhere in the note nor listed (`slide N` or `slides N–M`) in the `tal:not-covered` section | FAIL |
| `terms` | capitalised multi-word terms and words with an inner capital that appear in neither the transcript nor the slides (NOTE callouts are skipped) | WARN |
| `numbers` | numbers with a unit (%, percent, bps, years, months, weeks, days, hours, minutes) or a currency sign that are in the sources but not in the note, or the other way round | WARN |
| `structure` | the note rules of [writing](writing.md): markers, H4, numbered headings, callout types, TOC links, `<details>` answers, quotes per paragraph and their citations, uncited blockquotes (FAIL); length, time citations and quotes per minute, H2 count, thin sections, long paragraphs, bold, highlights, bullets, quote share (WARN) | FAIL |
| `items` | items.json against plan.json and the note: `variants`, `apply_share`, `citation`, `prompt_overlap`, `tracked_leak`, `tracked_vs_practice` (FAIL); `pretest_complete` (WARN); a missing items.json or assignment.json (FAIL) | FAIL |
| `cards` | `count` over the cap, `duplicates`, an empty `citation` (FAIL); `back_length` over 350 characters (WARN) | FAIL |
| `map` | map.json schema, node types, edges without a verb or with an unknown end, views over 12 nodes, nodes in no view | FAIL |
| `banned_phrases` | stock phrases in the note, such as "delve", "it's worth noting", "in conclusion", "in summary" | WARN |

**Skipped checks.** `items` is skipped when neither "quiz" nor "pretest" is in plan.outputs, `cards` when "cards" is not, and `map` when "map" is not. A skipped check is PASS with the detail `skipped: not in plan.outputs`. A listed output whose file is missing is FAIL.

**Unknown duration.** When neither plan.json nor source.json gives a duration, the per-minute checks are skipped and `structure` reports a WARN; time citations are not range-checked and `citations` reports a WARN. Unknown duration is never a FAIL on its own.

**Slides-only units.** Without `sources/transcript.json` a unit passes only when source.json's `kind` is "slides-only" (what `tutor-any-lecture slides --pdf F --unit DIR` writes into a unit that has no source.json), and then any time citation is a FAIL. Such a note cites slides only.

## The loop

1. Run `tutor-any-lecture cards export --unit DIR` when "cards" is in plan.outputs and `tutor-any-lecture map mermaid --unit DIR` when "map" is.
2. Run `tutor-any-lecture verify --unit DIR`.
3. For each FAIL, read its details, fix the file they name (usually explanation.md, items.json, cards.json or map.json) and rerun. After an items.json change, keep assignment.json unless a tracked concept changed; then rerun `tutor-any-lecture items assign --unit DIR --force` and rewrite the pretest section.
4. Stop at PASS. Fix WARNs that point at a real problem; leave the rest and mention them.

**Visual check.** Only for showcase samples, or when a check reported a problem that only rendering can confirm: render once, look, fix one round, stop.

**Honest reporting.** Report the `report` line exactly as printed. Never say the note was reviewed visually, read by a person or checked against the recording when it was not. Name any WARN you left.

## Exit codes

| code | meaning |
|---|---|
| 0 | PASS or WARN, a healthy transcript, doctor ready |
| 1 | verify or validate FAIL; an unhealthy or empty transcript; selftest not ok; a `ProfileError` or `PlanError`; a missing file; an input that could not be read or a tool that failed; a malformed plan.json, items.json, assignment.json, cards.json or map.json (one stderr line naming the file) |
| 2 | usage error (a wrong or missing flag), a command that is not implemented yet, an unknown item id |
| 3 | needs the user: doctor not ready; consent required (`profile set public_video_audio on`); a file needed from the user (`needs_user_file`); ASR time budget exceeded (rerun with a larger `--budget-minutes`); no ASR backend (see `tutor-any-lecture doctor`); the output exists (rerun with `--force`) |

## Acquisition JSON

`acquire import`, `acquire panopto`, `acquire local`, `acquire url` and `transcribe` print exactly one JSON object on stdout:
- `{"status": "ok", "health": {…}}`, exit 0;
- `{"status": "unhealthy", "health": {…}}`, exit 1: the files are written, but show the health numbers and tell the learner before planning on that transcript; a rerun needs `--force`;
- `{"status": "error", "message": …}`, exit 1, nothing written: the source had no timed text (`no timed segments found`), the input could not be read or parsed, a tool or ASR backend failed, the video page could not be read, or the URL is a playlist. Show `message` to the learner;
- `acquire url` only: `{"status": "needs_user_file", "message": …}`, exit 3.

`health` has the keys `coverage` (share of the duration the segments span, healthy from 0.9), `repetition` (share of segments repeating the previous one, healthy up to 0.5), `spots_ok` (segments near 10%, 50% and 90% of the duration), `overrun` (a segment ends more than 2 s after the duration), `loop` (five or more identical segments in a row), `ok`, and `duration_known`. With an unknown duration, coverage and spots cannot be measured and count as fine.

An existing `sources/transcript.json` without `--force` stops the command before any work (exit 3, one line on stderr). A budget or backend problem (exit 3) is also one stderr line, with no JSON on stdout.
