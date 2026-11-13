# Writing contract for explanation.md

This file says what the explanation note looks like. Read it before writing and check the note against it afterwards. The note follows the lecture as it was given and keeps the lecturer's points and best explanations faithfully. It is not a preview note (a systematic text that lets someone skip the lecture); the two are different genres with different uses.

Why it looks like this: headings help recall only where the topic really changes (Hyönä and Lorch 2004), so forced sections hurt; self-explanation prompts work when they ask why, not what (Bisra et al. 2018); practice questions should match the format of the assessment (Dunlosky et al. 2013); and formatting is best steered by positive examples rather than bans. The rules were tuned on real lectures and revised once after a with-rules versus without-rules comparison.

`tutor-any-lecture verify --unit DIR` enforces the numeric parts of this contract (see [gate](gate.md)). The numbers below are the ones in `notecheck.THRESHOLDS`, which is what verify enforces.

**Units of measure.** Length is counted in the note language: CJK characters for a Chinese, Japanese or Korean note (English quotes, LaTeX and punctuation not counted), words otherwise. `slide N` is the number printed in the slide's footer (the 15 of "15/32"), not the PDF page index: incremental builds make a PDF much longer than its footer count. If a page has no footer number, cite its PDF page number.

## Language and terms

The note is written in `plan.note_language`. The `terms` setting decides how technical terms appear:
- `bilingual`: when the lecture language and the note language differ, write a term as `English term (translation)` at its first use, then the lecturer's term alone;
- `note`: the note language only;
- `original`: the lecturer's term only.

Write directly: conclusion first, no greetings, no wrap-up. When you report the lecturer's position, write "the lecturer says", not "we think". Write headings in sentence case: a run of capitalised words, or a word with a capital inside it (an acronym, a CamelCase name), that does not appear in the transcript or slides draws a `terms` warning. NOTE callouts are exempt.

## Skeleton

```markdown
# <Unit title>

- [Pretest](#pretest)
- [<Topic 1>](#<slug>)
- [Not covered and errata](#not-covered-and-errata)

How to read this note: <two or three sentences, in the note language>

## Pretest

<!-- tal:pretest -->
1. <pre-variant prompt, verbatim from items.json>
   <details><summary>Answer</summary>
   <cited answer>
   </details>
<!-- /tal:pretest -->

## <Topic 1>

*(slides 2–4, 0:40–3:10)*

<paragraphs>

<!-- tal:check -->
1. <practice prompt, verbatim from items.json>
   <details><summary>Answer</summary>
   <cited answer>
   </details>
<!-- /tal:check -->

## <Topic 2>
...

## Not covered and errata

<!-- tal:not-covered -->
- slide 9: <one sentence on why it was not covered>
<!-- /tal:not-covered -->

<!-- tal:errata -->
> [!CAUTION]
> Transcript and slide errata
>
> | Time | Heard | Should be |
> |---|---|---|
> | 12:31 | eigenvaloo | eigenvalue |
<!-- /tal:errata -->
```

- Start the note with one H1 (a style rule; verify does not check it). Then the table of contents, then the "how to read this note" lines, then the sections.
- **How to read this note** (kept from v1, shortened): the body holds only what the lecturer said and the slides show, in lecture order; quoted text is verbatim (slides word for word, speech with filler words removed); `(slide N)` is the footer number and `(mm:ss)` the recording time; note boxes are tutor additions, caution boxes are errata and doubts; equations are numbered so they can be referred to. Add or drop half a sentence to fit the unit (for example, no exercises).
- **Table of contents.** One list item per H2 that you want listed. Each link must match an H2: `[text](#slug)` for markdown (see [markdown](output-targets/markdown.md)), `[[#Heading]]` with the heading text exactly for obsidian (see [obsidian](output-targets/obsidian.md)). Keep `[ ] | #` out of H2 text.
- **Optional sections.** "What the lecturer said about the course" collects arrangements, assessment, readings and exam scope that the lecturer scattered across the session, with every time range on its anchor line. "Exercises" and a formula quick-reference table appear only when the source has exercises or formulas (see below).

## Headings and anchor lines

One H2 per topic change by the lecturer, in lecture order; a 90-minute lecture usually has 10 to 16. Take topic changes from the lecturer's transition sentences ("so, bond valuation") and the slide sections; sources/chapters.json, when present, is a hint only (its chapters are often too fine and their titles often wrong). The single exception to lecture order is the optional course-arrangements section.

H3 appears only for three things, and its title starts with "Derivation:", "Worked example:" or "Class discussion:"; usually 3 to 6 per lecture. An H3 holds only the derivation or example itself; the lecturer's asides during it go back into the H2 prose (they may follow the H3). There is no H4, and headings carry no numbers. A section shorter than 150 CJK characters or 90 words is thin: merge it into the previous one.

The first line of every topic H2 is an italic anchor line written as a citation, for example `*(slides 14–16, 40:38–48:34)*` or, with several time ranges, `*(5:45–12:08, 36:47–40:29)*`. Fixed sections (pretest, not covered and errata, exercises, formula table) have no anchor line.

## What a section is made of

Each H2 holds one to six paragraphs; a paragraph completes one step of reasoning (roughly 60 to 250 CJK characters or 40 to 150 words; over 300 CJK characters or 180 words is too long). A display equation `$$…$$` belongs to its paragraph. Inside a paragraph the content keeps this order, using only the parts that exist: why the lecturer introduces the idea, then the definition (verbatim, cited), then intuition or a concrete example (examples before symbols), then the formula or derivation (key formulas numbered `$$…\tag{n}$$`, each derivation step naming the rule it uses), then a worked example, then the most common mistake.

The body of a paragraph is your explanation; quotes are the evidence set into it. At most 3 quotes per paragraph; quote definitions, results and the lecturer's own explanations, never transitions, repetitions or a second phrasing of the same point (paraphrase those and cite the time). Lists are only for parallel items: the formula table, the errata table, the exercise list and the item lists in marker sections. Reasoning, explanation and cause go into sentences. At most 15 bold spans in the note, at most one bolded conclusion per section.

`==highlights==` are for the obsidian target only, at most 8, and only for two triggers: the lecturer says something will or will not be examined, or an exercise uses the formula or convention directly. The markdown target has no highlights.

A paragraph written the right way (an illustrative finance example; the quotes are invented for the illustration, not real lecture words):

```markdown
Discrete compounding starts from £1 (slide 15). At rate $r$ paid once a year, the account holds $(1+r)$ after one year; at $r=10\%$ that is £1.10. After two years it holds the first year's $(1+r)$ plus interest on it: $(1+r)+(1+r)\times r=(1+r)^2$, or £1.21. The lecturer stresses why: in the second year not only the principal earns, because "the interest you earned last year earns interest too", so the result is a square and not $1+2r$ (44:38–44:53). For $n$ years it is $(1+r)^n$, and "give it fifty years and the number gets very large" (45:15–45:19).
```

The same content as fragments (what appeared without rules): a bold label, then three bullets "after 1 year: $1+r$", "after 2 years: $(1+r)^2$", "after $n$ years: $(1+r)^n$". The same content as a pile of quotes (what appeared with rules but no cap): every clause is a quote, and the explanation disappears. The first version links the lecturer's reason, words and formula into one argument; the second cuts them into items that explain nothing; the third only quotes.

## Faithful to the lecturer

Every definition, theorem and result in the body maps to a slide or a time. Definitions and theorems are quoted verbatim from the slides with `(slide N)`; the lecturer's key spoken explanations are quoted from the transcript with filler words ("uh", "all right", "you know") removed and nothing else changed, with `(mm:ss)` or a time range. Cite only the real source: slide content cites the slide, spoken content the time, both when both apply. A student's remark may be quoted as "a student answers: …" with its time and the lecturer's response. Mark removed self-repetition with "…".

Keep the lecturer's notation. A notation clash in the slides (one letter, two meanings) goes into a CAUTION callout; the body keeps the notation. When the slides give only a numeric example, a general form may go in the body, followed by a sentence saying the slides give only the example and the general form is a rewrite. Steps the lecturer skipped may be filled in a NOTE callout, using the method the lecturer named.

The transcript is machine-made: names and numbers are often wrong ("forty years" for "four years", "80%" for "8%"). Numbers, names, institutions and formulas follow the slides. Inside a quote, correct a clear mis-hearing only when the slides confirm the right word, and log it. Small talk before the lecture and during the break stays out; say in the not-covered section, in one sentence, which time range was the break. A substantive exchange during the break may go into the body or a NOTE callout, marked as during the break.

Order of writing: first pull the quotes you will use, with their sources, into a scratch file `quotes.md` in the unit folder (a working file, never a deliverable); then write the body around them; then check every sentence attributed to the lecturer against `quotes.md` and delete it or move it into a NOTE callout when it is not there. Last, walk through the slides page by page: each page's definitions, formulas and examples land in some section, or the page is listed as not covered.

## Callouts

GitHub alert syntax `> [!TYPE]`, with exactly four types:
- `> [!NOTE]`: a tutor addition, not from the lecture;
- `> [!IMPORTANT]`: a key result;
- `> [!WARNING]`: a common mistake;
- `> [!CAUTION]`: transcript or slide errata and doubts.

Any other type fails the gate. Answers always go in `<details><summary>Answer</summary>…</details>`, never in a callout.

A NOTE callout holds only three kinds of content: derivation steps the lecturer skipped; numbers computed from an expression the slides only state; one or two sentences linking the unit to earlier or later material. Each box is at most 150 CJK characters or 90 words (LaTeX not counted), at most two per section. It may end with one "why" or "how" question for the reader, never a "what" question and never an item prompt. When referring to later material, write "later, when X is covered"; do not invent week or session numbers. Proper names you add yourself belong in a NOTE callout (the `terms` check skips NOTE callouts).

## Marker sections

explanation.md carries machine-readable sections between paired markers: `<!-- tal:NAME -->` opens and `<!-- /tal:NAME -->` closes. NAME is one of `pretest`, `check`, `not-covered`, `errata`. `check` may occur many times (one per section quiz); the others at most once. Authoring rule: each marker on its own line; headings stay outside the markers; never nested; never inside a code fence. An unclosed, nested, unknown or duplicated marker, or a close marker with no matching open, fails the gate (`markers`).

What the sections print:
- `pretest`: exactly the prompts of the variants assigned to phase `pre`, one per tracked concept, in the order `tutor-any-lecture items next --unit DIR --phase pre` prints them (sorted concept id), each as a numbered item followed by a `<details>` answer.
- `check`: practice items only, verbatim from items.json, each numbered and followed by a `<details>` answer. Never a tracked item.
- `not-covered`: every slide the lecture did not cover, written as `slide N` (or `slides N–M` for a run), with a sentence on why; the break, if any, in one sentence.
- `errata`: transcript and slide errata, built from `sources/suspects.json` (heard word, nearest slide term, time in seconds; write it as mm:ss); flag, never silently fix. The lecturer's own slips go here too (say whether they corrected themselves), and slide typos with the slide number in the time column.

Every numbered item in `pretest` and `check` needs its `<details>` answer before the next numbered item. The answer cites its source. Start the answer on the line after `<summary>Answer</summary>`, as in the skeleton: on the same line, the `terms` check reads "Answer" and a capitalised first word of the answer as one term.

**No restating.** The lecture prose (the note with every marker section removed) never restates an item prompt: no sentence of it may reach 0.6 containment of any prompt. For each tracked concept, the section that covers it gives the cited answer to that concept's pretest question in its own prose.

## Citations

Every claim attributed to the lecturer carries `(slide N)`, `(mm:ss)` or `(slide N, mm:ss)`; ranges `(slides 14–16)`, `(13:42–14:05)`; an estimated time is written `(~13:40)`. Past one hour write `(1:02:03)`. Full-width parentheses `（…）` are accepted. Cite the slide's footer number; if a page has none, its PDF page number. A slides-only unit cites slides only.

The gate reads a parenthesis as a citation only when it holds nothing but citation parts separated by commas: `slide N`, `slides N–M` (plural, with a range), a time, a time range, `~` directly before a time. `(slide 14-16)`, `(slides 4)` and `(see slide 4)` are not citations. A slide number above the last slide, or a time more than 2 seconds past the duration, fails the gate.

When source.json `kind` is "url" and `url` is set, each timestamp in explanation.md is a link to the video at that time, inside the parentheses: `([13:42](<url>&t=822s))`, with `?t=` when the URL has no query, whole seconds, where `<url>` is source.json's `url` as it is. A range links its start only: `([13:42](<url>&t=822s)–14:05)`. A slide and a time: `(slide 15, [13:42](<url>&t=822s))`. The `~` stays before the bracket: `(~[13:40](<url>&t=820s))`. Every other source kind, or a platform with no time parameter, uses the plain `(mm:ss)`. Citation strings in items.json, cards.json and map.json stay plain.

## Length by goal and duration

Per minute of lecture, CJK characters / English words of lecture prose (marker sections excluded); deep | exam | quick:

| per minute | deep | exam | quick |
|---|---|---|---|
| total length | 44–89 / 26–53 | 30–70 / 18–42 | 10–25 / 6–15 |
| time citations | ≥ 0.67 | ≥ 0.5 | ≥ 0.2 |
| verbatim quotes | ≥ 0.22 | ≥ 0.15 | ≥ 0.07 |

Over the top of the range, first check for content the lecturer did not give; under the bottom, check the slide-by-slide walk for gaps. When the duration is unknown these per-minute checks are skipped with a warning.

**Goal and coverage.** No extra sections inserted into lecture prose; goal changes length and coverage. Every goal keeps citations and faithfulness. There is no "speed-read" block, no "to-do for next week", no "interview questions", no summary at the end.

## Structure rules the gate enforces

- No H4 or deeper; no numbered headings (FAIL).
- At most `max(16, ceil(16 × minutes / 90))` H2s (WARN).
- An H2 section of fewer than 150 CJK characters / 90 words is thin (WARN); a section whose prose is all inside marker sections is not counted.
- A paragraph over 300 CJK characters / 180 words is too long (WARN).
- At most 3 inline quotes per paragraph, and a paragraph with a quote carries a citation (FAIL). Quotes are text in `"…"`, `“…”` or `「…」` on one line, counted from 15 characters.
- Every non-callout blockquote is cited in it or on the next non-blank line (FAIL).
- At most 15 bold spans (WARN); `==highlights==` at most 8 for obsidian and none for markdown (WARN).
- Bullet lines at most 10% of the prose lines (WARN); table rows and table-of-contents lines are not bullet lines.
- Quoted characters 10–40% of the prose in the same language, or 1.0–2.0 × the note's length when a CJK note quotes a non-CJK lecture (WARN).
- TOC links must match H2s: `[[#Heading]]` for obsidian, `[text](#slug)` for markdown (FAIL).
- Callout types and `<details>` answers as above; marker problems (FAIL).

Besides structure, verify checks citations, slide coverage (every slide is cited or listed in `tal:not-covered`), terms, numbers with units, the items, cards and map, and a list of stock phrases ("delve", "it's worth noting", "in conclusion", "in summary" and similar); see [gate](gate.md).

## Exercises, formula table and v1 structures

- **v1 structures mapped to the v2 note model.**
  - v1's fixed "self-test" section (6–10 questions, answers in `> [!note]-` boxes) is replaced by `tal:check` sections: one per H2 section, at its end, built only from practice items, each answer inside `<details><summary>Answer</summary>…</details>`. The pretest is the `tal:pretest` section; neither marker section holds hand-written questions that are not in items.json.
  - v1's `> [!warning]` errata callout and correction table become a `> [!CAUTION]` callout inside the `tal:errata` section (rows: time, heard, should be).
  - v1's YAML front matter is dropped: the gate and the CLI read plan.json and source.json, not the note's front matter. In particular there is no `lecturer:` field and no teacher name anywhere. The "how to read this note" paragraph is kept, shortened, as the first lines after the H1 and the TOC, in the note language.
  - v1's "Exercises" section and formula quick-reference table are optional sections: allowed only when the source has exercises or formulas. They are ordinary H2 sections of lecture prose (cited, within the length and bullet limits), and any exercise answer is folded in `<details>`. The formula table may use table rows, which are not bullet lines.
  - v1's working file `quotes.md` stays a scratch file in the unit folder's working area, never a deliverable and never listed in the output table.
- **Exercises.** For each exercise say which formula applies and what to watch for; put the numeric answer, computed with code rather than by hand, in `<details><summary>Answer</summary>…</details>`. When the wording is ambiguous, pick the reading of the slides' closest example, say which and why, and give the other reading's answer in the same `<details>`.
- **Formula table.** Columns: number, formula, where it is used. One line after the table may state the exam conventions the lecturer gave. The note ends there.

## Example

For a complete note that passes the gate, run `tutor-any-lecture selftest --keep DIR`: it leaves a generated unit in DIR.
