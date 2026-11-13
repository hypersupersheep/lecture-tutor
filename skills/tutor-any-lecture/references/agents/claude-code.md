# Claude Code

The workflow is SKILL.md's; this page only maps it onto Claude Code's tools.

## Install

The installer copies the skill to `~/.claude/skills/tutor-any-lecture/` when `~/.claude` exists (or with `--agents claude`); Claude Code then lists `tutor-any-lecture` among its skills. The command itself is installed as SKILL.md, Step 0 says, with `--cli-only` because the skill is already in place. On Windows the installer is `powershell -NoProfile -ExecutionPolicy Bypass -File "<skill folder>\scripts\install.ps1"` with its flags (`-Yes -CliOnly`, as in Step 0); it works in Windows PowerShell 5.1 and in PowerShell 7, and from Git Bash. `bash install.sh` is not for Windows.

## Running the command

Run every `tutor-any-lecture …` call with the Bash tool (on Windows it runs Git Bash, so the same quoting applies). Put every path in single quotes, and write a single quote inside a path as `'\''`: `it's week 4.mp4` becomes `'it'\''s week 4.mp4'`. Then no file name can run as shell code. If the command is not on PATH, use the absolute path stored in `cli-path`, quoted the same way.

The installer, `acquire local`, `transcribe`, and `acquire url` when it transcribes audio can run for many minutes: give the Bash call its maximum timeout (10 minutes), or run it in the background and wait for it to finish. A stopped command cleans up after itself; run it again.

## Browser tools

Panopto and Moodle pages need a browser that already holds the learner's login. Claude Code can use either:
- **Claude in Chrome**, the browser extension that acts in the learner's own Chrome (tools named `mcp__claude-in-chrome__*`, with `javascript_tool` for page scripts);
- **the built-in browser** of the Claude desktop app (tools named `mcp__Claude_Browser__*`, with its own `javascript_tool`), whose sign-ins persist across sessions.

Use whichever is connected; load its tools before the first step. Navigate, read the page as text, and run page scripts with `javascript_tool`: the activity listing and `scripts/panopto_extract.js` from [panopto](../adapters/panopto.md) are pasted as the script's code (read the file with the Read tool first). Never click Download, Edit, Share or similar controls, and stop at any sign-in or "Verify you are human" page and ask the learner.

## Large script results

A `javascript_tool` result larger than about 50 KB is not placed in the conversation: Claude Code saves it to a file and shows its path, like `…/tool-results/toolu_….json`. That file holds a list `[{"type": "text", "text": "<json>"}]`, which `acquire panopto` reads as it is. Pass the path straight on:

```
tutor-any-lecture acquire panopto --extract <path shown in the tool result> --unit DIR
```

A smaller result appears inline: write it unchanged to a file with the Write tool, then pass that file. Never retype or summarise the transcript.

## Delivering

Send the delivered files to the learner with the session's file-sharing tool when one exists; otherwise list their absolute paths.
