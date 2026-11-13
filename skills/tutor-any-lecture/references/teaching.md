# Teaching data: plan, items, pretest, quizzes, cards, map

You write four JSON files by hand: plan.json, items.json, cards.json and map.json. The command checks them, assigns variants, picks the items to ask, logs answers and renders the rest. Every file below lives in the unit folder `<workspace>/courses/<course>/<unit>/`.

A command that reads plan.json, items.json, assignment.json, cards.json or map.json and finds it malformed exits 1 with one line on stderr that starts with the file's name. Fix the named file, then rerun the command.

## plan.json

One JSON object with exactly the twelve keys `course`, `unit`, `goal`, `content_type`, `note_language`, `lecture_language`, `duration_s`, `outputs`, `sections`, `concepts`, `tracked`, `output_target`. A missing key, or a value outside the rules below, is a `PlanError` (exit 1).

- `course`, `unit`: the two folder names of the unit. They must work as folder names everywhere: no `/ \ : * ? " < > |`, no control character, no leading or trailing space, no trailing dot. Write `CS 101 - Intro`, not `CS 101: Intro`.
- `goal`: deep, exam or quick. `output_target`: markdown or obsidian (a notion profile is written as markdown).
- `content_type`: formula, code, concept or mixed; it steers the item kinds below.
- `note_language`, `lecture_language`: lowercase primary subtags such as "en", "zh", "ja"; never "auto".
- `duration_s`: the lecture length in seconds, a number, or null when unknown.
- `outputs`: a list of strings from explanation, pretest, quiz, cards, map.
- `concepts`: a list of `{"id", "name", "type", "citations"}`. `type` is one of `definition`, `theorem`, `method`, `example`, `pitfall` (the map node types); `citations` are plain strings such as `"(slide 1)"` or `"(13:42)"`. Concept ids are unique strings; use the map's id style (letters, digits and underscores, starting with a letter) so a concept can also be a map node.
- `tracked`: a list of exactly `min(5, len(concepts))` distinct concept ids, all present in `concepts`.
- `sections`: a list of objects, one per planned H2 section of the note. Their keys are free (the command does not check them); use `{"title": "…", "concepts": [ids], "citations": ["(slide 1)", …]}`.

```json
{
  "course": "Intro Statistics",
  "unit": "Week 04 - Estimators",
  "goal": "deep",
  "content_type": "formula",
  "note_language": "en",
  "lecture_language": "en",
  "duration_s": 2950.0,
  "outputs": ["explanation", "pretest", "quiz", "cards", "map"],
  "sections": [
    {"title": "Why estimators can be biased", "concepts": ["bias"], "citations": ["(slides 2–4)", "(1:10–6:40)"]}
  ],
  "concepts": [
    {"id": "bias", "name": "Bias of an estimator", "type": "definition", "citations": ["(slide 3)", "(4:12)"]}
  ],
  "tracked": ["bias"],
  "output_target": "markdown"
}
```

## items.json

One JSON object with exactly two keys:
- `"tracked"`: an object keyed by concept id, whose value is an object keyed by variant letter (`"A"`, `"B"`, `"C"`, optionally `"D"`, `"E"`);
- `"practice"`: a list.

Every item, tracked or practice, is an object with exactly the nine keys `id`, `concept`, `kind`, `prompt`, `answer`, `rubric`, `citation`, `difficulty`, `variant`. `id`, `concept`, `prompt`, `answer`, `rubric` and `citation` are strings; `difficulty` is a small integer (1 easy to 3 hard). A tracked item's `variant` equals its letter key and its `concept` equals its concept key; a practice item has `"variant": null`. Ids are unique across the whole file. `kind` is one of `recall`, `apply`, `transfer`, `predict_output`, `complete_code`, `which_method`, `contrast`. `rubric` says what a full answer must contain and what earns half; `citation` is a plain citation string.

`tracked` holds the plan's tracked concepts only, each with A, B and C, so the bank is at least 3 × the tracked count plus the practice items. A short synthetic example (variants B and C of `bias` have the same shape as A, with their own ids and prompts, `"variant": "B"` and `"variant": "C"`):

```json
{
  "tracked": {
    "bias": {
      "A": {"id": "bias-A", "concept": "bias", "kind": "apply",
            "prompt": "An estimator averages to 2θ over many samples. What is its bias?",
            "answer": "θ: bias is the expected estimate minus the true value (slide 3).",
            "rubric": "1: says θ and uses expectation minus truth; 0.5: right idea, wrong sign.",
            "citation": "(slide 3, 4:12)", "difficulty": 1, "variant": "A"}
    }
  },
  "practice": [
    {"id": "p1", "concept": "bias", "kind": "contrast",
     "prompt": "How can an estimator be unbiased and still be a poor choice?",
     "answer": "Unbiased only fixes the average; a large variance still spreads estimates widely (5:30).",
     "rubric": "1: names variance or spread; 0.5: says 'can still be wrong' with no reason.",
     "citation": "(5:30)", "difficulty": 2, "variant": null}
  ]
}
```

`tutor-any-lecture items validate --unit DIR` runs the item checks on their own: `variants`, `apply_share`, `citation`, `prompt_overlap`, `tracked_leak`, `tracked_vs_practice`, `pretest_complete`. The gate runs the same checks.

## Tracked concepts and variants

5 tracked concepts per unit (all when fewer). Each has parallel variants A, B and C: the same concept and difficulty, a different surface (other numbers, another case, another direction). `tutor-any-lecture items assign --unit DIR` assigns them at random to pre, post and d7 and records the result in assignment.json; it reuses an existing assignment.json unless `--force` is given. D and E, for d1 and d21, are optional. Parallel variants of one concept must differ enough that no variant's prompt reaches 0.6 containment in another variant's prompt.

## Practice items

In-note checks (`tal:check`) and extra practice use practice items only. A practice prompt must not overlap a tracked prompt: containment ≥ 0.6 either way fails `tracked_vs_practice`.

## Order of work

1. Write items.json.
2. Run `tutor-any-lecture items assign --unit DIR`.
3. Write the pretest section of explanation.md from `tutor-any-lecture items next --unit DIR --phase pre` (its `items`, in the printed order).
4. Write the rest of the note, then cards.json and map.json for the listed outputs.

## Item kinds by content_type

At least 50% of all items, tracked and practice together, are apply/transfer kinds (every kind except recall). Prompts are paraphrased, never copied from the note: containment of a prompt in any sentence of the lecture prose stays below 0.6 (character 3-grams for CJK, word 2-grams otherwise).

| content_type | lean on |
|---|---|
| formula | derivation and "why" items, apply |
| code | `predict_output`, `complete_code` |
| concept | `contrast`, `which_method`, cases |
| mixed | a combination of the above |

Goal quick: a quiz session asks 5–8 items. items.json still carries A, B and C for every tracked concept and at least 50% apply/transfer items; the `variants` and `apply_share` checks do not relax for quick.

**Examples.** Worked example, then a faded example (the last steps left for the learner), then setup only.

**Why prompts.** One "why does this step hold" prompt per derivation, answer folded, the answer quoting the lecturer with a citation.

## Pretest

The pretest is asked in chat before the learner reads the note, whether or not they attended. Before the first question, and again when reporting the score, tell the learner that a low pretest score is normal: guessing first makes the lecture stick better. The score changes the reading focus, which folded supplements to suggest, and the next unit's `level`; it never triggers a rewrite of the note. Ask the items as the quiz protocol below says, with phase `pre`, and record how the learner met the lecture with `--exposure` when they tell you (none, attended, watched; unknown otherwise).

## Quiz protocol

- `tutor-any-lecture items next --unit DIR --phase P` takes P in pre|post|d1|d7|d21 and prints `{"phase", "items", "missing"}`. Practice items come from the `practice` list of items.json or from `tutor-any-lecture items get --unit DIR --id ID`, and are logged with `--phase practice`.
- One item at a time. The learner answers in their own words.
- Grade 0, ½ or 1 against the rubric. Then ask for confidence 1–3 (1 guessing, 3 sure).
- Show the cited answer after the attempt, never before.
- Log it: `tutor-any-lecture progress log --unit DIR --item ID --phase P --score S --confidence K [--exposure E]` (no `--course`: course and unit come from plan.json; score `0`, `0.5` or `1`). It appends to `<workspace>/progress/<course>.jsonl`.
- After a post or review quiz, `tutor-any-lecture cards add-misses --unit DIR` turns missed items into miss cards.

## Reviews

d1, d7 and d21 fall 1, 7 and 21 days after the first post-test; d1 and d21 are optional. `tutor-any-lecture progress due --course C` lists what is due as `{"unit", "phase", "due", "optional"}` entries. For d1 and d21, read `missing` in the `items next` output and write the D (d1) or E (d21) variants for those concepts into items.json before quizzing. `tutor-any-lecture progress render --course C` writes the progress page `<workspace>/progress/<course>.md`.

**Interleaving.** From week 3, quizzes mix in earlier units' items and "which method applies" items.

## Cards

Core cards at most 25 per unit (10 for goal quick). Miss cards come from `tutor-any-lecture cards add-misses --unit DIR`, at most 10 per unit, not counted against the core cap. Rules:
- one point per card, answered by recall;
- a clear cue on the front that does not leak the answer;
- difficulty around 90% success with some effort;
- only what will be examined;
- the back cites its source;
- backs over 350 characters draw a WARN;
- fronts whose character 3-gram Jaccard is ≥ 0.8 are duplicates (FAIL).

Card-writing rules adapted from anki-card-forge (https://github.com/FrostySL/anki-card-forge), MIT License, Copyright (c) 2026 Lukas Sinning.

GUIDs are stable (derived from course, unit and card id), so re-importing cards.tsv updates cards without losing review history: never renumber card ids. cards.json is a top-level list of `{"id", "concept", "front", "back", "citation", "kind"?}`; `kind` is "core" (the default) or "miss", and every value is a string. `tutor-any-lecture cards export --unit DIR` writes cards.tsv for Anki's import.

```json
[
  {"id": "c01", "concept": "bias", "front": "Bias of an estimator: definition?",
   "back": "Expected value of the estimator minus the true parameter.", "citation": "(slide 3)"}
]
```

## Overview map

map.json is `{"nodes": [{"id", "label", "type", "order"?, "citation"?}], "edges": [{"from", "to", "verb"}], "views": [{"id", "nodes"}]?}`.
- Node types: definition, theorem, method, example, pitfall.
- A node id uses letters, digits and underscores, starts with a letter, and is not `end`.
- Every edge names existing nodes and has a verb ("defines", "is used in", "fails when").
- At most 12 nodes per view. A map of more than 12 nodes needs views, and then every node belongs to at least one view.

`tutor-any-lecture map validate --unit DIR` checks it; `tutor-any-lecture map mermaid --unit DIR` writes overview.mmd (`--view ID` for one view).
