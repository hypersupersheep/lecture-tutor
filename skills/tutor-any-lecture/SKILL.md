---
name: tutor-any-lecture
description: Use when the user wants to learn from a lecture, recorded class, talk or course video, or from slides alone, and wants explanation notes, a pretest, a quiz, Anki cards or an overview map made from it (e.g. "teach me this lecture", "quiz me on week 4", "把这节课讲给我"). Works with local files, YouTube/Bilibili links, Panopto/Moodle pages, transcripts and PDFs.
---

# Tutor Any Lecture

Turn one lecture (a recording, a link, a transcript or a slide deck) into a cited explanation note, a pretest, a quiz bank, Anki cards and an overview map, checked by a gate before delivery; then quiz the learner after reading and at spaced reviews. The `tutor-any-lecture` command does the deterministic work: acquisition, transcription, checks and rendering. You write prose and JSON, grade answers and call the command.

## Running commands

- Pass an argument list when your tool takes one; otherwise quote every argument as your agent note says (see References), so a file name can never run as shell code.
- Paths: use the workspace that `tutor-any-lecture profile show` prints; it is absolute. The tool expands `~` in every path argument.
- Installing, `acquire local`, `transcribe`, and `acquire url` when it transcribes audio can run for many minutes: run them with the longest timeout your shell tool allows, or in the background. A command that was stopped cleans up after itself and can be run again.

## Step 0: Check the tool

- Run `tutor-any-lecture doctor --json`. Ready (`"ready": true`, exit 0): continue. Not ready (exit 3): show the `fix` lines of the failing checks and offer to apply them. A fix that starts with "Optional:" never blocks readiness.
- If the command is not found, read the CLI's absolute path from `${XDG_CONFIG_HOME:-$HOME/.config}/tutor-any-lecture/cli-path` (macOS, Linux) or `%APPDATA%\tutor-any-lecture\cli-path` (Windows), and use that path in place of `tutor-any-lecture` for every call in this session.
- If neither works, offer to install the command with the installer in this skill's folder (below, `<skill folder>`). The skill is already installed, so pass `--cli-only` (`-CliOnly` on Windows). Run it only after the user agrees:
  - macOS, Linux: `scripts/install.sh`, as `bash '<skill folder>/scripts/install.sh' --yes --cli-only`;
  - Windows (Windows PowerShell 5.1 or PowerShell 7, also from Git Bash): `scripts/install.ps1`, as `powershell -NoProfile -ExecutionPolicy Bypass -File "<skill folder>\scripts\install.ps1" -Yes -CliOnly`. `bash install.sh` is not for Windows.
- Installer exit codes: 0 ready (the command's path is now in `cli-path`); 1 failed or cancelled: show its stderr; 2 a bad option: correct the command; 3 needs action: when its last stdout line is the doctor JSON (`"ready": false`), show the failing checks' `fix` lines; otherwise show what it printed on stderr (uv and Python 3.10+ missing, git missing, or a Windows shell, for which it prints the PowerShell command to run instead).
- Speech recognition is an add-on, needed only for audio or video that has no captions. When a command exits 3 and says speech recognition is not installed, tell the learner it is a large download (several hundred megabytes, more on Apple Silicon); with their agreement, run the installer again with `--with-asr` (`-WithAsr`) and `--cli-only` (`-CliOnly`), then rerun the command.
- On first use (the workspace folder is missing or holds no unit; a unit is a file matching `<workspace>/courses/*/*/plan.json`), after doctor is ready, run `tutor-any-lecture selftest` once. Continue on exit 0; otherwise stop and report its output.

## Understand the request

Infer what the user wants (which lecture, which outputs, how deep) and the settings from the conversation. On the first run ask no questions; use the defaults. Settings live in `profile.yaml` in the config dir (the folder that holds `cli-path`); `tutor-any-lecture profile show` prints them. After delivery, invite the user to set them with `tutor-any-lecture profile set KEY VALUE`; keys, value sets and the consent gate are in [profile](references/profile.md).

## Acquire

1. Pick the unit folder first: `<workspace>/courses/<course>/<unit>/`, and remember both folder names. They become `course` and `unit` in plan.json, in `progress/<course>.jsonl` and in the card GUIDs. Take them from the user's wording, following the naming rule in [teaching](references/teaching.md) (write `CS 101 - Intro`, not `CS 101: Intro`); reuse them unchanged for later units of the same course.
   - When the learner gives only a link, run `tutor-any-lecture acquire url --url U --info` first (it writes nothing) and name the unit after its `title`, made safe for a folder name (`Lecture 3: Graphs/BFS` becomes `Lecture 3 - Graphs - BFS`). Ask for the course only when nothing (the title, the uploader, the conversation) suggests one.
2. For a folder of materials, run `tutor-any-lecture acquire route --folder <materials> --unit <unit folder>`. It only plans. Then:
   - a question about `unsafe-name`: ask the learner to rename the files it lists, then run the route again;
   - any other question: ask the learner its `text` and have them pick one of its `candidates`; for the pick `candidates[i]`, run that question's `argv[i]` as well;
   - a step with `runnable: false` is material this version cannot read (a PPTX deck, photos of slides, slides that appear only in the video): tell the learner, ask for a PDF export, then run `tutor-any-lecture slides --pdf`;
   - run every other step's `argv` as given (an import step may carry `--media`), with the cli-path in place of its first element when needed, in this order: transcript import or panopto, then `slides --pdf`, then `acquire local`.
3. Otherwise pick the adapter for the source:
   - a local video or audio file: [local](references/adapters/local.md), `tutor-any-lecture acquire local --file F --unit DIR`;
   - a public video link: [url](references/adapters/url.md), `tutor-any-lecture acquire url --url U --unit DIR [--budget-minutes N]`;
   - a transcript or caption file: [import](references/adapters/import.md), `tutor-any-lecture acquire import --file F --unit DIR`;
   - a Panopto recording: [panopto](references/adapters/panopto.md), `tutor-any-lecture acquire panopto --extract JSON --unit DIR`;
   - slides on a Moodle course page: [moodle](references/adapters/moodle.md).
   Panopto and Moodle pages need an agent with browser tools; see the agent notes under References.
4. When there is a PDF, run `tutor-any-lecture slides --pdf F --unit DIR` before any transcription (the ASR prompt uses its terms). Slides alone make a slides-only unit: its note cites slides only, never times.
5. Acquisition commands print one JSON object; exit 0 is `ok`. On exit 1 read `status`: `unhealthy` means the transcript (captions too) was kept with its `health` numbers: show them and tell the learner before planning on that transcript; `error` carries a `message`: show it to the learner. Exit 3 needs the user: `needs_user_file` (offer a media file, a transcript file or public video audio), consent, speech recognition (Step 0), a bigger `--budget-minutes`, or `--force` to overwrite. Details: [gate](references/gate.md).
6. A video's audio is downloaded only when the profile has `public_video_audio` on with a recorded consent ([url](references/adapters/url.md)), whatever the platform. The tool never uses the learner's login, so a recording behind a sign-in is out of reach: use the platform's captions, or a file the learner downloaded.
7. With a transcript, run `tutor-any-lecture slides suspects --unit DIR`. Suspects feed the errata section; the transcript is never edited.

## Read and plan

Read the transcript, slides, chapters and suspects, then write plan.json in the unit folder (its shape, what the command rejects, `sections` and the concept `type` values are in [teaching](references/teaching.md)). Resolve every value to a concrete one:
- `note_language`: the profile value, or the language of the conversation when the profile says auto;
- `lecture_language`: the profile value, or, when auto, source.json's `lecture_language`, or the language you read in the transcript or slides;
- both as lowercase primary subtags ("en", "zh", "ja"), never "auto";
- `goal`, `outputs` and `quote_density` from the profile; `output_target` from the profile, with notion written as markdown;
- `duration_s` from source.json's `duration` (null when unknown);
- `course` and `unit`: the two folder names from Acquire; `tracked`: 5 concept ids, or all when there are fewer than 5.

## Write

Follow [writing](references/writing.md) (the note contract) and [teaching](references/teaching.md) (items, cards, map; items.json layout). Order of work:
1. write items.json, then run `tutor-any-lecture items assign --unit DIR`;
2. write the pretest section of explanation.md from `tutor-any-lecture items next --unit DIR --phase pre`;
3. write the rest of the note, with plain time citations such as `(13:42)`; when the unit came from a link, run `tutor-any-lecture cite link --unit DIR` before the gate: it turns them into links to the video (it can be run again);
4. write cards.json and map.json for the outputs listed in plan.json.

For each output plan.json leaves out, skip its artefact and its step: no "cards": cards.json, `cards export` and `cards add-misses`; no "map": map.json and `map mermaid`; no "pretest": the pretest section and the pretest in chat (with "quiz" listed, the gate then warns `pretest_complete`); no "quiz": the `tal:check` sections and every quiz in chat (pretest, post quiz, reviews, practice), so nothing is logged for that unit; neither "pretest" nor "quiz": items.json and `items assign` too. explanation.md is always written: the gate reads it.

A command that finds plan.json, items.json, assignment.json, cards.json or map.json malformed exits 1 with one stderr line that starts with the file's name: fix that file, then rerun the command.

## Gate

Run `tutor-any-lecture cards export --unit DIR` when "cards" is in plan.outputs and `tutor-any-lecture map mermaid --unit DIR` when "map" is; then `tutor-any-lecture verify --unit DIR`. Fix and rerun until overall is PASS (exit 0). Report the `report` line exactly as printed; never claim a visual review that did not happen. The `measures:` line shows how close the note is to each limit. Exit codes and check names: [gate](references/gate.md).

## Pretest, then deliver

After the gate passes, when "quiz" and "pretest" are in plan.outputs, run the pretest in chat before the learner sees the note: the `items` of `tutor-any-lecture items next --unit DIR --phase pre`, one at a time. Ask how sure the learner is before you say whether the answer was right; then grade; then log both with `tutor-any-lecture progress log --unit DIR --item ID --phase pre --score S --confidence K`. Say that a low pretest score is normal.

Only then deliver the files: explanation.md, cards.tsv and the map files (`overview-<view>.mmd` for each view, or `overview.mmd`); where they go per `output_target` is in [markdown](references/output-targets/markdown.md) and [obsidian](references/output-targets/obsidian.md). With "quiz" listed, ask the learner to read the note and to tell you when they have.

## Post quiz

When the learner says they have read the note (only with "quiz" in plan.outputs):
1. run `tutor-any-lecture items next --unit DIR --phase post` and ask its `items` one at a time: confidence first, then grade, then log each with `tutor-any-lecture progress log --unit DIR --item ID --phase post --score S --confidence K`;
2. run `tutor-any-lecture cards add-misses --unit DIR` (when "cards" is in plan.outputs).

Reviews are counted from the day of the first post attempt. Until a `post` attempt exists, nothing else is ever due. For an answer given on another day, pass that day to `progress log` as `--date YYYY-MM-DD`; `progress due --date YYYY-MM-DD` shows what is due on a given day.

## Quiz me and reviews

- Which course: the one the learner names; otherwise every course with a log file under `<workspace>/progress/` (`<course>.jsonl`).
- Run `tutor-any-lecture progress due --course C`. Each entry names a `unit` and a `phase`; DIR is `<workspace>/courses/<course>/<unit>` (if that folder is missing, look for the plan.json under the workspace whose `course` and `unit` match; otherwise ask the learner).
- A `post` entry means that unit's post quiz is still owed: run Post quiz. For d1, d7 or d21, run `tutor-any-lecture items next --unit DIR --phase P` (for d1 and d21, first write the D or E variants its `missing` names), ask and log with `--phase P` as in Post quiz, then run `cards add-misses` (when "cards" is in plan.outputs).
- Anything the learner wants beyond what is due is practice: items from the `practice` list of items.json, or `tutor-any-lecture items get --unit DIR --id ID`, logged with `--phase practice`. From a course's third unit on, a quiz may add up to two practice items from earlier units, each logged against its own unit.
- `tutor-any-lecture progress render --course C` writes the progress page. Grading, confidence, variants and interleaving: [teaching](references/teaching.md).

## Optional extras

Extras are optional and never part of the gate.
- The audio lesson is experimental in this version (Apple Silicon only, its rules are written in Chinese) and is not offered unless the learner asks. Then follow the [audio script rules](references/audio-script-rules.md) and run `scripts/tts_synthesize.py` directly with any Python that has `mlx-audio` and numpy installed, with ffmpeg and ffprobe on PATH; `<python>` in that file means that interpreter. If mlx-audio is missing, tell the user to install it (`pip install mlx-audio`); never install it silently.
- Review sheet and hand-drawn overview map: the separate companion skills handwritten-notes-pdf and excalidraw-concept-map.

## Guardrails

- Never type, store or ask for passwords. Use the browser's existing login; at a login page, stop and ask the user to sign in.
- Never read browser cookies.
- Download media only when the profile allows it.
- Downloading audio is off until the learner switches it on; from then on it is their decision and their responsibility for every address. The tool does not check a platform's terms.
- Never circumvent DRM, and never use the learner's passwords or cookies. Downloading audio is the learner's choice and responsibility, through the public_video_audio switch.
- Every claim you attribute to the lecturer carries a (slide N) or (mm:ss) citation.
- Read-only on every platform: no submissions, posts or bookings. Course material stays local, for personal study.

## References

- [writing](references/writing.md): the note contract: citations, quotes, marker sections, length, structure.
- [teaching](references/teaching.md): plan.json and items.json shapes, variants, pretest, post quiz, reviews, cards, map.
- [gate](references/gate.md): the nine checks, statuses, exit codes, acquisition JSON.
- [profile](references/profile.md): settings, value sets, the consent gate, plan resolution.
- [local](references/adapters/local.md): local video or audio, local ASR.
- [url](references/adapters/url.md): public video links, captions first.
- [import](references/adapters/import.md): SRT, VTT, JSON and timestamped text transcripts.
- [panopto](references/adapters/panopto.md): Panopto recordings through the browser.
- [moodle](references/adapters/moodle.md): slides from a Moodle course page.
- [TEMPLATE](references/adapters/TEMPLATE.md): the headings for a new platform adapter.
- [claude-code](references/agents/claude-code.md): quoting, browser tools and large script results in Claude Code.
- [codex](references/agents/codex.md): Codex install path, quoting, running without browser tools.
- [generic](references/agents/generic.md): other agents, quoting, agents without browser tools, Claude.ai uploads.
- [markdown](references/output-targets/markdown.md): the unit folder layout and Markdown conventions.
- [obsidian](references/output-targets/obsidian.md): Obsidian links, highlights and the vault copy.
