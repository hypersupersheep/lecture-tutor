# Output target: Obsidian

`output_target: obsidian`. The unit is built and checked exactly as for [markdown](markdown.md); only the note's links and highlights differ, and the note is copied into the vault at the end.

## Settings

- `obsidian_vault`: the vault folder. When it is empty, ask the learner for it once, after delivery, and suggest `tutor-any-lecture profile set obsidian_vault <folder>`; until then deliver as for markdown.
- `naming`: how files are named in the vault. Only `default` exists in M1: the note keeps its name, `explanation.md`, inside its unit folder.

## Note conventions

- **Table of contents.** `[[#Heading]]`, with the H2 text exactly as written, so Obsidian can jump to it. Keep `[ ] | #` out of H2 text.
- **Highlights.** `==text==`, at most 8 in the note, and only where the lecturer says something will or will not be examined, or an exercise uses the formula directly.
- **Callouts** are the same four GitHub alerts (`> [!NOTE]`, `> [!IMPORTANT]`, `> [!WARNING]`, `> [!CAUTION]`), which Obsidian renders as callouts; answers stay in `<details>`.

## Where verify runs and where the note goes

The unit folder in the workspace, `<workspace>/courses/<course>/<unit>/`, stays the place where every command and `tutor-any-lecture verify --unit DIR` run. After verify reports PASS, copy the note into the vault under `<obsidian_vault>/<course>/<unit>/`. Copy only after PASS, and copy again after every later fix and re-verify.

Edits belong in the workspace copy. If the vault copy has changed since the last copy (the learner may have annotated it), ask before overwriting it.
