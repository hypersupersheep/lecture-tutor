# Profile

The learner's settings live in one YAML file, `profile.yaml`, in the config dir:
- macOS and Linux: `${XDG_CONFIG_HOME:-$HOME/.config}/tutor-any-lecture/profile.yaml`;
- Windows: `%APPDATA%\tutor-any-lecture\profile.yaml`.

The same folder holds `cli-path`. A missing or empty file means every default. The file is read on every command; nothing caches it.

- `tutor-any-lecture profile show` prints the effective profile as one JSON line.
- `tutor-any-lecture profile set KEY VALUE` changes one key and prints the new profile. An unknown key or a value outside its set is a `ProfileError`: one line on stderr, exit 1, nothing written.

**First run asks nothing.** Infer what you can from the conversation, use the defaults for the rest, and deliver. After delivery, invite the learner to set what matters to them, one line per suggestion with the exact `tutor-any-lecture profile set KEY VALUE` command.

## Fields

In file order, with defaults:

| key | default | values | what it does |
|---|---|---|---|
| `note_language` | `auto` | a language code, or auto | language of the note; auto means the language of the conversation |
| `lecture_language` | `auto` | a language code, or auto | language of the lecture, for captions and ASR; auto means detected |
| `terms` | `bilingual` | bilingual, note, original | how technical terms are written (see [writing](writing.md)) |
| `level` | `auto` | auto, beginner, intermediate, advanced | how much background the note explains; auto means judged from the conversation and, later, from the pretest scores |
| `goal` | `deep` | deep, exam, quick | length, coverage and quiz size (table below) |
| `outputs` | `[explanation, pretest, quiz, cards, map]` | a list | which outputs a unit gets |
| `output_target` | `markdown` | markdown, obsidian, notion | where the files go ([markdown](output-targets/markdown.md), [obsidian](output-targets/obsidian.md)); notion is delivered as Markdown for import |
| `workspace` | `~/TutorAnyLecture` | a folder | holds `courses/<course>/<unit>/` and `progress/` |
| `obsidian_vault` | empty | a folder | the vault for the obsidian target |
| `naming` | `default` | default | file naming in the vault; only default exists in M1 |
| `downloads` | `ask` | ask, allow | ask (default) asks before every download; allow permits only downloads the platform itself offers |
| `public_video_audio` | `off` | on, off | audio download from public video sites when no usable captions exist; consent gate below |
| `platforms` | `{}` | a mapping | base URLs of the learner's platforms, for example `moodle: https://moodle.example.edu`; the adapters use them as `<moodle_url>` and `<panopto_url>` |

`outputs` and `platforms` are set as YAML: `tutor-any-lecture profile set outputs "[explanation, quiz]"`. In the file itself, quote a value that YAML would read as a boolean (yes, no, true, false); `public_video_audio: on` and `off` are understood unquoted.

## The consent gate

`tutor-any-lecture profile set public_video_audio on` prints this notice and exits 3, writing nothing:

> Turning this on lets tutor-any-lecture download the audio track of public videos (YouTube, Bilibili and other sites yt-dlp supports) when no usable captions exist, transcribe it locally, then delete it. You are responsible for following each site's terms and copyright; use it for personal study only. Cookies, DRM-protected media and login-only media are never downloaded.

Show the notice to the learner. Only after they have read it and agreed, rerun with `--i-understand`: `tutor-any-lecture profile set public_video_audio on --i-understand`. Never turn it on for the learner, and never pass `--i-understand` on your own initiative. Turning it off needs no consent.

## From profile to plan.json

plan.json never holds "auto". Resolve each value when you write it:
- `note_language`: the profile value, or the language of the conversation when the profile says auto;
- `lecture_language`: the profile value, or, when auto, source.json's `lecture_language`, or the language you read in the transcript or slides;
- both as lowercase primary subtags ("en", "zh", "ja");
- `goal` and `outputs` from the profile; `output_target` from the profile, with notion written as markdown;
- `duration_s` from source.json's `duration` (null when unknown);
- `course` and `unit`: the unit's two folder names; `tracked`: 5 concept ids, or all when there are fewer than 5.

## Goal

| goal | the note | quiz and cards |
|---|---|---|
| deep (default) | the whole lecture in order, every slide explained or listed as not covered; 44–89 CJK characters / 26–53 words per minute | full sessions over the tracked and practice items; up to 25 core cards |
| exam | weighted to what will be examined: definitions, results, methods, the lecturer's exam hints; 30–70 / 18–42 per minute | exam-style items first, modelled on past papers when the learner provides them; interleaved review and more practice items; up to 25 core cards |
| quick | the main line only; 10–25 / 6–15 per minute | 5–8 items per session; up to 10 core cards |

Every goal keeps the citations and the faithfulness rules; goal changes length and coverage, never inserts extra sections into the lecture prose. items.json carries A, B and C for every tracked concept under every goal.

## Content type

plan.json's `content_type` is your call per unit, from what the lecture is mostly made of:

| content_type | typical lecture | note emphasis | item kinds |
|---|---|---|---|
| formula | derivations, models, proofs | numbered equations, each step's rule, worked examples | derivation and "why" items, apply |
| code | programming, data analysis | code with what it prints, common errors | `predict_output`, `complete_code` |
| concept | theory, history, argument | distinctions, cases, the lecturer's examples | `contrast`, `which_method`, cases |
| mixed | a combination | as above, section by section | a combination |
