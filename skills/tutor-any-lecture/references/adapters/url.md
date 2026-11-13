Adapter: public video links. One public video page, captions first; audio only with the learner's consent.

## Platform

Public video sites that yt-dlp supports: YouTube, Bilibili and many others. Command: `tutor-any-lecture acquire url --url U --unit DIR [--force] [--budget-minutes N]`. It reads the video page without cookies or credentials of any kind. `--budget-minutes` bounds speech recognition when it runs (default `max(30, 2 × the video length in minutes)`).

Lecture-capture and meeting platforms (Panopto, Kaltura, Mediasite, Echo360, YuJa, Opencast, Zoom), recognised by yt-dlp's extractor or by the address, are read through their captions only: their audio is never downloaded, whatever the profile says, and a token in their address is removed before it is stored.

## URL patterns

The address of one video, for example `https://www.youtube.com/watch?v=<id>`, `https://youtu.be/<id>` or `https://www.bilibili.com/video/<id>`. A playlist or channel address is refused: one video per unit, so ask the learner which video and create one unit for each.

## Where transcripts/captions live

In the site's caption tracks: manual ones uploaded by the owner, and automatic ones made by the site. The order of fallback:
1. a manual track in the lecture language (the profile's `lecture_language`; when auto, the video's declared language);
2. the original-language automatic track, never a machine-translated one, also when the manual track turns out unusable;
3. only when the profile has `public_video_audio: on` with a recorded consent (`public_video_audio_consent`, see [profile](../profile.md)), and never on a capture platform: the audio stream alone is downloaded to a temporary folder, transcribed locally (as in [local](local.md)) and deleted;
4. otherwise (the switch off, or a capture platform), when a caption track was found but none was healthy, the best one (by coverage) is kept and reported as `unhealthy`; with no readable track the command stops with `needs_user_file` (below). With the switch on and no recorded consent, the command exits 3 with the notice instead, even when unhealthy caption tracks were read.

A healthy track is used at once. Rolling repeats in automatic captions are removed on import.

## Read-only steps

1. When the learner gave only the link, run `tutor-any-lecture acquire url --url U --info` to name the unit: it writes nothing and prints `{"status": "ok", "title", "duration", "uploader", "manual_captions", "automatic_captions"}` (`manual_captions` lists language codes; `automatic_captions` is true or false). Name the unit folder after `title`, made safe for a folder name (see SKILL.md, Acquire).
2. If the learner has the slides, run `tutor-any-lecture slides --pdf F --unit DIR` first (the ASR prompt, if ASR runs, uses its terms).
3. Run `tutor-any-lecture acquire url --url U --unit DIR`.
4. Outcome, one JSON object on stdout:
   - `{"status": "ok", "health": {…}, "title": …, "acquisition": …}`, exit 0: `sources/transcript.json` and `sources/source.json` are written, with `"kind": "url"`, the `url`, and `"acquisition"` "cc" (manual captions), "auto" (automatic captions) or "asr";
   - `{"status": "unhealthy", "health": {…}, "title": …, "acquisition": …}`, exit 1: the kept caption track, or the ASR transcript, is unhealthy; the files are written. Show the health numbers (`coverage`, `repetition`, `spots_ok`, `overrun`, `loop`) and tell the learner before planning on that transcript;
   - `{"status": "error", "message": …}`, exit 1, nothing written: the video page could not be read (private, removed, region- or login-locked), the URL is a playlist, the audio could not be decoded, or the ASR backend failed. Show `message` to the learner;
   - `{"status": "needs_user_file", "message": …}`, exit 3: no caption track could be read, and audio may not or cannot be downloaded; on a capture platform the message says its recordings are not downloaded;
   - other exit-3 cases, one line on stderr and no JSON: the transcript already exists (rerun with `--force` to replace it); speech recognition is needed and not installed (with the learner's agreement, run the installer again with `--with-asr`, Windows `-WithAsr`; see SKILL.md, Step 0); it ran out of time budget (rerun with a larger `--budget-minutes`); or `public_video_audio` is on without a recorded consent (the notice is printed on stderr; see below).
5. On `needs_user_file`, offer the learner the three ways forward the message names:
   - provide the video or audio file: use [local](local.md);
   - provide a transcript or caption file: use [import](import.md);
   - enable `public_video_audio` in the profile: show the consent notice through `tutor-any-lecture profile set public_video_audio on` (see [profile](../profile.md)); only after the learner agrees, rerun it with `--i-understand`, then rerun `acquire url`. Never turn it on for them.
6. With a transcript, run `tutor-any-lecture slides suspects --unit DIR`.

Because source.json has `"kind": "url"` and the `url`, every timestamp in explanation.md links to the video at that time: write plain `(mm:ss)` citations and run `tutor-any-lecture cite link --unit DIR` before the gate (see [writing](../writing.md), Citations).

## Downloads offered?

`tutor-any-lecture profile set public_video_audio on` prints this notice and exits 3 without changing anything:

> Turning this on lets tutor-any-lecture download the audio track of a video (YouTube, Bilibili and other sites yt-dlp supports) when no usable captions exist, transcribe it locally, then delete it. The choice and the responsibility are yours for every address you give, a school's or a meeting platform's recordings included: check that you are allowed to download it, and follow its site's terms and copyright; use it for personal study only. The tool uses no cookies and no login, so a recording behind a sign-in is out of reach, and DRM is never circumvented.

Only after the learner agrees, run `tutor-any-lecture profile set public_video_audio on --i-understand`: it records the day in profile.yaml as `public_video_audio_consent`. Audio is downloaded only while the switch is on and that consent is recorded; a switch turned on by hand in profile.yaml without it makes `acquire url` print the notice and exit 3 without downloading anything.

Caption files are always fetched; they are text. Audio is downloaded only then, audio only (never video), never from a capture platform, into a temporary folder that is deleted after transcription. Cookies are never read, so login-only media is out of reach by design; DRM-protected media is never downloaded.

## Known pitfalls

- An automatic track in another language may be a machine translation; it is never picked when an original exists. When the only tracks are translations, the run behaves as if there were no captions.
- Automatic captions have no punctuation and mis-hear names: slides and `slides suspects` matter more here.
- A video that needs a login, age check or membership cannot be read. Do not offer cookies or a login; ask the learner for a file instead.
- Time links use `&t=<seconds>s`, or `?t=<seconds>s` when the URL has no query; `cite link` writes them. For a platform without a time parameter, cite plain `(mm:ss)` and do not run `cite link`.

## Verified by (name/date) or "experimental"

experimental
