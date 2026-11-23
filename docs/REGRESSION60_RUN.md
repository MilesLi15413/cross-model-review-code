# Regression-60 Run: Does Review Break Code That Already Works?

**Started:** 2026-11-21. **Branch:** `regression-60` (from `limited-demo-run`).
**Status:** complete (2026-11-21). All 540 reviews are valid and graded. Follow-ups
(items 1–7a, incl. BigCodeBench) complete 2026-11-22 on branch `bigcodebench-check`.
Authorship-label pilot (450 reviews) complete 2026-11-22.

## Summary of findings

1. **Review breaks working code, and GPT-5.5 does it most.** Passing drafts broken:
   LiveCodeBench GPT-5.5 9/162, Claude 1/162\*, Gemini 0/162; BigCodeBench GPT-5.5
   12/139, Gemini 4/139, Claude 2/139.
2. **The tendency is stable, the drafts are not.** A fresh GPT-5.5 repeat broke 7/162,
   only 3 of them the same drafts.
3. **The mechanism is rewriting.** Breaks come from larger edits (p ≤ 0.025 for GPT-5.5
   in every run), and the one-line "change as little as possible" prompt cuts GPT-5.5's
   breaks from 9 to 2 with no loss of fixes. Most breaks are wrong answers; GPT-5.5's
   crashes are input-parsing rewrites.
4. **Claude is the most useful reviewer** on BigCodeBench: it fixes 18/99 failing drafts
   (GPT-5.5 5, Gemini 6; significant against both) and breaks the fewest.
5. **The paper's GPT-5.5 solo score counts formatting as failure.** The paper's
   statistics are not wrong: its 83/116 and the gains from review (+18.1 / +12.9 pp,
   significant) reproduce exactly with the paper's own code. But 15 of the solo
   failures are correct code wrapped in a Markdown fence, so most of that gain is the
   reviewer fixing formatting. Counting code correctness only, GPT-5.5 solo is 98/116
   and the gains are +5.2 pp (not significant) and 0. This needs reinterpreting, not
   correcting (details: "Result of item 1").
6. **The paper's GPT-5.5 costs are ~45% too high** (cached tokens counted twice); with
   corrected costs GPT-5.5 solo is the most cost-effective condition.
7. **Authorship labels make no measurable difference** (pilot, 450 reviews). Telling a
   reviewer the true author, a false author, "you wrote this", or nothing changes its
   behavior no more than two identical runs differ; no self-preference (fixes when told
   "you wrote this" vs "a third model wrote this": Claude 1 vs 1, GPT-5.5 1 vs 1, Gemini
   3 vs 3). Rules out large label effects, not small ones (see "Authorship-label study").

\* **Note on Claude's one LiveCodeBench break (3784, Claude reviewing Gemini's draft).**
The review imports `sortedcontainers`, which the paper's grading environment does not
include, so it crashes there. The official count stays **1/162**, graded like every
other program. As a separate check (2026-11-22), the same program was graded with
`sortedcontainers` available from a throwaway folder, without changing the grading
environment or any record: it **passes every test (twice)**. On a judge that provides
the library (LeetCode and AtCoder both do), Claude breaks **0/162**. This matters for one
claim only: GPT-5.5 vs Claude on LiveCodeBench is 9 vs 1 (Holm p = 0.11, not significant)
as graded, and would be 9 vs 0 (Holm p ≈ 0.02, significant) with the library. Report
the official result and give this as a footnote; BigCodeBench independently shows the
same direction (12 vs 2).

This run answers three questions for all 9 writer × reviewer pairings of Claude,
GPT-5.5 and Gemini:

1. **Regression rate:** when a reviewer is handed a draft that already passes, how
   often does the code fail after review? (The main question.)
2. **Fix rate:** when a reviewer is handed a draft that fails, how often does it pass
   after review? (Added during the run at the user's request.)
3. **Cost:** what does each review, and each pairing, cost?

This is the plain cross-model review setting. There are **no authorship labels**: the
reviewer is never told who wrote the code.

Nothing in the paper's frozen results (`results/raw/lcb_hard_full`,
`results/raw/lcb_medium_100`) was changed. All new output uses the `regression60_`
prefix.

## Status and next steps

- **Everything above is complete** and committed on `bigcodebench-check` (local, not
  pushed). Nothing is running.
- **Raise with the coauthors before the paper is used or submitted:** (1) the GPT-5.5
  solo score counts formatting as failure, which makes up 71–87% of the claimed gain from
  review; (2) the GPT-5.5 cost tables are inflated ~45%, which reverses the
  cost-effectiveness claim.
- **Optional, needs credits:** Gemini 4 Neon rerun to match training dates (~$40–60);
  full authorship-label study (~$280+); style-recognition test; neutral label.
- **Not possible without changing the setup:** the 2 missing Gemini BigCodeBench drafts
  (consistent failures).

## The original paper: what it ran

**Question:** does having a second AI model review code improve it?

- **Models:** Claude Opus 4.7 (`claude-opus-4-7`, Claude Code CLI) and GPT-5.5
  (`gpt-5.5`, Codex CLI), both at high reasoning effort. One version each.
- **Six conditions (whole pipelines):** A = Claude alone; O = GPT-5.5 alone; AO = Claude
  writes, GPT-5.5 reviews; OA = GPT-5.5 writes, Claude reviews; AA = Claude reviews
  itself; OO = GPT-5.5 reviews itself. The reviewer outputs the final program.
- **Benchmark:** LiveCodeBench, hard slice (82 tasks) and medium slice (55). Headline =
  116 tasks gradable in all six conditions (61 hard + 55 medium), the "complete case";
  a second "reliability-inclusive" view counts unusable outputs as failures.
- **Review step:** one static pass, no tests, no tools, must output a full program.
  Reviewer prompt: "Identify any bugs, incorrect logic, missing edge cases, or
  inefficiencies. Produce a final corrected solution — either the original if it is
  correct, or an improved version. Do NOT run or test the code." Output in
  `<solution>` tags.
- **Design limit the paper stated itself:** each condition drew its own writer draft, so
  OA vs O compares two independent pipelines, not what a reviewer did to a given draft;
  "freeze each draft, score it, then review it" was listed as planned follow-up.
- **Grading:** LiveCodeBench's evaluator, one batch per condition at the end of the run
  (commit 6581226). **Costs:** recomputed from stored token counts at list prices.
- **Note:** the paper's GPT-5.5 writer ran through Codex with its built-in shell, and
  the records show it used it, although the setup is described as no-tool.

**Paper's results (116 tasks):**

| Label | Passed | Pass rate | Cost/task | Score per $ |
|-------|--------|-----------|-----------|-------------|
| A  | 106 | 91.4% | $0.226 | 4.04 |
| O  | 83  | 71.6% | $0.190 | 3.77 |
| AO | 96  | 82.8% | $0.382 | 2.17 |
| OA | 104 | 89.7% | $0.443 | 2.03 |
| AA | 106 | 91.4% | $0.389 | 2.35 |
| OO | 98  | 84.5% | $0.312 | 2.71 |

**Paper's claims:** "If GPT-5.5 writes, review helps" (OA +18.1 pp, OO +12.9 pp over O,
significant after correction). "If Claude writes, handing it to GPT-5.5 did not help"
(AO −8.6 pp). AA = A. AO vs OA not separable (p_BH = .14), so no general ranking of
reviewers. Claude solo is the most cost-effective.

## Compared with the original paper

**Reproduced, but needs reinterpreting**

| The paper said | What we found |
|----------------|---------------|
| GPT-5.5 solo passes 83/116 (71.6%) | **Correct as graded:** the paper's own code reproduces it exactly. But 15 of the failures are correct code inside a Markdown fence; on code correctness it is 98/116 (84.5%). |
| "If GPT-5.5 writes, review helps": OA +18.1 pp, OO +12.9 pp, both significant | **Correct as graded**, and significant. Most of the gain is the reviewer removing the fence, not fixing code; on code correctness the gains are +5.2 pp (not significant) and 0. |

**Corrected (an actual error)**

| The paper said | What we found |
|----------------|---------------|
| GPT-5.5 costs ($0.190/task solo); Claude solo is the most cost-effective (pass rate per dollar 4.04 vs 3.77) | The paper's code stored Codex's `input_tokens` (which already include cached tokens) and the cached count, and priced both, so cached tokens were charged twice (cached > input in 0 of 685 GPT turns; cached ≈ 67% of input). GPT-5.5 costs are ~45% too high. Corrected, **GPT-5.5 solo is the most cost-effective** (6.81 even with the paper's 83/116). Costs are estimates at the repo's list prices (`pricing.yaml`), not invoices; the fix matched OpenAI billing in this run. |

**Reinforced**

| The paper said | What we found |
|----------------|---------------|
| Claude writes + GPT-5.5 reviews (AO) is 8.6 pp worse than Claude alone | Explained directly: GPT-5.5 breaks Claude's working drafts (5/54 LiveCodeBench, 7/57 BigCodeBench), the worst pairing on both. |
| Claude reviewing itself (AA) adds nothing | Confirmed: Claude leaves most of its own drafts unchanged (73% on BigCodeBench) and broke none. |
| Scope warning: nothing protects a good draft from a worse rewrite | Shown to happen: every reviewer broke some working code. |
| Results are writer-conditional; the two cross-model orderings (AO vs OA) cannot be separated, so no general ranking of reviewers | **Partly.** At the pipeline level this still holds. On the same fixed drafts, a partial ranking appears: GPT-5.5 breaks the most working code (both benchmarks), Claude fixes the most failing code (BigCodeBench), and Claude vs Gemini on breaks cannot be separated (LCB 1 vs 0, BCB 2 vs 4, not significant). Which reviewer helps still depends on the writer, e.g. GPT-5.5 is the worst reviewer for Claude's drafts. |

**New (not measurable in the paper's design)**

1. *The reviewer's own effect on a fixed draft.* The paper compared independently sampled
   pipelines and listed "freeze each candidate and score it before review" as planned
   follow-up; this run does that, so a break is a direct measurement.
2. *Break rates:* GPT-5.5 5.6%, Claude 0.6%\*, Gemini 0% (LiveCodeBench); 8.6%, 1.4%,
   2.9% (BigCodeBench).
3. *Mechanism:* breaks come from larger rewrites; mostly wrong answers; GPT-5.5's crashes
   are input-parsing rewrites.
4. *A one-line fix:* "change as little as possible" cuts GPT-5.5's breaks from 9 to 2
   with no loss of fixes.
5. *Stability:* a repeat run gives a similar break rate on mostly different drafts.
6. *Fix rates:* Claude fixes failing drafts significantly more often (18/99 vs 5 and 6
   on BigCodeBench).
7. *Wider scope:* a third model (Gemini) and a second benchmark (BigCodeBench); the main
   pattern holds on both.

**Still open (same as the paper):** findings-only review with human adjudication,
reviewers with tools or tests, multiple writer samples per task, and multi-file or
repository-scale code.

**In one sentence:** the paper's statistics stand as graded, but its main story (review
improves GPT-5.5's code) is mostly a formatting effect; the better-supported story is
that a rewrite-style review pass often breaks working code, the choice of reviewer
matters, and asking for minimal edits largely prevents it.

## Results by model and pairing

All 9 writer → reviewer pairings were run on both benchmarks (every draft reviewed by
every reviewer, paper's reviewer prompt, no authorship label).

**Each model at a glance** (LCB = LiveCodeBench, BCB = BigCodeBench):

| | Claude | GPT-5.5 | Gemini |
|---|---|---|---|
| As writer: drafts passing | LCB 54/60; BCB **57/80** (best) | LCB 52/60; BCB 40/80 | LCB **56/60** (best); BCB 42/78 |
| Working drafts broken | LCB 1/162\*; BCB 2/139 | LCB **9/162**; BCB **12/139** (most) | LCB **0/162**; BCB 4/139 |
| Failing drafts fixed | LCB 6/18; BCB **18/99** (most) | LCB 5/18; BCB 5/99 | LCB 6/18; BCB 6/99 |
| Drafts left unchanged (LCB / BCB) | 22% / 36% | 7% / 6% (fewest) | 29% / 24% |
| Median edit, lines (LCB / BCB) | 7.5 / 6 | 37.5 / 15 (largest) | 14.5 / 6 |
| Cost per review (LCB / BCB) | $0.21 / $0.12 (API-equivalent; ran on Pro) | **$0.05 / $0.03** (cheapest) | $0.18 / $0.08 |
| Median review time (LCB / BCB) | 21 s / 6 s | 14 s / 13 s | 82 s / 24 s (slowest) |

\* 0/162 with `sortedcontainers` available; see the note under "Summary of findings".

**All 9 pairings** (broken = passing drafts that fail after review; fixed = failing
drafts that pass after review):

| Writer → reviewer | LCB broken | LCB fixed | BCB broken | BCB fixed |
|---|---|---|---|---|
| Claude → Claude   | 0/54 | 2/6 | 0/57 | 0/23 |
| Claude → Gemini   | 0/54 | 2/6 | 2/57 | 1/23 |
| Claude → GPT-5.5  | **5/54** | 3/6 | **7/57** | 0/23 |
| Gemini → Claude   | 1/56 | 0/4 | 0/42 | 7/36 |
| Gemini → Gemini   | 0/56 | 0/4 | 1/42 | 1/36 |
| Gemini → GPT-5.5  | 2/56 | 0/4 | 3/42 | 2/36 |
| GPT-5.5 → Claude  | 0/52 | 4/8 | 2/40 | **11/40** |
| GPT-5.5 → Gemini  | 0/52 | 4/8 | 1/40 | 4/40 |
| GPT-5.5 → GPT-5.5 | 2/52 | 2/8 | 2/40 | 3/40 |

Unchanged rate and median edit per pair: LCB `results/processed/regression60_by_pair.csv`,
BCB `results/processed/regression60_bcb_by_pair.csv`.

**What the pairings show:**

- GPT-5.5 is the riskiest reviewer of other models' code, worst on Claude's drafts.
- On its own drafts GPT-5.5 breaks less (2 on each benchmark), though it still rewrites.
- The best fixer depends on the writer: Claude fixes GPT-5.5's failing drafts most
  (11/40 BCB); Claude and Gemini each fix 4/8 on LCB.
- Self-review is mostly a no-op for Claude and Gemini: they leave half or more of their
  own drafts unchanged, with almost no breaks and almost no fixes.
- GPT-5.5 drafts reviewed by Gemini are a safe pairing: 0/52 and 1/40 broken, 4/8 and
  4/40 fixed.

**What the reviewer prompt asks.** Every reviewer got the paper's prompt unchanged:
"Identify any bugs, incorrect logic, missing edge cases, or inefficiencies. Produce a
final corrected solution — either the original if it is correct, or an improved version.
Do NOT run or test the code." It neither forces a rewrite nor asks for minimal edits: a
reviewer may return the draft unchanged, but must output a full program, and "improved
version" / "inefficiencies" leave room to rewrite. How much to change was each model's
own choice. The "smallest change needed" line was used only in item 5, only for GPT-5.5.

**Why GPT-5.5 changes so much.** What the data shows:

- Rewriting is its default, not a limit: with the minimal-edit line it left 74% of
  drafts unchanged (from 7%) and its mean edit fell from 47 to 5 lines.
- It rewrites its own code too: unchanged on only 14% of its own BCB drafts (Claude
  73%), so this is not distrust of other models' code.
- Part of it is cosmetic: on BCB it returned 4% of Claude's drafts exactly unchanged,
  but 16% ignoring whitespace.
- The prompt's "improved version" invites it; Claude and Gemini read it as "fix if
  broken", GPT-5.5 as "produce a better version".

Plausible but untested: GPT-5.5 runs through the Codex CLI, built as an agent that makes
changes, and models differ in training on how much to defer to existing code. Safe
claim: GPT-5.5 rewrites by default, and an explicit minimal-edit instruction largely
switches that off.

**Why Gemini broke 0 on LCB.** It changes less (31% of passing drafts unchanged vs 8% for
GPT-5.5; median edit 14.5 vs 37.5 lines), and 0/162 vs Claude's 1/162 is within noise
(95% interval 0–2.3%). It is not perfect: 4/139 on BCB, more than Claude. When it does
edit, its edits average 37 lines (Claude 19), yet it broke none on LCB, so its edits seem
to keep the original logic more often.

## Setup

| Model  | Exact ID                 | Accessed through                | Effort          |
|--------|--------------------------|---------------------------------|-----------------|
| Claude | `claude-opus-4-7`        | Claude Code 2.1.330 (Pro plan)  | high            |
| GPT    | `gpt-5.5`                | Codex CLI 0.163.0 (API key)     | high            |
| Gemini | `gemini-3.1-pro-preview` | Gemini CLI 0.65.0 (API key)     | HIGH (thinking) |

**How it works.** A writer model solves a LiveCodeBench problem. A reviewer model reads
the problem and the draft, without running any tests, and returns a revised solution.
The paper's grader (`analysis/lcb_eval_runner.py`) scores the code against hidden
tests. Only drafts that **pass** are sent for review, so any failure after review is a
regression the reviewer caused.

**Prompts.** Writers use the paper's prompt (`harness/prompts/writer_lcb.txt`), and
reviewers use the paper's reviewer prompt (`harness/prompts/reviewer_lcb.txt`). It is
filled in exactly as the paper's pipeline fills it. Each review is a fresh, one-shot
call with no shared conversation.

**Where the drafts come from:**

| Writer  | Drafts from                                        | CLI version used for the draft |
|---------|----------------------------------------------------|--------------------------------|
| Claude  | The paper's original runs (condition A)            | Claude Code 2.1.50             |
| GPT-5.5 | The paper's original runs (condition O)            | Codex CLI 0.125.0-alpha.3      |
| Gemini  | New in this run (condition B3)                     | Gemini CLI 0.65.0              |

All reviews use the current CLI versions in the Setup table.

**Checks done before any paid call (Step 3):**

- `ANTHROPIC_API_KEY` is not set, so Claude bills the Pro plan.
- Gemini B3 uses the paper's writer prompt, not the help-request prompt. It runs at HIGH
  thinking, with no tools and the same parser and grader.
- All three CLIs passed a live "Reply exactly with OK" check.
- The first Codex check failed because the API key had expired. A new key was loaded
  and the check passed.

## Changes made to the harness for this run

### 1. Out-of-credits is now a hard stop

Before this run, the harness had no handling for HTTP 402 (Payment Required) or an
empty balance. Worse, OpenAI reports an empty balance as `insufficient_quota`, and the
harness treated that as an ordinary rate limit and retried it forever.

Now any 402 or out-of-credits error:

- stops the whole run,
- is never retried,
- is never saved as a model failure.

Gemini's ordinary per-minute "quota exceeded" errors still wait and retry as before.
The check only looks at failed calls, so a successful reply that happens to contain
"402" does not stop anything. There are 11 tests for this in
`tests/test_out_of_credits.py`.

### 2. GPT-5.5 reviews without tools, like the other two

**What we found.** Codex loads the user's personal settings (`~/.codex`), which on this
machine include 4 MCP tool servers, 9 plugins, memories, skills and hooks. Codex also
has a **built-in shell** that lets the model run commands, even with no MCP servers.
Gemini, by contrast, already runs with every tool switched off.

**What we changed.** For this run only, GPT reviews use a separate Codex settings folder
(`~/.codex-regression60`, outside the repo) that holds only the login. Shell, web
search and the other built-in tools are switched off, and the sandbox is read-only.
The user's own Codex settings are not touched.

**How we checked.** One test call asked GPT to list its tools and run
`python3 -c 'print(6*7)'`:

- It answered **CANNOT_RUN** and made 0 tool calls.
- The only tools left are a file-edit tool (useless in a read-only folder), an
  "ask the user" tool (no one answers in headless mode) and a wrapper for those two.
  None can run code.
- Input per call dropped from about 17,000 to about 10,600 tokens, so GPT reviews cost
  less than in the demo.

Every GPT review record stores `codex_home: isolated` and its tool-call count.

## Step 1: the 60 problems

The paper's 116 problems (the pooled complete case in
`results/processed/pooled_manifest.csv`) were sorted. Then `random.seed(2026)` gave a
fixed order, and the first 60 problems in that order were kept.

**Replacements: none.** Every one of the 60 has a valid original solo record for both
Claude (A) and GPT-5.5 (O), with the draft code stored.

**Mix:** 26 hard and 34 medium.

```
3562 3634 3677 3688 3714 3715 3716 3717 3720 3721 3722 3737 3754 3759 3760
3762 3763 3764 3771 3779 3783 3784 3786 3789 3794 3795 3801 3805 3809
abc387_c abc388_c abc388_f abc389_e abc389_f abc390_c abc390_g abc391_e
abc391_f abc392_d abc392_g abc393_d abc393_f abc394_d abc394_e abc394_g
abc395_c abc396_c abc396_g abc397_c abc398_b abc398_f abc399_c abc399_d
abc399_e abc399_f abc400_c arc191_c arc194_b arc195_a arc195_e
```

## Step 2: which original drafts pass

Every original draft was **regraded now** with the paper's grader. That way "passed
before review" and "failed after review" come from the same grader.

| Writer  | Passing drafts | Agrees with the paper's stored result |
|---------|----------------|---------------------------------------|
| Claude  | **54 / 60**    | 60 / 60                               |
| GPT-5.5 | **52 / 60**    | 52 / 60                               |

**The 8 disagreements.** All 8 are GPT-5.5 drafts that the paper scored as failing and
that pass today: 3562, 3688, 3717, 3789, 3801, abc388_f, abc399_e and arc195_e.

- Each was regraded two more times on its own and passed every time, so this is not
  random.
- All 8 went from fail to pass; none went the other way.
- **Cause (found later, see "Result of item 1"):** GPT-5.5 wrapped these programs in a
  ```` ```python ```` Markdown fence. The paper's grading ran the fenced text as is
  (a syntax error); the current grader strips the fence, and the code passes.
- Across all 116 problems this affects 15 GPT-5.5 solo programs (item 1). The frozen
  results were not changed. This run uses the regraded
  results, and the paper's values are kept in the `paper_passed` column of the
  inventory.

## Stage 1a: Gemini alone on the first 10 problems

| Measure               | Result                                          |
|-----------------------|-------------------------------------------------|
| Records saved         | 10 / 10                                         |
| Parse failures        | 0                                               |
| Errors or timeouts    | 0                                               |
| Retries               | 0                                               |
| **Passed**            | **10 / 10**                                     |
| Tool calls            | 0 (only `gemini-3.1-pro-preview` was used)      |
| Cost per call         | average **$0.211**, maximum $0.396              |
| Total cost            | $2.11                                           |
| Time per call         | average 109 s, maximum 213 s                    |

| Problem | Result | Cost   | Time  | Output tokens |
|---------|--------|--------|-------|---------------|
| 3562    | pass   | $0.348 | 194 s | 27,581        |
| 3634    | pass   | $0.048 | 21 s  | 2,590         |
| 3677    | pass   | $0.134 | 59 s  | 9,732         |
| 3688    | pass   | $0.396 | 213 s | 31,614        |
| 3714    | pass   | $0.112 | 49 s  | 7,960         |
| 3715    | pass   | $0.202 | 90 s  | 15,448        |
| 3716    | pass   | $0.305 | 166 s | 24,050        |
| 3717    | pass   | $0.346 | 182 s | 27,403        |
| 3720    | pass   | $0.106 | 58 s  | 7,435         |
| 3721    | pass   | $0.109 | 56 s  | 7,620         |

**Cost flag.** The average cost was **48% above the demo's $0.142**, which is more than
the 30% threshold. Gemini thought for much longer on these problems: almost all of its
output is thinking, which is billed as output. The first 10 problems in sorted order are
all LeetCode-style, so they may not represent the other 50.

## Stage 1b: Gemini alone on the other 50 problems

| Measure               | Other 50 problems    | All 60 problems         |
|-----------------------|----------------------|-------------------------|
| Records saved         | 50 / 50              | 60 / 60                 |
| Parse failures        | 0                    | 0                       |
| Errors or timeouts    | 0                    | 0                       |
| Retries               | 0                    | 0                       |
| **Passed**            | **46 / 50**          | **56 / 60 (93%)**       |
| Tool calls            | 0                    | 0                       |
| Average cost per call | $0.171               | **$0.178**              |
| Maximum cost per call | $0.426               | $0.426                  |
| Total cost            | $8.55                | **$10.66**              |
| Average time per call | 87 s                 | 90 s                    |

**Gemini's solo pass rate is 56 / 60 (93%).** The 4 failures are 3763, abc392_d,
abc399_e and arc191_c.

**All three writers on the same 60 problems** (regraded with the same grader):

| Writer  | Hard (26) | Medium (34) | Total (60)      |
|---------|-----------|-------------|-----------------|
| Claude  | 22        | 32          | 54 (90%)        |
| GPT-5.5 | 22        | 30          | 52 (87%)        |
| Gemini  | 24        | 32          | **56 (93%)**    |

Three problems were failed by all three writers: 3763, abc392_d and arc191_c.

**Cost.** Over all 60 problems Gemini averaged $0.178 per call, 25% above the demo's
$0.142. Hard problems cost more (average $0.244) than medium ones ($0.127).

**How to read this:** Gemini's drafts are new, while the Claude and GPT-5.5 drafts come
from the paper's runs on older CLI versions, and the GPT drafts were written with a
shell available. So this table compares the drafts going into review. It is not a clean
head-to-head of the three models.

## Stage 2: reviews

**Passing drafts going into review: 162** (Claude 54, GPT-5.5 52, Gemini 56), so 486 passing-draft
reviews in total, 162 per reviewer.

**Projected cost, computed before starting (Step 6):**

| Account | Remaining before Stage 2 | Projection at demo rates   | Spending cap set |
|---------|--------------------------|----------------------------|------------------|
| Gemini  | about $79                | 162 × $0.260 = **$42**     | $77              |
| OpenAI  | about $44.60             | 162 × $0.123 = **$20**     | $42.50           |
| Claude  | Pro plan                 | $0                         | n/a              |

Even at 25% above the demo's rate (as happened with Gemini solo), Gemini would cost
about $53. GPT calls are now about 38% smaller than in the demo, so its projection is
likely high.

**What was run.** Every draft was reviewed once by each of the 3 reviewers, including
each model reviewing its own drafts: 162 passing drafts (regressions) and 18 failing
drafts (fixes), so 180 reviews per reviewer and **540 in total**.

| Reviewer | Reviews | Valid | Parse failures | Errors | Tool calls | Usage-limit waits |
|----------|---------|-------|----------------|--------|------------|-------------------|
| Claude   | 180     | 180   | 0              | 0      | n/a        | 12 short waits    |
| GPT-5.5  | 180     | 180   | 0              | 0      | 0          | 0                 |
| Gemini   | 180     | 180   | 0              | 0      | 0          | 0                 |

The Claude reviews finished in a few hours on the Pro plan, not days as feared.

### Regression results (breaking working code)

**By reviewer** (all writers pooled; 95% Clopper–Pearson intervals):

| Reviewer | Regressions   | Rate     | 95% interval  | Unchanged | Edit size (mean / median lines) |
|----------|---------------|----------|---------------|-----------|---------------------------------|
| Claude   | 1 / 162       | 0.6%     | 0.0% – 3.4%   | 22%       | 15.0 / 7.5                      |
| GPT-5.5  | **9 / 162**   | **5.6%** | 2.6% – 10.3%  | 7%        | 46.9 / 37.5                     |
| Gemini   | 0 / 162       | 0.0%     | 0.0% – 2.3%   | 29%       | 26.3 / 14.5                     |


**Are the differences real?** All three reviewers saw the same 162 drafts, so they can
be compared draft by draft (exact McNemar test):

| Comparison          | Drafts only the first broke | Only the second broke | p      | After Holm correction (6 tests) |
|---------------------|-----------------------------|-----------------------|--------|---------------------------------|
| GPT-5.5 vs Gemini   | 9                           | 0                     | 0.004  | 0.023, significant              |
| GPT-5.5 vs Claude   | 9                           | 1                     | 0.021  | 0.11, not significant           |
| Claude vs Gemini    | 1                           | 0                     | 1.0    | 1.0                             |

None of the fix-rate comparisons differ (all p = 1.0).

Claude's one break (3784) imports `sortedcontainers`, which the grader lacks; with the
library available it passes, which would make GPT-5.5 vs Claude 9 vs 0 (Holm p ≈ 0.02).
See the note under "Summary of findings".

**By pair** (writer → reviewer):

| Writer  | Reviewer | Regressions | Rate  | 95% interval  | Fixes | Unchanged | Median edit | $/review | Pair total |
|---------|----------|-------------|-------|---------------|-------|-----------|-------------|----------|------------|
| Claude  | Claude   | 0 / 54      | 0%    | 0 – 6.6%      | 2 / 6 | 27%       | 3           | $0.188   | $11.30     |
| Claude  | GPT-5.5  | **5 / 54**  | 9.3%  | 3.1 – 20.3%   | 3 / 6 | 0%        | 45.5        | $0.050   | $3.02      |
| Claude  | Gemini   | 0 / 54      | 0%    | 0 – 6.6%      | 2 / 6 | 7%        | 29          | $0.184   | $11.03     |
| GPT-5.5 | Claude   | 0 / 52      | 0%    | 0 – 6.9%      | 4 / 8 | 35%       | 4           | $0.245   | $14.68     |
| GPT-5.5 | GPT-5.5  | 2 / 52      | 3.8%  | 0.5 – 13.2%   | 2 / 8 | 22%       | 8.5         | $0.042   | $2.53      |
| GPT-5.5 | Gemini   | 0 / 52      | 0%    | 0 – 6.9%      | 4 / 8 | 25%       | 17.5        | $0.177   | $10.59     |
| Gemini  | Claude   | 1 / 56      | 1.8%  | 0.05 – 9.6%   | 0 / 4 | 3%        | 20          | $0.210   | $12.57     |
| Gemini  | GPT-5.5  | 2 / 56      | 3.6%  | 0.4 – 12.3%   | 0 / 4 | 0%        | 61.5        | $0.047   | $2.81      |
| Gemini  | Gemini   | 0 / 56      | 0%    | 0 – 6.4%      | 0 / 4 | 55%       | 0           | $0.173   | $10.38     |

Costs are at API rates from `experiments/configs/pricing.yaml`; Claude's are the
API-equivalent (it ran on Pro at $0). Pair totals include the failing-draft reviews.
GPT-5.5 costs were corrected for a cached-token double count (see "Cost: actual spend").

**Self-review vs. cross-model review** (all reviewers pooled):

| Setting      | Regressions     | 95% interval  | Fixes   | Unchanged | Median edit |
|--------------|-----------------|---------------|---------|-----------|-------------|
| Self-review  | 2 / 162 (1.2%)  | 0.1% – 4.4%   | 4 / 18  | 34%       | 3           |
| Cross-model  | 8 / 324 (2.5%)  | 1.1% – 4.8%   | 13 / 36 | 12%       | 28.5        |

This gap comes almost entirely from GPT-5.5 reviewing other models' code: 7 of the 8
cross-model regressions are by GPT-5.5.

### Every regression

| Problem  | Writer  | Reviewer | Edit size (lines) |
|----------|---------|----------|-------------------|
| 3688     | Gemini  | GPT-5.5  | 114               |
| 3714     | Gemini  | GPT-5.5  | 57                |
| 3715     | Claude  | GPT-5.5  | 22                |
| 3784     | Gemini  | Claude   | 53                |
| abc388_f | Claude  | GPT-5.5  | 106               |
| abc389_e | Claude  | GPT-5.5  | 62                |
| abc396_g | Claude  | GPT-5.5  | 55                |
| abc399_d | Claude  | GPT-5.5  | 76                |
| abc399_e | GPT-5.5 | GPT-5.5  | 81                |
| abc388_f | GPT-5.5 | GPT-5.5  | 68 (time limit)   |

The abc388_f review by GPT-5.5 of its own draft produced a program that did not finish
the hidden tests even with a 1-hour limit (graded alone), so it counts as a fail: the
rewrite made the solution too slow.

Every regression came with a large rewrite (22 to 114 changed lines). No small edit
broke working code.

### Every fix

| Problem  | Writer  | Fixed by (edit size in lines)                       |
|----------|---------|-----------------------------------------------------|
| 3688     | Claude  | Claude (29), Gemini (12), GPT-5.5 (108)             |
| 3754     | GPT-5.5 | Claude (13), Gemini (4), GPT-5.5 (13)               |
| 3762     | GPT-5.5 | Claude (15), Gemini (4)                             |
| abc396_c | GPT-5.5 | Claude (24), Gemini (36)                            |
| abc399_e | Claude  | GPT-5.5 (97)                                        |
| arc194_b | GPT-5.5 | Claude (55), Gemini (50), GPT-5.5 (14)              |
| arc195_e | Claude  | Claude (9), Gemini (20), GPT-5.5 (89)               |

No reviewer fixed any of Gemini's 4 failing drafts. Three of those (3763, abc392_d,
arc191_c) were failed by every writer.

### What stands out

- **GPT-5.5 is the reviewer that breaks working code.** It caused 9 of the 10
  regressions (5.6% of its reviews, against 0.6% for Claude and 0% for Gemini).
  The GPT-5.5 vs Gemini difference survives correction for multiple tests.
- **GPT-5.5 rewrites other models' code heavily.** It returned another model's draft
  unchanged 0 times out of 110, with a median edit of 54.5 lines. On its own drafts it
  edits far less (median 8.5 lines, 22% unchanged), though 2 of its 52 own passing
  drafts still broke. It is also the cheapest and fastest
  reviewer (about $0.05 and 14 s per review).
- **Gemini is the most conservative reviewer.** It broke nothing, but returned its own
  drafts unchanged 55% of the time, and did not fix any of its own 4 failing drafts.
- **Fixing is similar across reviewers:** Claude 6 / 18, Gemini 6 / 18, GPT-5.5 5 / 18.
  With only 18 failing drafts, these rates are very uncertain.
- **GPT drafts written with tools.** Dropping the 5 GPT-5.5 drafts written with tool use
  does not change the conclusions: both GPT-draft regressions (abc399_e and abc388_f,
  GPT reviewing GPT) are among those 5, so GPT-draft regressions go from 2 / 52 to 0 / 47.
  The reviewers' own regression rates are barely affected.

**How to read this:** each draft was reviewed once, so a single regression can be
ordinary run-to-run variation. Pair-level rates rest on about 50 drafts and have wide
intervals; the per-reviewer totals (about 160 drafts each) are the more reliable
numbers.

## FURTHER EXPERIMENTATION

*Added 2026-11-21, after the main run. Nothing in this section has been run yet unless it
says so. Each item says why it is being done and what it would add to a paper.*

### Why do more

The main run gives a clear, publishable-looking result: GPT-5.5 breaks working code
(9 / 162) far more often than Gemini (0 / 162), and the difference survives correction
for multiple tests. Before it can stand in an academic paper, it needs to survive the
questions a reviewer will ask:

1. **Is the original paper's data sound?** We found grader drift (8 GPT-5.5 drafts scored
   as failing now pass), GPT-5.5 having a shell and web search despite a "no tool use"
   description, and a cost double count.
2. **Is the GPT-5.5 result consistent, and why does it happen?** Each draft was reviewed
   once, so the 9 breaks could partly be chance.
3. **Does it generalize?** Everything so far is competitive-programming puzzles from one
   benchmark.
4. **Contamination?** The problems (Jan–Apr 2025) predate Claude's and GPT-5.5's
   training cutoffs.

### The plan

| # | Experiment | Cost | Why | Would it help? | Status |
|---|------------|------|-----|----------------|--------|
| 1 | **Regrade all 116 paper problems × 6 conditions** with the current grader | Free | Checks whether the grader drift we saw on 60 problems affects the paper's published pass rates (GPT-5.5 solo: 71.6%) | **Yes, essential.** If the paper's numbers are off, it must be corrected before anything else; a referee finding it first would damage credibility | **Done: see "Result of item 1" below** |
| 2 | **Recheck the paper's GPT-5.5 costs** for the cached-token double count | Free | The same pricing code produced the paper's cost tables | **Yes.** A cost claim that is 2× off undermines any cost-effectiveness argument | **Done: see "Result of item 2"** |
| 3 | **Classify every break**: wrong answer, too slow, or crash; test whether edit size predicts breaking | Free | Explains *how* review breaks code (e.g. abc388_f was a rewrite that made the program too slow) | **Yes.** A mechanism makes the finding more convincing and more useful | **Done: see "Result of item 3"** |
| 4 | **Repeat GPT-5.5's 180 reviews** (same prompt, fresh calls) | ≈ $8 OpenAI | Shows whether GPT breaks the *same* drafts again or different ones | **Yes.** Separates a consistent weakness from run-to-run noise, the most likely referee objection | **Done: see "Results of items 4 and 5"** |
| 5 | **"Change as little as possible" prompt** for GPT-5.5's 180 reviews (one added line: `harness/prompts/reviewer_lcb_minimal_edit.txt`) | ≈ $8 OpenAI | Tests whether GPT's heavy rewriting is what causes the breaks | **Yes.** If one line removes most breaks, that is a practical, citable contribution | **Done: see "Results of items 4 and 5"** |
| 6 | **BigCodeBench grader check**: install it and grade its own reference solutions twice | Free | BigCodeBench tests depend on pinned libraries and sometimes files or network; a flaky grader would make break counts meaningless | **Decides #7.** Only worth adding BigCodeBench if the grader is reliable | **Done: passed (0 disagreements)** |
| 7a | **If #6 passes: BigCodeBench**, about 60 tasks sampled from the full set (not Hard), all 9 pairings | ≈ $25–35 Gemini, ≈ $5 OpenAI, Claude free | Real-world library code (pandas, files, APIs) instead of puzzles | **Yes, most for the paper.** Answers "does this only apply to competitive programming?"; the full set gives enough passing drafts | **Done (80 tasks): see "Result of item 7a"** |
| 7b | **If #6 fails: the other 56 LiveCodeBench problems**, all 9 pairings | ≈ $40 Gemini, ≈ $8 OpenAI, Claude free | About twice the data on the same problems; full coverage of the paper's 116 | **Somewhat.** Tightens GPT-5.5 vs Claude (now 9 vs 1, not significant after correction) but does not address generality | Not run (#6 passed) |

Only one of 7a and 7b fits the remaining Gemini credit ($48).

### Result of item 1: the paper's GPT-5.5 solo score counts formatting as failure

Every frozen final program in the paper's pooled 116-problem complete case was regraded
with the current grader (`scripts/regression60_regrade116.py`,
`results/processed/regression60_paper_regrade_116.csv`). The frozen records were only
read.

| Paper label | Condition                        | Paper   | Regrade | Fail → pass | Pass → fail |
|-------------|----------------------------------|---------|---------|-------------|-------------|
| A           | `B1_claude_solo`                 | 106/116 | 106/116 | 0           | 0           |
| **O**       | **`B2_gpt55_solo`**              | **83/116 (71.6%)** | **98/116 (84.5%)** | **15** | 0 |
| AO          | `C1_claude_writes_gpt55_reviews` | 96/116  | 96/116  | 0           | 0           |
| OA          | `C2_gpt55_writes_claude_reviews` | 104/116 | 104/116 | 0           | 0           |
| AA          | `C3_claude_writes_claude_reviews`| 106/116 | 106/116 | 0           | 0           |
| OO          | `C4_gpt55_writes_gpt55_reviews`  | 98/116  | 98/116  | 0           | 0           |

(One C1 program, arc194_b, timed out in the regrade and is counted as in the paper.)

**Only the GPT-5.5 solo condition is affected, and only in the hard slice:** 15
programs the paper scored as failing pass today, every time, and nothing flips the
other way.

**Cause, confirmed: a Markdown fence, not wrong code.** Regrading with the paper's own
code (commit 6581226, its in-run batch grading, same configs and 4 workers;
`scripts/paper_code_regrade/`) reproduces the paper (46/82 vs 44/82 stored on the hard
slice) and all 15 fail again, each with "invalid syntax" before any test runs. GPT-5.5
wrapped its code in a ```` ```python ```` fence inside the `<solution>` tags; the paper's
in-run grading passed the fence to Python, while the later grader strips it
(`normalize_code_artifact`) and the same programs pass every test. Fenced programs occur
**only** in GPT-5.5 solo (20 hard, 1 medium, all scored as failing in the paper): in
every reviewed condition the reviewer's output is graded, so GPT-5.5's fences never
reach the grader. LiveCodeBench's own pipeline extracts code from inside fences
(`lcb_runner/utils/extraction_utils.py`), so the official scorer would count these as
passing. The paper therefore penalised GPT-5.5 solo, and only it, for formatting.
Only deviation from the paper's setup: Python 3.14 (the paper's version is unrecorded).

**What it does to the paper's headline comparisons against O:**

| Contrast | Paper   | With the regraded O (98/116) |
|----------|---------|------------------------------|
| OA vs O  | +18.1 pp | **+5.2 pp**                 |
| OO vs O  | +12.9 pp | **+0.0 pp**                 |
| AO vs A  | −8.6 pp  | −8.6 pp (unchanged)         |
| AA vs A  | +0.0 pp  | +0.0 pp (unchanged)         |

The paper's large gains from adding a reviewer to GPT-5.5 largely disappear. **This
must be raised with the coauthors before the paper is used or submitted.**

**How to read this: the paper's number was not miscalculated; it measures something
different from what the paper claims.** The paper's grader gives 83/116 reproducibly
(see above). But 15 of GPT-5.5's 33 failures are correct code in a Markdown fence, so
83/116 mixes "wrote correct code" with "followed the output format", and it is
presented as the first. Three points make this matter:

- *Only GPT-5.5 solo was exposed to the format test.* In every reviewed condition the
  reviewer's output is graded, and no reviewer output was fenced, so the comparison is
  not like for like.
- *The claimed benefit of review is mostly the reviewer removing the fence.* On code
  correctness the gains are +5.2 pp (OA, not significant: 11 vs 5 problems, p = 0.21)
  and 0 (OO, 8 vs 8), down from +18.1 and +12.9 pp (26 vs 5 and 21 vs 6, both
  significant).
- *LiveCodeBench's own scorer would pass these programs*, since its pipeline extracts
  code from inside fences. 98/116 is the benchmark-standard pass rate.

**How much of the gain is the fence, exactly:** OA passes all 15 fenced tasks and OO
passes 13 of them. So 15 of OA's 21-task net gain over O (71%) and 13 of OO's 15-task
net gain (87%) are tasks where GPT-5.5 solo had correct but fenced code.

**BigCodeBench is unaffected:** none of its 238 drafts or 714 reviews, from any model,
is fenced.

A defensible alternative is to keep 83/116 and state explicitly that output formatting
counts as failure, but then the paper must also explain why the reviewed conditions do
not face the same test. Suggested wording for the coauthors: *"The GPT-5.5 solo pass
rate was not miscalculated, but 15 of its failures were formatting, not wrong code: our
grader did not strip Markdown fences, and only the solo condition was exposed to that.
On code correctness GPT-5.5 solo is 98/116, and the claimed benefit of review mostly
disappears."* 5 of the 15
flipped drafts were also written with tool use (see Limitations).

### Result of item 2: the paper's GPT-5.5 costs are overstated by about 45%

`scripts/regression60_cost_recheck.py` prices every turn of the 116 × 6 frozen records
from token counts exactly as the paper's tables did (`compute_metrics.py
--recompute-costs`) and reproduces the paper's cost column to the cent. It then removes
the double count (Codex's `input_tokens` already include the cached tokens, which were
charged again at the cached rate). Per-task detail:
`results/processed/regression60_paper_cost_recheck.csv`.

| Label | Paper $/task | Corrected $/task | Change | Paper score/$ | Corrected score/$ |
|-------|--------------|------------------|--------|---------------|-------------------|
| A  | $0.226 | $0.226 | 0%   | 4.04 | 4.04 |
| O  | $0.190 | **$0.105** | −45% | 3.77 | **6.81** (8.05 with the regraded 98/116) |
| AO | $0.382 | $0.340 | −11% | 2.17 | 2.43 |
| OA | $0.443 | $0.306 | −31% | 2.02 | 2.93 |
| AA | $0.389 | $0.389 | 0%   | 2.35 | 2.35 |
| OO | $0.312 | $0.177 | −43% | 2.71 | 4.77 |

Claude-only conditions are unchanged. **The ranking flips:** GPT-5.5 solo, not Claude
solo, is the most cost-effective condition, and OO beats both Claude conditions. Any
cost-effectiveness claim in the paper must be redone; raise with the coauthors together
with item 1.

### Result of item 3: how reviews break code, and edit size predicts it

`scripts/regression60_classify_breaks.py` re-runs every LiveCodeBench break with the
paper's grader and reads the first failing test's error code; for BigCodeBench it uses
the evaluator's stored failure line. Detail: `results/processed/regression60_break_types.csv`.

| Run | Breaks | Wrong answer | Crash | Too slow |
|-----|--------|--------------|-------|----------|
| LiveCodeBench Stage 2 | 10 | 6 | 3 | 1 |
| LiveCodeBench repeat (item 4) | 7 | 5 | 2 | 0 |
| LiveCodeBench minimal edit (item 5) | 2 | 1 | 0 | 1 |
| BigCodeBench | 18 | 11 | 7 | 0 |

- **Mostly wrong answers:** the rewrite changes the logic and the program still runs.
- **GPT-5.5's LiveCodeBench crashes are input parsing** (e.g. `invalid literal for int()
  with base 2: b'3 3'`, `too many values to unpack`): the rewrite reads the input in a
  different format from the problem's, which a test run would catch at once.
- **Claude's only LiveCodeBench break (3784) is a grader-environment artifact:** the review
  imports `sortedcontainers`, which the grader's Python lacks (LeetCode and AtCoder both
  provide it). On a real judge it may well pass, which would make Claude's count 0 / 162.
- **abc388_f is the one real "too slow" case**, in both GPT-5.5 runs on its own draft.
  The grader's per-test limit did not stop it, so it was capped at 10 minutes per program
  here (and found unfinished after 58–60 minutes alone in Stage 2 and item 5).

**Does edit size predict breaking?** Yes, for every reviewer with enough breaks.
Changed lines on passing drafts, breaks vs. reviews that did not break (one-sided
Mann-Whitney; `results/processed/regression60_edit_size.csv`):

| Run | Reviewer | Breaks: median edit | Others: median edit | p |
|-----|----------|---------------------|---------------------|---|
| LCB Stage 2 | GPT-5.5 | 68 (n = 9) | 36 (n = 153) | 0.005 |
| LCB repeat | GPT-5.5 | 58 (n = 7) | 36 (n = 155) | 0.025 |
| LCB minimal edit | GPT-5.5 | 21 (n = 2) | 0 (n = 160) | 0.004 |
| BigCodeBench | GPT-5.5 | 24 (n = 12) | 11 (n = 127) | 0.002 |
| BigCodeBench | Gemini | 14 (n = 4) | 5 (n = 135) | 0.10 |
| BigCodeBench | Claude | 7.5 (n = 2) | 2 (n = 137) | 0.24 |

Breaks come from larger rewrites, within GPT-5.5 as well as between reviewers. Together
with item 5 (smaller edits, far fewer breaks), this is the mechanism: **review breaks
working code by rewriting it.**

### Results of items 4 and 5: GPT-5.5 breaks are noisy, and a one-line prompt removes most

Same 180 drafts, GPT-5.5 reviewer, fresh calls (`results/processed/regression60_gpt_rep2_*`,
`regression60_gpt_minedit_*`):

| Run | Regressions | Rate (95% interval) | Fixes | Unchanged | Mean edit (lines) |
|-----|-------------|---------------------|-------|-----------|-------------------|
| Stage 2 (original) | 9 / 162 | 5.6% (2.6 – 10.3%) | — | 7% | 46.9 |
| Item 4: repeat, same prompt | 7 / 162 | 4.3% (1.8 – 8.7%) | 2 / 18 | 7% | 45.9 |
| Item 5: "change as little as possible" | **2 / 162** | **1.2% (0.2 – 4.4%)** | 3 / 18 | 74% | 5.2 |

- **Item 4:** the break *rate* repeats but the *drafts* mostly do not: only 3 of the 7
  repeat-run breaks were also broken in the original run. GPT-5.5's breaking is a stable
  tendency, not a fixed set of hard drafts.
- **Item 5:** one added prompt line cuts breaks from 9 to 2 and edit size by about 9×,
  without losing fixes. Heavy rewriting looks like the mechanism.
- One minimal-edit review (abc388_f, GPT-5.5 on its own draft) did not finish the hidden
  tests in 58 minutes graded alone, so it counts as a fail (too slow), the same rule as the
  Stage 2 abc388_f break.

### Result of item 7a: BigCodeBench, all 9 pairings

**Grader check (item 6), passed.** BigCodeBench's official evaluation image
(bigcodebench 0.2.4, pinned by digest) graded all 1,140 reference solutions twice with
0 disagreements; the same 5 references failed both times.

**Setup, and how it differs from the LiveCodeBench run.** Identical models, efforts,
CLIs, isolation (GPT-5.5 without tools), one-shot reviews, and all 9 writer × reviewer
pairings. Differences:

- *Prompts:* `writer_bcb.txt` / `reviewer_bcb.txt` are the LiveCodeBench prompts with
  only the first line changed ("competitive programming problem" → "Python programming
  task").
- *Grader:* BigCodeBench's own evaluator inside its Docker image, as on its leaderboard,
  20 s per task (`harness/benchmarks/bigcodebench.py`), instead of the paper's grader.
- *Tasks:* 80 tasks sampled from the full instruct set (`experiments/task_lists/bcb_80.txt`),
  excluding the 5 always-failing references and any task importing a networking library
  (requests, urllib, socket, …), so no result depends on the internet.
- *Drafts:* written fresh by the three models for this run (not from the paper's runs).
  Gemini returned no usable draft for 2 tasks (78 Gemini drafts), giving 238 drafts and
  714 reviews, all graded (0 grading errors).

**Writers' pass rates:** Claude 57/80, Gemini 42/78, GPT-5.5 40/80, so 139 passing and
99 failing drafts.

**Regressions (breaking a passing draft) and fixes, by reviewer** (all writers):

| Reviewer | Regressions | Rate (95% interval) | Fixes | Fix rate | Unchanged | Mean edit (lines) |
|----------|-------------|---------------------|-------|----------|-----------|-------------------|
| Claude   | 2 / 139     | 1.4% (0.2 – 5.1%)   | **18 / 99** | **18.2%** | 36% | 8.7 |
| GPT-5.5  | **12 / 139**| **8.6% (4.5 – 14.6%)** | 5 / 99 | 5.1% | 6% | 18.4 |
| Gemini   | 4 / 139     | 2.9% (0.8 – 7.2%)   | 6 / 99  | 6.1% | 24% | 10.8 |

**Draft-by-draft comparisons** (exact McNemar test, Holm correction over 6 tests):

| Comparison | Only the first | Only the second | p | After Holm |
|------------|----------------|-----------------|---|------------|
| Breaks: GPT-5.5 vs Claude | 12 | 2 | 0.013 | 0.052, borderline |
| Breaks: GPT-5.5 vs Gemini | 10 | 2 | 0.039 | 0.12, not significant |
| Breaks: Gemini vs Claude  | 3  | 1 | 0.63  | 1.0 |
| Fixes: Claude vs GPT-5.5  | 14 | 1 | 0.001 | **0.006, significant** |
| Fixes: Claude vs Gemini   | 15 | 3 | 0.008 | **0.038, significant** |
| Fixes: Gemini vs GPT-5.5  | 5  | 4 | 1.0   | 1.0 |

**By pair** (writer → reviewer):

| Writer | Reviewer | Broken | Fixed | Unchanged | Median edit |
|--------|----------|--------|-------|-----------|-------------|
| Claude  | Claude  | 0/57 | 0/23 | 73% | 0 |
| Claude  | Gemini  | 2/57 | 1/23 | 8% | 6 |
| Claude  | GPT-5.5 | **7/57** | 0/23 | 4% | 11.5 |
| Gemini  | Claude  | 0/42 | 7/36 | 4% | 11.5 |
| Gemini  | Gemini  | 1/42 | 1/36 | 50% | 0.5 |
| Gemini  | GPT-5.5 | 3/42 | 2/36 | 1% | 21.5 |
| GPT-5.5 | Claude  | 2/40 | **11/40** | 30% | 7 |
| GPT-5.5 | Gemini  | 1/40 | 4/40 | 14% | 13.5 |
| GPT-5.5 | GPT-5.5 | 2/40 | 3/40 | 14% | 12 |

Gemini has 78 drafts, not 80. Both tasks failed on all 3 attempts (a third attempt was
made on 2026-11-22, ~$0.10), so the failure is consistent, not chance: on bcb_303 the
Gemini API ended with "Model stream ended with malformed function call"; on bcb_428
Gemini returned complete code but in a Markdown block without the required
`<solution>` tags, which the parser counts as invalid (the same output rule as the
paper's). Accepting it would change the setup, so both stay missing; with 238 of 240
drafts this cannot change a conclusion.

Full tables: `results/processed/regression60_bcb_metrics.csv`, `_by_pair.csv`,
`_transitions.csv` (every break and fix).

**What it shows.** The LiveCodeBench finding carries over to real-world library code:
GPT-5.5 is again the reviewer that breaks working code most often (12 vs 2 for Claude,
the same direction and similar size as 9 vs 1 on LiveCodeBench), and again it rewrites
most and leaves the fewest drafts unchanged. New on BigCodeBench: Claude fixes failing
drafts significantly more often than either other reviewer, which LiveCodeBench (18
failing drafts) was too small to show. Self-review is mostly a no-op for Claude (73% of
its own drafts unchanged, 0 breaks, 0 fixes). Pooling with LiveCodeBench is not advised,
as graders and pass rates differ; report the two side by side.

**Cost:** recorded at API rates, about $25 Gemini and $10 OpenAI for drafts and reviews
(pilot included); Claude ran on the Pro plan.

### Considered and set aside

- **Fresh problems from after the models' training cutoffs.** This is the cleanest answer
  to contamination, but no ready source exists: the newest LiveCodeBench release (v6)
  ends on 2025-04-06, which is what we already used, and AtCoder's official test cases
  are no longer public. Building tests ourselves (inputs generated within each problem's
  limits, expected outputs from several independent accepted solutions) is possible but
  is roughly a week of careful work. Deferred unless the paper targets a main conference.
- **Contamination is partly addressed already for free.** Gemini's training cutoff
  (January 2025) predates every problem, so Gemini likely never saw them; it broke 0
  drafts. GPT-5.5, which may have seen them, broke 9. Prior exposure clearly does not
  stop a reviewer from breaking code. As a writer, Gemini also passed the most (56/60 vs Claude 54, GPT-5.5
  52), evidence against a large contamination effect (not proof; see Limitations, which
  also notes Gemini 4 Neon as a way to close the training-date gap).

### How these feed the paper

- Items 1–3 correct and explain what we already have, and should be done regardless.
- Items 4–5 turn "GPT-5.5 breaks code" into "GPT-5.5 breaks code consistently, because
  it rewrites, and here is a one-line fix", or show that it does not.
- Item 7 tests whether the finding holds beyond one benchmark.

## Authorship-label study (separate; pilot done)

Regression-60 and BigCodeBench never name an author: every review there is "no label".
Whether a reviewer treats code differently depending on who it is told wrote it is a
separate study. Its full design is below (merged here from the former
`docs/AUTHORSHIP_LABEL_STUDY.md`, drafted 2026-10-17, updated 2026-11-04), followed by
the demo and pilot results. Nothing in it changes the paper's results or the frozen
runs under `results/raw/`.

### Research question and hypotheses

Does a reviewer behave differently depending on who it is told wrote the code? The
paper's reviewer prompt (`harness/prompts/reviewer_lcb.txt`) contains no authorship
information; this study adds one line naming an author and measures whether that line
alone changes the review. Hypotheses, stated as directions to test, not expectations:

- **H1, self-preference:** a reviewer is more lenient (leaves more unchanged, edits
  less, breaks fewer passing drafts) when told the draft is its own.
- **H2, deference:** a reviewer edits less when told the draft is by a model it treats
  as stronger.
- **H3, skepticism:** a reviewer edits more when told the draft is by a model it treats
  as weaker.

H2 and H3 predict opposite signs for the same contrast; the study estimates direction
and size per reviewer and assumes neither.

### Design

**Models.** Three families act as both writers and reviewers, all at high effort with no
tools (`experiments/configs/label_study.yaml`):

| Family | Model | CLI | Label string |
|---|---|---|---|
| Claude | `claude-opus-4-7` | Claude Code | `Claude` |
| GPT | `gpt-5.5` | Codex CLI | `GPT/Codex` |
| Gemini | `gemini-3.1-pro-preview` | Gemini CLI | `Gemini` |

**Drafts are reused, not regenerated.** Every label condition reviews identical code;
only the reviewer calls are new. Drafts are each writer's solo drafts (`B1_claude_solo`,
`B2_gpt55_solo`, `B3_gemini_solo`), already graded, listed in a manifest. Fully
crossed: every draft is reviewed by all three reviewers under every label, so every
comparison is on the same program.

**Labels.** For each draft and reviewer, reviews identical except for one prompt line:

| Label condition | Line shown to the reviewer |
|---|---|
| **True** | the real author: "This code was written by &lt;writer&gt;." |
| **False → model A** | "This code was written by &lt;A&gt;.", A = one of the two models that did not write it |
| **False → model B** | the same, naming the other model that did not write it |
| **No label** | no line |
| **No label, repeated** (pilot only) | identical to no label, run again to measure noise |

With three models every draft has exactly two wrong authors, and each gets its own
false-label review (no random choice). Often one wrong name is the reviewer itself.
Example for Claude reviewing a GPT draft: true "GPT/Codex"; false "Gemini" (another
model); false "Claude" (told it wrote the code itself); no label. Each record stores the
model named (`labeled_family`) and whether it was the reviewer (`label_relation`:
`self`, `other`, `none`).

**Contrasts:**

| Contrast | What it isolates |
|---|---|
| No label vs repeated no label | run-to-run noise floor a label effect must exceed |
| False → self vs false → other, same draft | **self-preference (H1)**, both labels equally wrong; the cleanest test |
| True vs no label | whether naming the real author changes the review |
| True vs each false label | whether the stated author matters, code held fixed |
| Labeled as a given model vs no label | H2/H3: how a reviewer treats a named model |

**Prompt construction.** `reviewer_lcb.txt` is not modified. The template
`harness/prompts/reviewer_lcb_label_study.txt` adds an `{author_label}` line before
`SUBMITTED SOLUTION:` and asks for an `<issues>` list before the `<solution>`. The label
is filled in before the draft, so text inside a draft cannot collide with a placeholder.
Every record stores the SHA-256 of the full prompt and of the template.
`tests/test_label_study.py` enforces: prompts for different labels differ only in the
label line; true and false differ only in the model name; every draft and reviewer gets
a true, a no-label, and one false label per wrong model, never a false label naming the
real author; old single-false-label demo records are reused only for the model they
named; manifest grades override stored grades; the repeat arm adds exactly one unlabeled
repeat per draft and reviewer.

**Known residual differences.** The no-label condition has no label line at all, so
labeled vs no label also measures whether a line is present; the cleanest contrasts are
between labeled conditions. An optional neutral label ("written by an AI model") would
isolate this. The no-label condition uses the label template (it asks for `<issues>`),
not the paper's exact reviewer prompt.

**Self-identity.** Each CLI tells its model what it is (Claude Code: Claude; Codex: an
OpenAI/Codex agent; Gemini CLI: Gemini). It is not verified that each reviewer
identifies with its label string, in particular that GPT-5.5 reads "GPT/Codex" as
itself.

**Earlier demo version.** The first demo (2026-11-02) gave each draft only one false
label, chosen with a fixed seed (`label_seed: 20261101`), which mixed "another model"
with "you". Those 18 reviews are reused as the false-label review for the model they
named (saved as `L_<writer>_by_<reviewer>_false`); the 18 missing ones were added
2026-11-04 as `L_<writer>_by_<reviewer>_false_<model named>`.

**Cell order** is shuffled across labels and reviewers, so rate limits or drift over
time do not line up with one label.

### Metrics and tests

Each review is one of: **fixed** (draft failed, returned code passes), **changed, same
outcome**, **unchanged** (returned code equals the draft after normalization), or
**regression** (draft passed, returned code fails).

- **Primary** (informative on every draft): unchanged rate, edit size (changed lines),
  issues reported (items in `<issues>`).
- **Secondary** (low power): fix rate on failing drafts, regression rate on passing
  drafts. Invalid outputs are reported separately, never counted as regressions.
- **Tests:** McNemar (exact) on the same drafts for binary outcomes, each false label
  tested separately, never pooled; Wilcoxon signed-rank for edit size and issues. The
  demo used Benjamini–Hochberg (`analysis/statistical_tests.py`); the pilot uses Holm
  within each reviewer (`scripts/label_pilot_analysis.py`).

### Files

| Path | Purpose |
|---|---|
| `experiments/configs/label_study.yaml` | Reviewers, template, seed |
| `experiments/configs/label_demo_drafts.yaml` | Demo draft manifest |
| `experiments/configs/label_pilot_drafts.yaml`, `label_study_pilot*.yaml` | Pilot manifest and configs (GPT without tools; `_no_claude`, `_claude_only` split passes) |
| `harness/prompts/reviewer_lcb_label_study.txt` | Labeled reviewer template |
| `experiments/run_label_study.py` | Builds cells, reviewer-only calls with checkpoint/resume, `--repeat-none`, `--max-spend`, grading |
| `analysis/label_study_metrics.py` | Per-cell tables and paired tests |
| `scripts/label_pilot_analysis.py` | Pooled paired contrasts with Holm (pilot) |
| `tests/test_label_study.py` | Prompt, label-assignment, override and repeat tests |
| `results/raw/demo_labels/`, `results/raw/label_pilot/` | Demo and pilot records |
| `results/processed/label_study_demo_*.csv`, `label_pilot_*.csv` | Tables |

Tables: `_summary.csv` (reviewer × writer × label, false labels pooled),
`_by_false_label.csv` (each false label separate), `_self_vs_other.csv` (by relation),
`_paired_tests.csv` (McNemar of each label vs no label), `label_pilot_contrasts.csv`
(pooled pilot contrasts). Records reuse the `TaskRecord` schema; the draft is copied
into `writer_artifact` with writer cost 0, and `extra` holds `source_record`,
`draft_sha256`, `writer_family`, `reviewer_family`, `label_arm`, `labeled_family`,
`label_text`, `label_relation`, `draft_unchanged`, `diff_lines`, `issue_count`,
`issues`.

**Untouched:** `results/raw/lcb_hard_full/` and `lcb_medium_100/` are read-only inputs
(the runner refuses a checkpoint inside them); `run_experiment.py`, `reviewer_lcb.txt`,
`writer_lcb.txt`, `all_conditions.yaml` and the paper's processed tables are unchanged.

### Scale and cost

| Run | Drafts | Reviews | Cost |
|---|---|---|---|
| Demo (done) | 6 | 72 | ~$9 Gemini + GPT; Claude on Pro |
| Pilot (done, with repeat) | 30 | 450 | Gemini $29.01, GPT-5.5 $7.41, Claude $43.10 API-equivalent |
| Hard tier, 61 tasks × 3 writers | 183 | 2,196 (2,745 with repeat) | est. ~$280 Gemini + GPT at demo rates; Claude ~$0.29/review on credits |
| Pooled 116 tasks × 3 writers | 348 | 4,176 | est. ~$530 Gemini + GPT |

### Plan

1. ~~Runner, prompts, analysis, tests.~~ Done.
2. ~~Demo (6 drafts).~~ Done 2026-11-02; both false labels 2026-11-04.
3. ~~Pilot with repeated no-label noise floor.~~ Done 2026-11-22 (results below).
4. Style-recognition test: not run.
5. Hard tier, then optionally medium for the pooled 116: not run; decision after the
   pilot (see "Reading" below).

### Side test (not run): can reviewers recognize the author?

If a reviewer can tell the author from style, "no label" is not truly blind and a false
label may be seen through. Design: forced choice "Which model wrote this solution:
Claude, GPT or Gemini?", one word, no review; about 40 drafts per writer shown to each
reviewer; report accuracy against 1-in-3 chance (binomial test) and the confusion matrix.
If accuracy is well above chance, "no label" is read as implicitly labeled.

### Limitations of the label study

- **Power:** few drafts fail for the strongest writers, so fix rates rest on few cases;
  hence unchanged rate, edit size and issues are primary.
- **Environment drift:** CLI versions and possibly model serving changed since the
  paper's runs, and Gemini is a preview model; only comparisons within this study are
  valid.
- **Same transfer boundary as the paper** (see [SCOPE.md](SCOPE.md)): fixed prompts,
  high effort, one static rewrite-only review, no tools, single-file Python with hidden
  tests.
- **What a label effect would mean:** that the reviewer conditions on stated authorship
  in this prompt format, not how labels act in real workflows, where authorship comes
  through commit metadata or context.

### Results

**Demo (2026-11-01 to 11-04, before this run):** 6 drafts (one passing, one failing per
writer, 3 problems) × 3 reviewers × 4 labels = 72 reviews, all valid.

- Passing drafts: 0 breaks under any label (36 reviews).
- Failing drafts: 19 fixed, 12 changed but still failing, 5 unchanged.
- All 81 paired tests p = 1.0 after correction: no evidence either way.
- Cleanest self-preference comparison (two equally false labels, "you wrote this" vs "a
  third model wrote this"): the reviewer fixed the draft only when told it was its own in
  3 of 6, the reverse in 1, same in 2. Worth testing, not a finding (one draft, one
  review per comparison).
- Gemini returned its own drafts unchanged in 7 of 8 reviews regardless of label.
- Caveat: the demo's GPT reviewer used the default Codex setup, which likely had shell
  tools; the demo's no-label condition uses the label template, not the paper's exact
  prompt.

**Pilot (approved and run 2026-11-22).** 10 problems from the regression-60 sample ×
3 writers = 30 drafts (17 passing, 13 failing; every writer has failing drafts): 6
problems chosen for failing drafts (3763, abc392_d, arc191_c, abc399_e, 3688, 3754) and
4 drawn at random from all-pass problems (3720, 3794, abc391_e, abc397_c). Each reviewer
reviews each draft 5 times: true, both false labels, no label, and a **repeated no-label
review to measure run-to-run noise**. 450 reviews (150 per reviewer).

Fixes so the pilot matches regression-60:

- GPT-5.5 reviews **without tools** (isolated Codex home); verified, 0 tool calls.
- Draft pass/fail from the **regression-60 regrade** (fence stripped), not the paper's
  stored grade, which would have marked 2 passing GPT-5.5 drafts as failing.
- **Spending caps** (`--max-spend`): Gemini $29, OpenAI $16 (balances $31 and $18). If
  a cap is reached the run stops starting new reviews for that model, keeps finished
  ones, and can resume after a top-up.

Estimated cost: Gemini $27–39, GPT-5.5 $8–14, Claude $0 (Pro plan). Files:
`experiments/configs/label_pilot_drafts.yaml`, `label_study_pilot.yaml`,
`results/raw/label_pilot/`, logs `results/raw/label_pilot.log`, `label_pilot_claude.log`.

**Pilot results (2026-11-22).** All 450 reviews done and graded (150 per reviewer; the
last 3 Gemini reviews were run after the cap at the user's request), 0 invalid, 0
grading errors. Spend: Gemini $29.01, GPT-5.5 $7.41, Claude $43.10 API-equivalent
($10.40 on the Pro plan, ~$32.70 from usage credits). Analysis:
`scripts/label_pilot_analysis.py` → `results/processed/label_pilot_contrasts.csv`
(per-cell tables: `results/processed/label_pilot_*.csv`). Every comparison is paired on
the same draft; McNemar for unchanged / pass, Wilcoxon for edit size and issue count,
Holm within reviewer.

| Reviewer | Contrast (n drafts) | Unchanged | Mean edit (lines) | Passing after review | Holm p (smallest) |
|---|---|---|---|---|---|
| Claude | **Noise:** no label vs repeat (30) | 9 vs 9 | 14.6 vs 11.1 | 18 vs 19 | 1.0 |
| Claude | **Self-pref:** "you wrote it" vs "third model" (20) | 7 vs 7 | 10.2 vs 14.1 | 13 vs 13 | 1.0 |
| Claude | True label vs no label (30) | 11 vs 9 | 7.3 vs 14.6 (raw p = 0.02) | 19 vs 18 | 0.50 |
| GPT-5.5 | **Noise** (30) | 6 vs 5 | 34.6 vs 35.1 | 18 vs 18 | 1.0 |
| GPT-5.5 | **Self-pref** (20) | 0 vs 0 | 50.0 vs 57.5 | 12 vs 12 | 1.0 |
| GPT-5.5 | True vs no label (30) | 5 vs 6 | 36.2 vs 34.6 | 20 vs 18 | 1.0 |
| Gemini | **Noise** (30) | 14 vs 14 | 21.5 vs 17.3 | 21 vs 20 | 1.0 |
| Gemini | **Self-pref** (20) | 5 vs 4 | 26.4 vs 28.4 | 14 vs 14 | 1.0 |
| Gemini | True vs no label (30) | 14 vs 14 | 18.5 vs 21.5 | 20 vs 21 | 1.0 |

In the self-preference rows, both labels are false: "you wrote it" names the reviewer;
"third model" names the model that is neither the reviewer nor the real author. Split by
draft author, so the third model is explicit (10 drafts each; A = told "you wrote it",
B = told the third model wrote it):

| Reviewer | Real author | Third model named (B) | Drafts | Unchanged A vs B | Mean edit A vs B | Passing after A vs B | Fixes A vs B | Breaks A vs B |
|---|---|---|---|---|---|---|---|---|
| Claude | GPT-5.5 | Gemini | 10 | 5 vs 6 | 7.0 vs 2.8 | 7 vs 7 | 1 vs 1 | 0 vs 0 |
| Claude | Gemini | GPT-5.5 | 10 | 2 vs 1 | 13.4 vs 25.3 | 6 vs 6 | 0 vs 0 | 0 vs 0 |
| GPT-5.5 | Claude | Gemini | 10 | 0 vs 0 | 43.6 vs 54.9 | 6 vs 6 | 1 vs 1 | 0 vs 0 |
| GPT-5.5 | Gemini | Claude | 10 | 0 vs 0 | 56.4 vs 60.2 | 6 vs 6 | 0 vs 0 | 0 vs 0 |
| Gemini | Claude | GPT-5.5 | 10 | 1 vs 1 | 37.1 vs 40.3 | 7 vs 7 | 2 vs 2 | 0 vs 0 |
| Gemini | GPT-5.5 | Claude | 10 | 4 vs 3 | 15.8 vs 16.5 | 7 vs 7 | 1 vs 1 | 0 vs 0 |

Pass/fail, fixes and breaks are identical in every row. Edit size moves in both
directions: on GPT-5.5's drafts Claude edited more when told "you wrote it" than when
told Gemini wrote it (7.0 vs 2.8 lines), while on Gemini's drafts it edited less when
told "you wrote it" than when told GPT-5.5 wrote it (13.4 vs 25.3). With 10 drafts per
row and no consistent direction, this is within run-to-run noise.

What it shows:

- **No label effect beyond noise.** For every reviewer, the true, false and self labels
  move unchanged rate, edit size, issues and outcome by no more than two identical
  no-label runs differ from each other. Nothing is significant after correction.
- **No self-preference.** Told "you wrote this" vs "a third model wrote this" (same
  draft, both false), each reviewer fixed exactly as many drafts (Claude 1 vs 1, GPT-5.5
  1 vs 1, Gemini 3 vs 3) and broke none. The demo's 3-of-6 hint did not replicate.
- **One weak hint, not significant:** Claude edited less when given the true label
  (7.3 vs 14.6 lines, raw p = 0.02, Holm 0.50) or told the code was its own (10.2 vs
  18.1, raw p = 0.03, Holm 0.78). Its own noise contrast differs by 3.5 lines, so this is
  worth checking in a larger run, not a finding.
- **Model behavior is far bigger than any label:** GPT-5.5 never left another model's
  draft unchanged under any label and edits ~35–57 lines; Claude and Gemini leave a third
  to half unchanged. Breaks: Claude 0, Gemini 0, GPT-5.5 1 across all labels.
- **Noise floor:** between two identical no-label runs, the pass/fail outcome flipped on
  1 draft per reviewer and the unchanged status on 2–6.

**Reading:** with 20–30 paired drafts per reviewer, the pilot can rule out large label
effects, not small ones. A full study aiming at small effects needs several times more
drafts (the planned hard tier: 183 drafts, ~$280 at demo rates, more with Claude on
credits). Given no signal here, the label question is lower priority than the
review-breaks-code findings.

Not yet run: the style-recognition test (can a reviewer tell the author without a
label?), an optional neutral label ("written by an AI model"), and the full study
(~$280 for the hard tier).

## Cost: actual spend

| Part                                   | Gemini       | OpenAI (GPT-5.5) | Claude (API-equivalent) |
|----------------------------------------|--------------|------------------|-------------------------|
| Preflight and test calls               | about $0.03  | about $0.40      | $0                      |
| Gemini solo drafts (60)                | $10.66       | n/a              | n/a                     |
| Reviews of passing drafts (162 each)   | ┐            | ┐                | ┐                       |
| Reviews of failing drafts (18 each)    | ┘ $32.01     | ┘ $8.36          | ┘ ($38.56)              |
| **Total**                              | **≈ $42.70** | **≈ $8.40**      | **$0** (Pro plan)       |
| Credits loaded                         | $90          | $45              | Pro                     |
| **Left, per the billing pages**        | **$48**      | **$37**          | n/a                     |

Total actual spend: **about $51**, under the $80 target. Costs are computed from token
counts at the rates in `experiments/configs/pricing.yaml`, and match the balances
reported on the provider billing pages after the run.

**Correction: GPT-5.5 cost was first overstated by about 2×.** Codex reports
`input_tokens` *including* the cached tokens, and the harness priced the cached tokens
twice (once at the full rate, once at the cached rate). The first version of this table
said $16.60; the corrected figure, $8.40, matches the OpenAI billing page. The harness is
fixed (new Codex records store only uncached input tokens, flagged
`input_tokens_exclude_cached`), and the analysis corrects older records. **The paper's
own GPT-5.5 cost figures were computed the same way and are likely overstated too.**

**Claude's API-equivalent** is $38.56 from `pricing.yaml`, as the run spec asks. Claude
Code itself reports $49.46 for the same reviews; the difference is how it prices cache
writes.

**Per review** (average): Claude $0.214 (API-equivalent), GPT-5.5 $0.046, Gemini $0.178.
**Time per review** (median): Claude 21 s, GPT-5.5 14 s, Gemini 82 s.

### Follow-up spend (2026-11-22)

| Part | Gemini | OpenAI (GPT-5.5) | Claude (API-equivalent) |
|------|--------|------------------|-------------------------|
| Item 4: GPT-5.5 repeat (180 reviews) | n/a | $7.02 | n/a |
| Item 5: minimal-edit prompt (180 reviews) | n/a | $7.53 | n/a |
| BigCodeBench drafts (240, incl. pilot) | $5.79 | $3.01 | ($15.85) |
| BigCodeBench reviews (714, incl. pilot) | $19.47 | $7.37 | ($44.13) |
| Items 1–3, 6, sortedcontainers check, paper-code regrade | $0 | $0 | $0 |
| Authorship-label pilot (450 reviews) | $29.01 | $7.41 | $43.10 ($10.40 Pro + ~$32.70 usage credits) |
| Third attempt at 2 Gemini BCB drafts | ~$0.10 | n/a | n/a |
| **Total follow-ups** | **≈ $54** | **≈ $32** | **~$33 usage credits** (rest on Pro) |

All GPT-5.5 figures use the corrected (single-counted) cached tokens. Balances: before
the label pilot Gemini $21 (topped up to $31), OpenAI $18; Claude usage credits $90
loaded for the pilot. **After everything (2026-11-22): Gemini ≈ $1.90, OpenAI ≈ $10,
Claude credits ≈ $57.**

### Budget history

| Account | Credits loaded           | Spent before Stage 2 |
|---------|--------------------------|----------------------|
| Gemini  | $90 ($70 + $20 top-up)   | about $10.70         |
| OpenAI  | $45 ($30 + $15 top-up)   | about $0.40          |
| Claude  | Pro plan                 | $0                   |

**Earlier projection after Stage 1a** (kept for the record), assuming about 156 passing
drafts. This led to the credit top-ups:

| Account | If review costs match the demo | If reviews are also 48% higher |
|---------|--------------------------------|--------------------------------|
| Gemini  | about $53                      | about $73 (over the limit)     |
| OpenAI  | about $19                      | about $28 (tight)              |

The OpenAI numbers should come in lower, because GPT calls are now about 38% smaller
(see "GPT-5.5 reviews without tools"). The exact Stage 2 cost will be computed from the
real number of passing drafts before Stage 2 starts. The Stage 2 runner can also stop
each account at a spending cap (`--max-spend`).

## Limitations and caveats

- **Drafts and reviews come from different CLI versions.** The Claude and GPT-5.5 drafts
  come from the paper's original runs on older CLI versions (Claude Code 2.1.50, Codex
  CLI 0.125.0-alpha.3). All reviews, and the Gemini drafts, use current versions.
- **The paper's GPT-5.5 drafts were written with tools.** The frozen records show the
  GPT writer ran 562 shell commands and 40 web searches across the paper's 685 Codex
  calls, and the GPT reviewer ran 2 shell commands. This conflicts with the paper's
  "no tool use" description and is worth raising with the coauthors. **In this run's
  sample, only 5 of the 60 GPT-5.5 drafts were written with tool use.** The analysis
  reports GPT-draft results with and without those 5 drafts. Claude barely used tools
  in the paper: 9 of its 369 writer calls took 2–3 turns, and the rest took 1.
- **GPT reviews here differ from the demo.** The demo's GPT reviewer loaded the user's
  Codex settings, including tools. This run's GPT reviewer has no tools.
- **Grader drift, explained.** 8 of the paper's GPT-5.5 "failing" drafts pass today
  (Step 2); across 116 problems, 15. Cause confirmed: GPT-5.5 wrapped code in a Markdown
  fence that the paper's grading did not strip (see "Result of item 1"). The rerun of
  the paper's own code used Python 3.14; the paper's Python version is unrecorded.
- **Few failing drafts.** Only 18 drafts failed (Claude 6, GPT-5.5 8, Gemini 4), so the
  fix rates are very rough. Gemini's 4 failing drafts include 3 problems no writer solved.
- **One review per draft** in the main run (GPT-5.5 was repeated once, item 4: similar
  rate, mostly different drafts; Claude and Gemini were not repeated). Each draft was reviewed once per reviewer, so run-to-run
  variation is not measured.
- **Not a pre-registered test.** The significance tests were chosen after seeing the
  data; treat them as a guide, not a confirmed finding.
- **Possible contamination.** The 60 problems come from the newest LiveCodeBench release
  (v6) and are dated Jan 4 – Apr 5, 2025. Published training cutoffs: Claude Opus 4.7,
  January 2026; GPT-5.5, December 2025; Gemini 3.1 Pro, January 2025. So the problems are
  **before** Claude's and GPT-5.5's cutoffs (they may have seen them, and their public
  solutions) but **after** Gemini's. Solo pass rates for Claude and GPT-5.5 may be
  inflated. The regression measurement is less affected, since it asks what a reviewer
  does to a fixed draft. Gemini, the one reviewer that likely had not seen the problems,
  broke none of the drafts.

  **Evidence that contamination is small, not proof.** If prior exposure gave Claude
  and GPT-5.5 a large advantage, they should out-solve a model that never saw the
  problems. They do not: Gemini, writing without exposure, passed **56/60**, more than
  Claude (54/60) and GPT-5.5 (52/60). This argues against a large contamination effect.
  It does not rule out a small one, because the models differ in ability as well as in
  training dates: a stronger Gemini could hide a modest boost that exposure gave the
  other two. BigCodeBench (released mid-2024, before all three cutoffs) gives a
  comparison with equal exposure, and the reviewer pattern holds there.

  **Possible follow-up: Gemini 4 Neon.** `gemini-4-neon` (generally available, training
  cutoff March 2026) would put all three models after the problems, closing the gap in
  training dates. It would mean rerunning every Gemini draft and review on both
  benchmarks (estimated $40–60). Before deciding: confirm the API key can access it
  (some users report it showing as unavailable) and that it is a comparable tier to
  Gemini 3.1 Pro. Gemini 3.1 Pro was used because it was Google's flagship Pro model when
  Gemini was added (2026-11-01); the training cutoff was not considered then.
- **Gemini is a preview model,** and its behavior may change.
- **The paper had unusable outputs** (no program to grade: CLI error, timeout, nothing
  extracted), all on the hard slice: Claude conditions 15–17 of 82 (mostly Claude CLI
  errors), GPT-5.5 conditions 2–6. The paper's headline uses only the 116 tasks where all
  six conditions were gradable, and reports a second view counting them as failures.
  "Unusable" is not bad syntax: code with bad syntax is graded and fails.
- **The grader's per-test time limit does not stop every hung program.** abc388_f ran
  for an hour at 100% CPU; such programs were capped and counted as too slow, the same
  rule as the Stage 2 abc388_f break.
- **The grading environment lacks some judge libraries** (`sortedcontainers`), which
  turned Claude's 3784 review into a crash; kept as graded, noted separately.
- **BigCodeBench is not pooled with LiveCodeBench:** different grader (official Docker
  evaluator, 20 s per task), different tasks (network-using tasks and 5 always-failing
  references excluded), fresh drafts. Report side by side.
- **Claude cost.** Claude runs on a Pro subscription, so it costs nothing. Its cost at
  API prices is recorded for comparison.
- **Gemini's cost varies a lot by problem,** from $0.05 to $0.40 per call in Stage 1a,
  so early averages are a rough guide.

## Files

- **Task lists:** `experiments/task_lists/lcb_regression_60.txt` and
  `lcb_regression_60_first10.txt`.
- **Sample log:** `results/processed/regression60_sample_log.json` (seed, full seeded
  order, replacements, slice of each problem).
- **Draft inventory:** `results/processed/regression60_draft_inventory.csv`.
- **Raw records:** `results/raw/regression60_gemini_solo/`,
  `results/raw/regression60_preflight/`, and later `results/raw/regression60_reviews/`.
- **Scripts:** `scripts/regression60_sample.py`, `scripts/regression60_inventory.py`,
  `scripts/regression60_grade_solo.py`, and the Stage 2 runner
  `experiments/run_regression60_reviews.py`.
- **Harness changes:** `harness/core/cli_runner.py` (out-of-credits stop, isolated Codex
  settings), `harness/core/pipeline.py`, `experiments/run_experiment.py`,
  `experiments/run_label_study.py`.
- **Tests:** `tests/test_out_of_credits.py`, `tests/test_regression60_reviews.py`.
- **Tables:** `results/processed/regression60_metrics.csv` (by reviewer, own vs other
  models' drafts, self vs cross), `regression60_by_pair.csv` (by pair, with a
  `no_tool_drafts` row for GPT-5.5 drafts), `regression60_transitions.csv` (every
  regression and fix).
- **Review records:** `results/raw/regression60_reviews/R_<writer>_by_<reviewer>/`.
- **Analysis:** `scripts/regression60_analyze.py`.

Follow-ups (2026-11-22):

- **Paper regrade (item 1):** `scripts/regression60_regrade116.py` →
  `results/processed/regression60_paper_regrade_116.csv`; paper's own code:
  `scripts/paper_code_regrade/` (README, `paper_batch_regrade.py`,
  `paper_batch_meta.py`) → `results/processed/regression60_paper_code_b2_hard_meta.json`.
- **Cost recheck (item 2):** `scripts/regression60_cost_recheck.py` →
  `results/processed/regression60_paper_cost_recheck.csv`.
- **Break classification (item 3):** `scripts/regression60_classify_breaks.py` →
  `regression60_break_types.csv`, `regression60_edit_size.csv`.
- **GPT-5.5 repeat / minimal edit (items 4–5):** `results/raw/regression60_gpt_rep2/`,
  `results/raw/regression60_gpt_minedit/`, prompt
  `harness/prompts/reviewer_lcb_minimal_edit.txt`, tables `regression60_gpt_rep2_*.csv`,
  `regression60_gpt_minedit_*.csv`.
- **BigCodeBench (items 6–7a):** `harness/benchmarks/bigcodebench.py`,
  `experiments/run_bcb_writers.py`, `experiments/task_lists/bcb_80.txt`, prompts
  `harness/prompts/writer_bcb.txt` / `reviewer_bcb.txt`, `scripts/resume_bcb.sh`,
  `tests/test_bigcodebench.py`; records `results/raw/regression60_bcb_drafts/`,
  `regression60_bcb_reviews/`; tables `regression60_bcb_*.csv`.
- **sortedcontainers check:** `scripts/regression60_check_3784_sortedcontainers.py`.
- **Label pilot:** `experiments/configs/label_pilot_drafts.yaml`,
  `label_study_pilot.yaml` (+ `_no_claude`, `_claude_only`),
  `experiments/task_lists/label_pilot_10.txt`, records `results/raw/label_pilot/`,
  analysis `scripts/label_pilot_analysis.py` → `results/processed/label_pilot_*.csv`.
- **Chat brief:** `docs/CONTEXT_BRIEF_FOR_CHAT.md` (self-contained summary of all of this).

---

## For Miles: questions your professor may ask

**"What is a regression here?"**
A draft that passed the hidden tests before review and fails them after review. Only
passing drafts are reviewed, so every such failure is caused by the reviewer.

**"Why regrade the original drafts?"**
So "before" and "after" are scored by the same grader. Otherwise a regression could just
be grader drift.

**"Why do 8 GPT-5.5 drafts disagree with the paper?"**
GPT-5.5 put its code in a ```` ```python ```` fence. The paper's grading ran the fence
as code (a syntax error); the current grader strips it, and the code passes every test.
Rerunning the paper's own code reproduces the paper exactly, so the paper's number was
computed correctly but counts a formatting issue as wrong code. Across all 116 problems
this affects 15 GPT-5.5 solo programs and only that condition (see "Result of item 1").

**"Did GPT-5.5 have tools in the paper?"**
Yes. Codex has a built-in shell, and the paper's records show the GPT writer used it
hundreds of times. In this run the GPT reviewer has no tools, like Claude and Gemini.

**"Why is Gemini more expensive than in the demo?"**
It thought much longer on these problems. Thinking tokens are billed as output.

**"So which reviewer should you use?"**
GPT-5.5 is the cheapest reviewer (about $0.03–0.05 per review) but breaks working code
most often on both benchmarks, by rewriting it. Claude breaks the least and, on
BigCodeBench, fixes the most (18/99 vs 5 and 6). Gemini is cautious like Claude but fixes
no more than GPT-5.5. If GPT-5.5 is used, add the minimal-edit line.

**"Is GPT-5.5 significantly worse?"**
On LiveCodeBench: against Gemini yes (9 vs 0, Holm p = 0.023); against Claude 9 vs 1 is
not significant (p = 0.11), and would be 9 vs 0 (p ≈ 0.02) if the grader had
`sortedcontainers`. On BigCodeBench 12 vs 2 against Claude is borderline (Holm p =
0.052). The direction is the same on both benchmarks.

**"Does self-review break less?"**
Pooled, a little (1.2% vs 2.5%), but that is mostly GPT-5.5 rewriting other models' code.
Within each reviewer the samples are too small to say.

**"Are the results comparable with the paper?"**
Partly. The LiveCodeBench drafts are the paper's own, but the reviews use newer CLI
versions, and the GPT reviewer has no tools. BigCodeBench uses its own official grader
and fresh drafts, so it is reported beside LiveCodeBench, not pooled.

**"So was the paper wrong?"**
Its statistics are not wrong: the paper's own code reproduces 83/116 and the review gains
exactly. But 15 of GPT-5.5 solo's failures are correct code in a Markdown fence, which
makes up 71% (OA) and 87% (OO) of the claimed gain from review. That needs
reinterpreting. The cost tables are an actual error (item 2).

**"Why were cached tokens counted twice?"**
A bug, not a choice. The pricing formula adds input, cached and cache-creation tokens,
which is right for Anthropic (input excludes cached) but wrong for OpenAI, whose
`input_tokens` already include the cached tokens. This run had the same bug at first;
it was caught because spend did not match OpenAI billing, and fixed. Cached tokens are
still counted once, at the cheap rate.

**"Does the reviewer prompt force a rewrite?"**
No. It allows returning the original if correct, but asks for "an improved version" and
"inefficiencies" and requires a full program. Each model chose how much to change; only
GPT-5.5 rewrote by default. The minimal-edit line was tested only on GPT-5.5 (item 5).

**"Why does GPT-5.5 change so much?"**
It is a default, not a limit: with one "smallest change needed" line it left 74% of
drafts unchanged and its mean edit fell from 47 to 5 lines. It rewrites its own drafts
too, and part of the change is cosmetic. Why it defaults to rewriting (the agentic
Codex CLI, training) is not tested here.

**"Why did Gemini break 0 on LiveCodeBench?"**
It changes less, and 0 vs Claude's 1 out of 162 is noise; it broke 4/139 on BigCodeBench.

**"Didn't Claude and GPT-5.5 see these problems in training?"**
Possibly (cutoffs Jan 2026 and Dec 2025; problems Jan–Apr 2025). Gemini 3.1 Pro's cutoff
(Jan 2025) is before them, yet it solved the most (56/60), which argues against a large
contamination advantage, though it is not proof. BigCodeBench (mid-2024) gives an equal-
exposure comparison, and the pattern holds. Gemini 4 Neon (cutoff Mar 2026) could close
the gap (~$40–60). Gemini 3.1 Pro was chosen as Google's flagship Pro model when added;
the cutoff was not considered then.

**"What does 'unusable' mean, and did the paper have any?"**
No program to grade (CLI error, timeout, nothing extracted), not bad syntax; bad syntax
is graded and fails. The paper had them on the hard slice only (mostly Claude CLI
errors) and excluded them from its headline 116 tasks. Here: 0 in the main run; 2
Gemini BigCodeBench drafts failed all 3 attempts.

**"Did you run all the pairings?"**
Yes: all 9 writer → reviewer pairings on both benchmarks (see "Results by model and
pairing").

**"Do authorship labels matter?"**
Not measurably in the pilot (450 reviews): true, false, "you wrote this" and no label
differ no more than two identical runs, and there is no self-preference. Small effects
are not ruled out; the full study (~$280+) would be needed.
