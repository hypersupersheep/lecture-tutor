# Codex

The workflow is SKILL.md's; this page only maps it onto Codex.

## Install

The installer copies the skill to `~/.codex/skills/tutor-any-lecture/` when `~/.codex` exists (or with `--agents codex`). The command itself is installed as SKILL.md, Step 0 says, with `--cli-only` because the skill is already in place. On Windows the installer is `powershell -NoProfile -ExecutionPolicy Bypass -File "<skill folder>\scripts\install.ps1"` with its flags (`-Yes -CliOnly`, as in Step 0); it works in Windows PowerShell 5.1 and in PowerShell 7, and from Git Bash. `bash install.sh` is not for Windows.

## Calling the command

Run each `tutor-any-lecture …` call as an argument list when the tool takes one. Otherwise run it as a shell command: put every path in single quotes, and write a single quote inside a path as `'\''`: `it's week 4.mp4` becomes `'it'\''s week 4.mp4'`. Then no file name can run as shell code. In PowerShell, write a single quote inside a single-quoted path as `''` instead. If the command is not on PATH, read its absolute path from `${XDG_CONFIG_HOME:-$HOME/.config}/tutor-any-lecture/cli-path` (or `%APPDATA%\tutor-any-lecture\cli-path` on Windows) and use that.

A sandbox that blocks network access stops the commands that need it: `acquire url` (the video site) and the first local transcription (the speech model download). When one fails that way, ask the learner to allow network access for that command, and run it again; every other command works offline. The installer and transcription can run for many minutes: give them the longest timeout the sandbox allows, or run them in the background.

## Without browser tools

Panopto and Moodle pages are out of reach without a browser that holds the learner's login. Then:
- ask the learner for the files instead: the slide PDF, and a transcript or caption export (SRT, VTT or TXT; see [import](../adapters/import.md)), or the recording itself when the platform offers a download (see [local](../adapters/local.md));
- public video links still work through `acquire url` (see [url](../adapters/url.md)), because the command fetches captions itself;
- never ask for a password or a cookie to get around the missing browser.

If browser tools are connected, follow [panopto](../adapters/panopto.md) and [moodle](../adapters/moodle.md) with them: navigate, read the page, run page scripts, and save a large script result to a file before passing it to `acquire panopto --extract`.
