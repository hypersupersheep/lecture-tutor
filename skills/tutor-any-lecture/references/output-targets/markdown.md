# Output target: Markdown

The default target (`output_target: markdown`). Plain Markdown with GitHub alerts, readable on GitHub, in most editors, and importable into Notion.

## Unit folder

Every unit lives at `<workspace>/courses/<course>/<unit>/` with fixed file names (the workspace is the profile's `workspace`, `~/TutorAnyLecture` by default):

| file | written by | what it is |
|---|---|---|
| `sources/transcript.json` | `acquire …`, `transcribe` | the timed transcript; never edited |
| `sources/source.json` | `acquire …`, `transcribe`, `slides --pdf` | where the material came from: kind, URL, duration, language, health |
| `sources/chapters.json` | `acquire panopto` | the platform's chapter titles and times |
| `sources/slides/pages.json` | `slides --pdf` | slide text by page, with footer numbers |
| `sources/suspects.json` | `slides suspects` | likely mis-heard words with the nearest slide term |
| `plan.json` | you | what the unit teaches (see [teaching](../teaching.md)) |
| `explanation.md` | you | the note (see [writing](../writing.md)) |
| `items.json` | you | the item bank |
| `assignment.json` | `items assign` | which variant is asked in which phase |
| `cards.json` | you; `cards add-misses` appends | the Anki cards |
| `cards.tsv` | `cards export`, `cards add-misses` | the Anki import file |
| `map.json` | you | the concept map |
| `overview-<view>.mmd` | `map mermaid` | one Mermaid flowchart per view of the map, when map.json has views |
| `overview.mmd` | `map mermaid` | the whole map as a Mermaid flowchart, when map.json has no views (or the one view asked for with `--view`) |
| `verify.json` | `verify` | the gate's result |

Progress is per course, outside the unit folders:
- `<workspace>/progress/<course>.jsonl`: one line per logged attempt (`progress log`);
- `<workspace>/progress/<course>.md`: the progress page (`progress render`).

## Markdown conventions

- **Table of contents.** `[text](#slug)`, where the slug is the H2 text in lowercase, with punctuation dropped (letters, digits, underscores and hyphens stay) and each space turned into `-`: `## Bias and variance: a trade-off` becomes `#bias-and-variance-a-trade-off`. A repeated heading gets `-1`, `-2`, … in document order, counting every heading level.
- **No `==highlights==`**: Markdown does not render them, and the gate warns on any.
- **Callouts** are GitHub alerts, `> [!NOTE]`, `> [!IMPORTANT]`, `> [!WARNING]`, `> [!CAUTION]`; answers are `<details><summary>Answer</summary>…</details>`.
- **Equations** are `$…$` and `$$…$$`, which GitHub and most editors render.

## Delivering

After verify passes and the pretest is done (see SKILL.md), tell the learner where the unit folder is and what to open: `explanation.md` to read, `cards.tsv` to import into Anki (File, Import), and the map in any Mermaid viewer: each `overview-<view>.mmd` when the map has views, otherwise `overview.mmd`.

**Notion** (`output_target: notion`): plan.json says markdown, and the files are the same. The learner imports `explanation.md` with Notion's Markdown import; alerts arrive as quotes and `<details>` blocks may need re-folding by hand.
