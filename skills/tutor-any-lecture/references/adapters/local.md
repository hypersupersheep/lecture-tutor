Adapter: local files. A recording or slide deck already on the learner's computer, transcribed on this machine.

## Platform

The learner's own files: a lecture video or audio recording, and the slide PDF. Speech recognition (ASR) runs locally: mlx-whisper on Apple Silicon, faster-whisper elsewhere. It is an add-on that the installer adds with `--with-asr` (Windows `-WithAsr`); doctor is ready without it. Commands:
- `tutor-any-lecture acquire local --file F --unit DIR [--force] [--budget-minutes N]` for a video or audio file (the audio track is extracted with ffmpeg first);
- `tutor-any-lecture transcribe --audio F --unit DIR [--backend B] [--model M] [--budget-minutes N] [--force]` for an audio file transcribed as it is, optionally with a chosen backend (mlx or faster) and model;
- `tutor-any-lecture slides --pdf F --unit DIR [--images]` for the slides.

## URL patterns

None: file paths. Paths with spaces or non-Latin characters work, because every command takes its arguments as a list. Video: .mp4, .mkv, .mov, .webm, .avi, .m4v. Audio: .mp3, .m4a, .wav, .aac, .flac, .ogg. For a whole folder of materials, `tutor-any-lecture acquire route --folder <materials> --unit DIR` sorts the files and plans these commands (see SKILL.md, Acquire).

## Where transcripts/captions live

Nowhere yet: local ASR makes the transcript. If the learner already has a transcript or caption file for the recording, use the [import](import.md) adapter instead; it is faster and usually more accurate.

## Read-only steps

1. **Slides first.** When there is a slide PDF, run `tutor-any-lecture slides --pdf F --unit DIR` before any transcription: the ASR prompt is built from the slide terms in `sources/slides/pages.json`. On a run it printed `{"status": "ok", "pages": N, "labelled": M}` (M is the number of pages with a footer number) and exited 0. It writes `sources/slides/pages.json` and, when the unit has no `sources/source.json`, a slides-only `source.json` (`"kind": "slides-only"`); it never overwrites an existing source.json. Running it again replaced pages.json without `--force`. `--images` also saves one PNG per page.
2. **Slides only.** With no recording, stop here: the unit is slides-only, and its note cites slides only, never times.
3. **Transcribe.** Run `tutor-any-lecture acquire local --file F --unit DIR` (or `tutor-any-lecture transcribe --audio F --unit DIR` for an audio file as it is). It can run for many minutes: use the longest timeout your shell tool allows, or run it in the background; a stopped run cleans up and can be started again. The first transcription may download the speech model. The time budget defaults to `max(30, 2 × the media length in minutes)` minutes; `--budget-minutes N` changes it.
4. **Outcome.** One JSON object on stdout:
   - `{"status": "ok", "health": {…}}`, exit 0: `sources/transcript.json` and `sources/source.json` (`"kind": "local"`, `"acquisition": "asr"`) are written;
   - `{"status": "unhealthy", "health": {…}}`, exit 1: the files are written, but read `status`, show the health numbers (`coverage`, `repetition`, `spots_ok`, `overrun`, `loop`) and tell the learner before planning on that transcript;
   - `{"status": "error", "message": …}`, exit 1, nothing written: the input file does not exist or is a folder, no timed text came out, the file could not be read or decoded, or ffmpeg or the ASR backend failed. Show `message` to the learner;
   - exit 3, one line on stderr and no JSON: transcription did not finish within the budget (rerun with a larger `--budget-minutes`); speech recognition is not installed (the line says so: tell the learner it is a large download, several hundred megabytes and more on Apple Silicon, and with their agreement run the installer again with `--with-asr`, Windows `-WithAsr`, as SKILL.md, Step 0 says); a backend named with `--backend` is unknown or not installed (the line names the package); or the transcript already exists (rerun with `--force` to replace it).
5. **Suspects.** Run `tutor-any-lecture slides suspects --unit DIR`. On a run it printed `{"status": "ok", "suspects": N}` and exited 0, writing `sources/suspects.json`, a list of `{"time", "heard", "nearest", "ratio"}` (time in seconds). Run before any transcript exists, it exited 1 with `transcript not found: …; run an acquisition first` on stderr. It never edits the transcript.

## Downloads offered?

Nothing from the internet, except the speech model on the first transcription (doctor's `asr_model` check reports whether it is cached). The learner's files are only read; the extracted audio is a temporary file that is deleted.

## Known pitfalls

- On a machine without a GPU a 90-minute lecture can take a long time; check doctor first and raise `--budget-minutes` rather than retrying blindly.
- Recognition is weakest on names, numbers and formulas. The slide terms in the ASR prompt help; `slides suspects` flags what remains, and the note's errata section reports it. The transcript itself is never edited.
- A recording that starts long before the lecture (room noise, a break) can lower the health numbers; tell the learner rather than trimming the file yourself.

## Verified by (name/date) or "experimental"

experimental
