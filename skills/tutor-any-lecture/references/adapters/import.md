Adapter: transcript import. A transcript or caption file the learner already has.

## Platform

Any source that exports timed text: caption files, a speech-to-text tool's output, and the transcript exports of meeting and lecture-capture platforms such as Zoom, Teams and Panopto. Command: `tutor-any-lecture acquire import --file F --unit DIR [--duration SEC | --media FILE] [--force]`; `--media` reads the lecture's length from its video or audio file.

## URL patterns

None: a file path. Paths with spaces or non-Latin characters work.

## Where transcripts/captions live

In the file the learner gives you. The parser is chosen by the file's suffix:
- `.srt`: SubRip, with `,` or `.` before the milliseconds;
- `.vtt`: WebVTT, header and cue settings allowed;
- `.json`: Whisper-style segments, either `{"segments": [{"start", "end", "text"}, …]}` or a bare list of such objects (times in seconds);
- `.txt` and any other suffix: timestamped text, one line per segment starting with `[m:ss]` or `[h:mm:ss]`; a line without a stamp continues the previous segment.

Files may be UTF-8 with or without a byte-order mark, with Windows or Unix line endings. DOCX is not read in M1: ask the learner for an SRT, VTT or TXT export of the same transcript instead (most platforms offer one next to the DOCX).

## Read-only steps

1. When the recording itself is at hand, pass it as `--media FILE`; otherwise ask for the media length if the learner knows it, and pass it in seconds as `--duration SEC` (not both). Without it the duration is unknown: the health check cannot measure coverage, and the gate's per-minute checks become warnings.
2. If there are slides, run `tutor-any-lecture slides --pdf F --unit DIR` (before or after the import; it never overwrites the source.json the import writes).
3. Run `tutor-any-lecture acquire import --file F --unit DIR --duration SEC`.
4. Outcome, one JSON object on stdout:
   - `{"status": "ok", "health": {…}}`, exit 0: `sources/transcript.json` and `sources/source.json` (`"kind": "transcript"`, `"acquisition": "import"`) are written;
   - `{"status": "unhealthy", "health": {…}}`, exit 1: the files are written, but read `status`, show the health numbers (`coverage`, `repetition`, `spots_ok`, `overrun`, `loop`) and tell the learner before planning on that transcript. A transcript that covers only part of the lecture, or ends after the given duration, lands here;
   - `{"status": "error", "message": …}`, exit 1, nothing written: the file does not exist, held no timed text (`no timed segments found`), was not UTF-8, or could not be parsed. Show `message` to the learner and ask for another export;
   - exit 3, one line on stderr: the unit already has `sources/transcript.json`; rerun with `--force` to replace it.
5. Run `tutor-any-lecture slides suspects --unit DIR` when the unit has slides.

## Downloads offered?

Nothing is downloaded. Where the learner gets the file depends on their platform; if `downloads` is ask, ask before you fetch an export for them from a page.

## Known pitfalls

- A plain-text transcript without `[m:ss]` stamps has no timed segments and fails with `error`; ask for the timed export.
- The last segment of a timestamped TXT has no end time; it is taken as 5 seconds, or up to the duration.
- Exports that add speaker names keep those names in the text; leave them out of quotes.

## Verified by (name/date) or "experimental"

experimental
