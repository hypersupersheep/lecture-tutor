---
name: tutor-any-lecture
description: Use when the user wants to learn from a lecture, recorded class, talk or course video, or from slides alone, and wants explanation notes, a pretest, a quiz, Anki cards or an overview map made from it (e.g. "teach me this lecture", "quiz me on week 4", "把这节课讲给我"). Works with local files, YouTube/Bilibili links, Panopto/Moodle pages, transcripts and PDFs.
---

# Tutor Any Lecture

Turn one lecture (a recording, a link, a transcript or a slide deck) into a cited explanation note, a pretest, a quiz bank, Anki cards and an overview map, checked by a gate before delivery. The `tutor-any-lecture` command does the deterministic work: acquisition, transcription, checks and rendering. You write prose and JSON, grade answers and call the command. Pass every command as an argument list, never as one joined shell string.

## Step 0: Check the tool

- Run `tutor-any-lecture doctor --json`. Ready (`"ready": true`, exit 0): continue. Not ready (exit 3): show the failing checks' `fix` lines and offer to apply them.
- If the command is not found, read the CLI's absolute path from `${XDG_CONFIG_HOME:-$HOME/.config}/tutor-any-lecture/cli-path` (macOS, Linux) or `%APPDATA%\tutor-any-lecture\cli-path` (Windows), and use that path in place of `tutor-any-lecture` for every call in this session.
- If neither works, offer to run the installer that ships in this skill's folder: `scripts/install.sh` (macOS, Linux; for example `bash <this skill's folder>/scripts/install.sh --yes`) or `scripts/install.ps1` (Windows; `pwsh -File <this skill's folder>\scripts\install.ps1 -Yes`). Run it only after the user agrees. Exit 3 from the installer means one of two things. If its last stdout line is the doctor JSON (`"ready": false`), show the failing checks' `fix` lines, as for `doctor --json`. Otherwise uv and Python 3.10+ are missing: show the instructions it printed on stderr.
- On first use (the profile's workspace folder is missing or holds no unit; a unit is a file matching `<workspace>/courses/*/*/plan.json`), after doctor is ready, run `tutor-any-lecture selftest` once. Continue on exit 0; otherwise stop and report its output.

## Understand the request

Infer what the user wants (which lecture, which outputs, how deep) and the settings from the conversation. On the first run ask no questions; use the defaults. Settings live in `profile.yaml` in the config dir (the folder that holds `cli-path`); `tutor-any-lecture profile show` prints them. Value sets: `goal` deep|exam|quick; `terms` bilingual|note|original; `level` auto|beginner|intermediate|advanced; `output_target` markdown|obsidian|notion; `downloads` ask|allow; `public_video_audio` on|off.
After delivery, invite the user to set them with `tutor-any-lecture profile set KEY VALUE`; details in [profile](references/profile.md).

## Acquire

1. Pick the unit folder first: `<workspace>/courses/<course>/<unit>/`, and remember both folder names. They become `course` and `unit` in plan.json, in `progress/<course>.jsonl` and in the card GUIDs. Take them from the user's wording; keep them filesystem-safe (no path separators, no `..`, none of `/ \ : * ? " < > |`, no leading or trailing space, no trailing dot: write `CS 101 - Intro`, not `CS 101: Intro`); reuse them unchanged for later units of the same course.
2. For a folder of materials, run `tutor-any-lecture acquire route --folder <materials> --unit <unit folder>`. It only plans. For each entry of `questions`, ask the learner its `text` and have them pick one of its `candidates`; for the pick `candidates[i]`, run that question's `argv[i]` as well. Run everything in this order: transcript import or panopto, then `tutor-any-lecture slides --pdf`, then `tutor-any-lecture acquire local`, so a `media` answer runs after the `slides --pdf` step. Run each argv as a list, never joined into a shell string (with the cli-path in place of its first element when needed), and skip steps with `runnable: false`.
3. Otherwise pick the adapter for the source:
   - a local video or audio file: [local](references/adapters/local.md), `tutor-any-lecture acquire local --file F --unit DIR`;
   - a public video link: [url](references/adapters/url.md), `tutor-any-lecture acquire url --url U --unit DIR`;
   - a transcript or caption file: [import](references/adapters/import.md), `tutor-any-lecture acquire import --file F --unit DIR`;
   - a Panopto recording: [panopto](references/adapters/panopto.md), `tutor-any-lecture acquire panopto --extract JSON --unit DIR`;
   - slides on a Moodle course page: [moodle](references/adapters/moodle.md).
   Panopto and Moodle pages need an agent with browser tools; see the agent notes under References.
4. When there is a PDF, run `tutor-any-lecture slides --pdf F --unit DIR` before any transcription (the ASR prompt uses its terms). Slides alone make a slides-only unit: its note cites slides only, never times.
5. Acquisition commands print one JSON object. On exit 1 read `status`: for `unhealthy`, show the health numbers and tell the learner before planning on that transcript; for `error`, show `message` to the learner: the source had no timed text, the input could not be read, a tool failed, the video could not be reached, or the URL is a playlist (one video per unit). Exit 3 needs the user: a file, consent, a bigger budget, or `--force` to overwrite.
6. With a transcript, run `tutor-any-lecture slides suspects --unit DIR`. Suspects feed the errata section; the transcript is never edited.

## Read and plan

Read the transcript, slides, chapters and suspects, then write plan.json in the unit folder (its shape, `sections` and the concept `type` values are in [teaching](references/teaching.md)). Resolve every value to a concrete one:
- `note_language`: the profile value, or the language of the conversation when the profile says auto;
- `lecture_language`: the profile value, or, when auto, source.json's `lecture_language`, or the language you read in the transcript or slides;
- both as lowercase primary subtags ("en", "zh", "ja"), never "auto";
- `goal` and `outputs` from the profile; `output_target` from the profile, with notion written as markdown;
- `duration_s` from source.json's `duration` (null when unknown);
- `course` and `unit`: the two folder names from Acquire; `tracked`: 5 concept ids, or all when there are fewer than 5.

## Write

Follow [writing](references/writing.md) (the note contract) and [teaching](references/teaching.md) (items, cards, map; items.json layout). Order of work:
1. write items.json, then run `tutor-any-lecture items assign --unit DIR`;
2. write the pretest section of explanation.md from `tutor-any-lecture items next --unit DIR --phase pre`;
3. write the rest of the note;
4. write cards.json and map.json for the outputs listed in plan.json.

A command that finds plan.json, items.json, assignment.json, cards.json or map.json malformed exits 1 with one stderr line that starts with the file's name: fix that file, then rerun the command.

## Gate

Run `tutor-any-lecture cards export --unit DIR` when "cards" is in plan.outputs and `tutor-any-lecture map mermaid --unit DIR` when "map" is; then `tutor-any-lecture verify --unit DIR`. Fix and rerun until overall is PASS (exit 0). Report the `report` line exactly as printed; never claim a visual review that did not happen. Exit codes and check names: [gate](references/gate.md).

## Deliver and pretest

Deliver the files; where they go per `output_target` is in [markdown](references/output-targets/markdown.md) and [obsidian](references/output-targets/obsidian.md). Then, before the learner reads the note, run the pretest in chat: one question at a time, as in teaching.md, logging each answer with `tutor-any-lecture progress log --unit DIR --item ID --phase pre --score S --confidence K`. Say that a low pretest score is normal.

## Quiz mode and reviews

- `tutor-any-lecture items next --unit DIR --phase P` gives the items to ask, with P in pre|post|d1|d7|d21 (`practice` is an argparse error there). Practice items come from the `practice` list of items.json, or from `tutor-any-lecture items get --unit DIR --id ID`, and are logged with `--phase practice`.
- Grade each answer, then run `tutor-any-lecture progress log --unit DIR --item ID --phase P --score S --confidence K` (no `--course`; course and unit come from plan.json).
- "Review" starts from `tutor-any-lecture progress due --course C`. For a due entry, DIR is `<workspace>/courses/<course>/<entry.unit>`; if that folder is missing, look for the plan.json under the workspace whose `course` and `unit` match; otherwise ask the learner.
- `tutor-any-lecture progress render --course C` writes the progress page; `tutor-any-lecture cards add-misses --unit DIR` adds miss cards after a quiz.

Protocol details (grading, confidence, D and E variants, interleaving): [teaching](references/teaching.md).

## Optional extras

Extras are optional and never part of the gate.
- Audio lesson, Apple Silicon macOS only in M1: follow the [audio script rules](references/audio-script-rules.md) and run `scripts/tts_synthesize.py` directly with any Python that has `mlx-audio` and numpy installed, with ffmpeg and ffprobe on PATH; `<python>` in that file means that interpreter. If mlx-audio is missing, tell the user to install it (`pip install mlx-audio`); never install it silently.
- Review sheet and hand-drawn overview map: the separate companion skills handwritten-notes-pdf and excalidraw-concept-map.

## Guardrails

- Never type, store or ask for passwords. Use the browser's existing login; at a login page, stop and ask the user to sign in.
- Never read browser cookies.
- Download media only when the profile allows it.
- Never capture streams of recordings whose downloads are disabled, and never circumvent DRM.
- Every claim you attribute to the lecturer carries a (slide N) or (mm:ss) citation.
- Read-only on every platform: no submissions, posts or bookings. Course material stays local, for personal study.

## References

- [writing](references/writing.md): the note contract: citations, marker sections, length, structure.
- [teaching](references/teaching.md): plan.json and items.json shapes, variants, pretest, quiz protocol, cards, map.
- [gate](references/gate.md): the nine checks, statuses, exit codes, acquisition JSON.
- [profile](references/profile.md): settings, value sets, the consent gate, plan resolution.
- [local](references/adapters/local.md): local video or audio, local ASR.
- [url](references/adapters/url.md): public video links, captions first.
- [import](references/adapters/import.md): SRT, VTT, JSON and timestamped text transcripts.
- [panopto](references/adapters/panopto.md): Panopto recordings through the browser.
- [moodle](references/adapters/moodle.md): slides from a Moodle course page.
- [TEMPLATE](references/adapters/TEMPLATE.md): the headings for a new platform adapter.
- [claude-code](references/agents/claude-code.md): browser tools and large script results in Claude Code.
- [codex](references/agents/codex.md): Codex install path and running without browser tools.
- [generic](references/agents/generic.md): other agents, agents without browser tools, Claude.ai uploads.
- [markdown](references/output-targets/markdown.md): the unit folder layout and Markdown conventions.
- [obsidian](references/output-targets/obsidian.md): Obsidian links, highlights and the vault copy.
