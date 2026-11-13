Adapter template. Copy this file to `adapters/<platform>.md`, keep the seven headings in this order, and fill each one. An adapter describes how to get one lecture's transcript, slides and metadata into a unit folder with the existing `tutor-any-lecture` commands; it adds no new command.

## Platform

What the platform is, who typically uses it, and which `tutor-any-lecture` command its material ends up in (`acquire import`, `acquire panopto`, `acquire local`, `acquire url`, `transcribe`, or `slides --pdf`), with the exact flags, for example `tutor-any-lecture acquire import --file F --unit DIR [--duration SEC] [--force]`.

## URL patterns

The page addresses the agent will see, with placeholders for everything institution-specific: `<moodle_url>`, `<panopto_url>`, `<course>`, `<unit>`, `<id>`. No real institution's address.

## Where transcripts/captions live

Where on the page, or in which export, the timed text is found, and in which format. Say what to do when there is none.

## Read-only steps

Numbered steps the learner or agent can follow without changing anything on the platform: open, read, export what the platform offers. Then the command, and its outcome:
- for `acquire …` and `transcribe`: one JSON object on stdout, `{"status": "ok", "health": {…}}` (exit 0), `{"status": "unhealthy", "health": {…}}` (exit 1), `{"status": "error", "message": …}` (exit 1), and the exit-3 cases (see [gate](../gate.md));
- on exit 1 the agent reads `status`: for `unhealthy` it shows the health numbers and tells the learner before planning on that transcript; for `error` it shows `message`;
- an existing `sources/transcript.json` is replaced only with `--force` (otherwise exit 3).

Never click submit, post, edit, share or booking controls. At a login page, stop and ask the user to sign in.

## Downloads offered?

Which downloads the platform itself offers (and to whom), and how the profile's `downloads` setting applies: ask (default) asks before every download; allow permits only downloads the platform itself offers. Never circumvent DRM, and never use the learner's passwords or cookies; downloading audio is the learner's choice and responsibility, through the public_video_audio switch.

## Known pitfalls

Delays before material appears, misleading labels, empty transcripts, tokens in URLs that must not be read or recorded, bot checks to hand to the user.

## Verified by (name/date) or "experimental"

Who verified the steps on a real lecture and when, without personal names (for example "a contributor, 2026-11"), or "experimental" when no real run is known.
