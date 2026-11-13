# Other agents

The workflow is SKILL.md's. This page covers agents other than Claude Code and Codex, agents without browser tools, Claude.ai uploads, and the Cowork mode of the Claude desktop app.

## Install

For agents that read `~/.agents/skills`, the installer copies the skill to `~/.agents/skills/tutor-any-lecture/` when `~/.agents` exists (or with `--agents agents`). For any other agent, copy the folder `tutor-any-lecture` into that agent's skills folder by hand. The command itself is installed as SKILL.md, Step 0 says; any agent that can run shell commands can use it.

## No browser tools

Panopto and Moodle pages are out of reach: they need a browser that already holds the learner's login. Ask for files instead:
- the slide PDF (see [moodle](../adapters/moodle.md) for where it usually is);
- a transcript or caption export, SRT, VTT or TXT (see [import](../adapters/import.md));
- or the recording itself when the platform offers a download (see [local](../adapters/local.md)).

Public video links still work through `acquire url` (see [url](../adapters/url.md)). Never ask for passwords or cookies to make up for the missing browser.

## Claude.ai upload

Zip the folder `tutor-any-lecture` and upload it as a skill. Claude.ai cannot reach files on the learner's computer and cannot process large videos, so this route works from slides, captions and transcripts only: no local media and no local speech recognition. Step 0 still applies in Claude.ai's own environment; if doctor cannot become ready there, the gate cannot run: tell the learner, and suggest an agent on their own computer.

## Cowork (Claude desktop)

The workflow, the writing contract and the guardrails are the same; only the differences below apply. This path has not been run end to end; when the environment behaves differently from this page, follow what you see and tell the learner.

- **Connect folders first.** Cowork cannot see the learner's files until they are connected: request the workspace folder (and the Obsidian vault, if the target is obsidian) with the folder-request tool, for example `mcp__cowork__request_cowork_directory`; skip folders already connected.
- **Two path views.** Read, Write and Edit use the host's paths. The shell runs in a Linux virtual machine where connected folders appear under other paths (usually `/sessions/<session>/mnt/<folder>/`): run `ls` to find them before using them.
- **Tool mapping.**

  | SKILL.md says | in Cowork |
  |---|---|
  | run a command | the VM shell tool (`mcp__workspace__bash`; older versions call it `Bash`) |
  | install the command | inside the VM, per Step 0; this changes nothing on the host |
  | deliver files | `mcp__cowork__present_files`, for files in the outputs or uploads folder or a connected folder |
  | browser tools, page scripts | the built-in browser tools (`mcp__Claude_Browser__*`), sharing the desktop app's sign-ins |
  | scratch and working files | the outputs folder |

- **Network.** The VM's network allows only package registries and code hosts (PyPI, npm, GitHub, the Ubuntu archive) and Anthropic. Moodle and Panopto are reachable only through the browser tools, and video sites usually not at all.
- **Scripts.** Script paths start from the Base directory shown when the skill loads. If the shell cannot read that path, read the script with Read, write it to the outputs folder and run it from there. `scripts/panopto_extract.js` is pasted into the page-script tool and never goes through the shell.
- **Large script results.** A page-script result over about 50 KB is saved to a tool-results file. If the shell cannot read that file, fetch the result in pieces: let the script store its result in `window.__panopto`, then read `JSON.stringify(window.__panopto).slice(i, i + 40000)` for i = 0, 40000, …; write each piece with Write to the outputs folder, join them, check that the total length matches the page's, and pass the joined file to `tutor-any-lecture acquire panopto --extract`.
- **Not possible in the VM; do it back on the learner's computer** (for example in Claude Code):
  - the audio lesson: `scripts/tts_synthesize.py` needs macOS on Apple Silicon (the script for it can be written here);
  - the review sheet and the hand-drawn overview map from the companion skills: they need a local Chrome and fonts and libraries from CDNs;
  - local speech recognition when there is no transcript: the speech model cannot be downloaded through the VM's network. Ask the learner first, as always.

  Say clearly at delivery what was not done, so the learner can ask for it in an agent on their computer.
