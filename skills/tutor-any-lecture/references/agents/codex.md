# Codex

The workflow is SKILL.md's; this page only maps it onto Codex.

## Install

The installer copies the skill to `~/.codex/skills/tutor-any-lecture/` when `~/.codex` exists (or with `--agents codex`). The command itself is installed as SKILL.md, Step 0 says.

## Calling the command

Run each `tutor-any-lecture …` call as a shell command with every path quoted, or as an argument list when the tool takes one. If the command is not on PATH, read its absolute path from `${XDG_CONFIG_HOME:-$HOME/.config}/tutor-any-lecture/cli-path` (or `%APPDATA%\tutor-any-lecture\cli-path` on Windows) and use that.

A sandbox that blocks network access stops the commands that need it: `acquire url` (the video site) and the first local transcription (the speech model download). When one fails that way, ask the learner to allow network access for that command, and run it again; every other command works offline.

## Without browser tools

Panopto and Moodle pages are out of reach without a browser that holds the learner's login. Then:
- ask the learner for the files instead: the slide PDF, and a transcript or caption export (SRT, VTT or TXT; see [import](../adapters/import.md)), or the recording itself when the platform offers a download (see [local](../adapters/local.md));
- public video links still work through `acquire url` (see [url](../adapters/url.md)), because the command fetches captions itself;
- never ask for a password or a cookie to get around the missing browser.

If browser tools are connected, follow [panopto](../adapters/panopto.md) and [moodle](../adapters/moodle.md) with them: navigate, read the page, run page scripts, and save a large script result to a file before passing it to `acquire panopto --extract`.
