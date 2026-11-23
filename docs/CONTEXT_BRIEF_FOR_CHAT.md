# Context brief: cross-model code review study (original paper vs. follow-up experiments)

Date of this brief: 2026-11-22. Everything below is from the project repo
(`cross-model-review-code`, branch `bigcodebench-check`); full detail is in
`docs/REGRESSION60_RUN.md`.

---

## 1. The original paper: what it ran

**Question:** does having a second AI model review code improve it?

**Models (one version each):** Claude Opus 4.7 (`claude-opus-4-7`, via Claude Code CLI) and
GPT-5.5 (`gpt-5.5`, via Codex CLI), both at high reasoning effort.

**Six conditions ("pipelines"):**

| Label | Pipeline |
|-------|----------|
| A  | Claude writes, no review |
| O  | GPT-5.5 writes, no review |
| AO | Claude writes, GPT-5.5 reviews and outputs the final program |
| OA | GPT-5.5 writes, Claude reviews |
| AA | Claude writes, Claude reviews |
| OO | GPT-5.5 writes, GPT-5.5 reviews |

**Benchmark:** LiveCodeBench (competitive programming: AtCoder and LeetCode-style
problems, single-file Python, hidden tests). Hard slice (82 tasks) and medium slice
(55 tasks). Headline table = 116 tasks where all six conditions produced a gradable
program (61 hard + 55 medium), the "complete case".

**Review step:** one static pass. The reviewer sees the problem and the draft, cannot
run tests or use tools, and must output a full replacement program. Reviewer prompt:
"Identify any bugs, incorrect logic, missing edge cases, or inefficiencies. Produce a
final corrected solution — either the original if it is correct, or an improved
version. Do NOT run or test the code." Output goes inside `<solution>` tags.

**Design limitation the paper itself stated:** each condition sampled its own writer
draft, so e.g. OA vs O compares two independent pipelines, not what a reviewer did to a
particular draft. The paper listed "freeze each draft, score it, then review it" as
planned follow-up.

**Grading:** LiveCodeBench's evaluator, run in one batch per condition at the end of the
run. **Costs:** recomputed from stored token counts at list prices.

**Unusable outputs:** hard slice only (mostly Claude CLI errors: 12–17 per Claude
condition, 2–6 per GPT condition); excluded from the complete case, counted as failures
in a secondary "reliability-inclusive" view. Medium slice had none.

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
both significant after correction). "If Claude writes, handing the draft to GPT-5.5 did
not help" (AO −8.6 pp). AA = A. AO vs OA not separable (p_BH = .14), so no general
ranking of reviewers. Claude solo most cost-effective.

---

## 2. What we did (follow-up experiments)

### Main experiment ("regression-60"): does review break code that already works?

- **60 problems** drawn from the paper's 116 (`random.seed(2026)`; 26 hard, 34 medium).
- **Three writers:** Claude and GPT-5.5 drafts reused from the paper's original solo runs
  (A and O); **Gemini 3.1 Pro** (`gemini-3.1-pro-preview`, Gemini CLI, high thinking)
  drafts written new.
- **Every draft regraded now with one grader** before review, so "passed before" and
  "failed after" use the same grader. Drafts passing: Claude 54/60, GPT-5.5 52/60,
  Gemini 56/60 (162 passing, 18 failing).
- **Three reviewers × every draft** (all 9 writer → reviewer pairings): 540 reviews, each
  a fresh one-shot call with the **paper's reviewer prompt, unchanged**, no authorship
  label.
- **Key measurements:** *regression* = passing draft fails after review (reviewer broke
  it); *fix* = failing draft passes after review. Because the draft is fixed, these are
  direct measurements of the reviewer's effect (the paper's planned follow-up).
- Harness changes: GPT-5.5 reviews run **without tools** (shell/web off) like the other
  two; out-of-credits is a hard stop; Codex cost double count fixed (see findings).
- Claude ran on a Pro subscription ($0 actual; API-price equivalents recorded).

### Follow-up items (all done)

1. **Regrade the paper's 116 × 6 final programs** with the current grader (free).
2. **Recheck the paper's GPT-5.5 costs** for a cached-token double count (free).
3. **Classify every break** (wrong answer / crash / too slow) and test whether edit size
   predicts breaking (free).
4. **Repeat GPT-5.5's 180 reviews** with fresh calls (is breaking consistent?).
5. **"Change as little as possible" prompt** for GPT-5.5 (one added line: "Make the
   smallest change needed. If the solution is already correct, return it unchanged; do
   not rewrite or restructure code that works").
6. **BigCodeBench grader check:** official evaluator in its pinned Docker image graded
   all 1,140 reference solutions twice, 0 disagreements → reliable.
7. **BigCodeBench run:** 80 tasks from the full instruct set (real-world Python with
   pandas, files, etc.), excluding 5 always-failing references and tasks that use the
   network. Same models, settings and prompts (only the first line changed from
   "competitive programming problem" to "Python programming task"); BigCodeBench's own
   evaluator. Drafts written fresh. 238 drafts (Gemini gave no usable draft on 2 tasks:
   API errors), 714 reviews, all graded.

**Spend (approx., API rates, GPT-5.5 corrected):** regression-60 Gemini ~$43, OpenAI
~$8; GPT-5.5 repeat ~$7 and minimal-edit ~$7.5; BigCodeBench Gemini ~$25, OpenAI ~$10;
Claude $0 (Pro plan). Free: regrades, cost recheck, break classification, paper-code
rerun, sortedcontainers check. Label pilot (running): est. Gemini $27–39, OpenAI $8–14.

---

## 3. Findings

### A. Review breaks working code; GPT-5.5 does it most

| Reviewer | LCB: broke (of 162 passing) | LCB: fixed (of 18 failing) | BCB: broke (of 139) | BCB: fixed (of 99) | Unchanged (LCB / BCB) | Median edit lines (LCB / BCB) |
|----------|------|------|------|------|------|------|
| Claude  | 1\* (0.6%) | 6 | 2 (1.4%) | **18** | 22% / 36% | 7.5 / 6 |
| GPT-5.5 | **9 (5.6%)** | 5 | **12 (8.6%)** | 5 | 7% / 6% | 37.5 / 15 |
| Gemini  | 0 (0%) | 6 | 4 (2.9%) | 6 | 29% / 24% | 14.5 / 6 |

- LCB significance (paired McNemar, Holm over 6 tests): GPT-5.5 vs Gemini 9 vs 0,
  p = 0.023 (significant); GPT-5.5 vs Claude 9 vs 1, p = 0.11 (not significant).
- BCB: breaks GPT-5.5 vs Claude 12 vs 2, Holm p = 0.052 (borderline); **fixes: Claude vs
  GPT-5.5 p = 0.006, Claude vs Gemini p = 0.038 (both significant)**.
- Worst pairing on both benchmarks: GPT-5.5 reviewing Claude's drafts (5/54 LCB, 7/57 BCB).
- \*Claude's one LCB break (problem 3784) imports `sortedcontainers`, missing from the
  paper's grading environment. In a separate throwaway check with the library available
  it passes (twice) → 0/162 on a judge that provides it (LeetCode/AtCoder do). Official
  count stays 1/162. With 0, GPT-5.5 vs Claude would be 9 vs 0 (Holm p ≈ 0.02).

### B. Mechanism: rewriting

- Breaks come from larger edits: for GPT-5.5, breaking edits ~2× larger than
  non-breaking (p ≤ 0.025 in all four runs; BCB p = 0.002).
- **One-line minimal-edit prompt:** GPT-5.5 breaks 9 → 2 of 162, unchanged 7% → 74%,
  mean edit 47 → 5 lines, no loss of fixes (3/18).
- Break types: mostly wrong answers (LCB 6/10, BCB 11/18); GPT-5.5's LCB crashes are
  input-parsing rewrites (reads input in the wrong format); one "too slow" (abc388_f).
- GPT-5.5 rewrites by default, even its own drafts (unchanged on only 14% of its own BCB
  drafts vs Claude 73%); some edits are cosmetic.

### C. Stability

Repeating GPT-5.5's reviews: 7/162 breaks (similar rate), but only 3 were the same
drafts. Stable tendency, not a fixed set of hard drafts.

### D. Writers

LCB: Gemini 56/60, Claude 54/60, GPT-5.5 52/60. BCB: Claude 57/80, Gemini 42/78,
GPT-5.5 40/80. Self-review is mostly a no-op for Claude (73% of own BCB drafts unchanged,
0 breaks, 0 fixes).

### E. The paper's GPT-5.5 solo score (item 1)

- Current-grader regrade: only O changes, 83/116 → 98/116; all 15 flips fail→pass, all
  hard slice; other five conditions match exactly.
- **Cause confirmed by rerunning the paper's own code (commit 6581226, same in-run batch
  grading, same configs):** it reproduces the paper (46/82 vs 44/82 stored on hard) and
  all 15 fail again, each with "invalid syntax" before any test runs. GPT-5.5 wrapped
  its code in a ```` ```python ```` Markdown fence inside the solution tags; the paper's
  grading passed the fence to Python; the later grader strips it and the same code
  passes every test. Fenced programs occur **only** in O (20 hard, 1 medium), because in
  reviewed conditions the reviewer's (unfenced) output is graded. LiveCodeBench's own
  pipeline extracts code from inside fences, so the official scorer would pass them.
- **Interpretation:** the paper's statistics are **not wrong** (they reproduce exactly
  and are significant as graded), but they count formatting as failure. On code
  correctness: O = 98/116; OA vs O +5.2 pp (11 vs 5, p = 0.21, not significant); OO vs O
  0 (8 vs 8). AO vs A unchanged (−8.6 pp, 3 vs 13, p = 0.02). Needs reinterpreting, not
  correcting.
- Side note: 5 of the 15 flipped GPT-5.5 drafts were written with tool use (Codex shell),
  although the paper describes a no-tool setup.

### F. The paper's GPT-5.5 costs (item 2): an actual error

The paper's code stored Codex's `input_tokens` (which already include cached tokens) and
the cached count, and priced both, so cached tokens were charged twice. Claude was
unaffected (Anthropic reports cached separately). Evidence: cached > input in 0 of 685
GPT turns; cached ≈ 67% of input. Same bug existed in our harness at first; caught
because spend didn't match OpenAI billing; fixed (now matches billing).

| Label | Paper $/task | Corrected | Paper score/$ | Corrected score/$ |
|-------|------|------|------|------|
| A  | 0.226 | 0.226 | 4.04 | 4.04 |
| O  | 0.190 | **0.105** | 3.77 | **6.81** (8.05 with 98/116) |
| AO | 0.382 | 0.340 | 2.17 | 2.43 |
| OA | 0.443 | 0.306 | 2.02 | 2.93 |
| AA | 0.389 | 0.389 | 2.35 | 2.35 |
| OO | 0.312 | 0.177 | 2.71 | 4.77 |

GPT-5.5 solo becomes the most cost-effective condition (holds even with the paper's own
pass rate). Costs are list-price estimates (repo `pricing.yaml`), not invoices.

---

### G. All 9 pairings and each model

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

- GPT-5.5 is the riskiest reviewer of other models' code (worst on Claude's drafts); on
  its own drafts it breaks less but still rewrites.
- The best fixer depends on the writer (Claude fixes GPT-5.5's failing drafts most).
- Self-review is mostly a no-op for Claude and Gemini (half or more of own drafts
  unchanged, almost no breaks or fixes).

| | Claude | GPT-5.5 | Gemini |
|---|---|---|---|
| Cost per review (LCB / BCB) | $0.21 / $0.12 (API-equivalent; ran on Pro) | $0.05 / $0.03 (cheapest) | $0.18 / $0.08 |
| Median review time (LCB / BCB) | 21 s / 6 s | 14 s / 13 s | 82 s / 24 s |

Profiles: **Claude** — safest and most useful reviewer (fewest breaks, most fixes on
BCB), best BCB writer, most expensive at list prices. **GPT-5.5** — cheapest, but rewrites
almost everything and breaks the most; the minimal-edit line fixes most of that.
**Gemini** — cautious like Claude (0 LCB breaks, 4 BCB), fixes no more than GPT-5.5,
slowest; best LCB writer (56/60) despite a training cutoff before the problems.

**The reviewer prompt neither forces a rewrite nor asks for minimal edits.** It allows
returning the original if correct, but requires a full program and asks for "an improved
version" and "inefficiencies". How much to change was each model's choice. The
minimal-edit line was used only in item 5, only for GPT-5.5.

**Why GPT-5.5 changes so much (measured):** rewriting is a default, not a limit (minimal-
edit line → 74% unchanged, mean edit 47 → 5 lines); it rewrites its own code too (14% of
own BCB drafts unchanged vs Claude 73%); part is cosmetic (4% exactly unchanged on
Claude's BCB drafts, 16% ignoring whitespace); the prompt's "improved version" invites it.
Untested hypotheses: the Codex CLI is built as an agent that makes changes; training
differs in deference to existing code.

**Why Gemini broke 0 on LCB:** it changes less (31% of passing drafts unchanged, median
edit 14.5 vs GPT-5.5's 37.5), and 0 vs Claude's 1 out of 162 is noise (95% interval
0–2.3%); on BCB it broke 4. When it edits, edits are large (mean 37 lines) yet rarely
break, so it seems to keep the original logic.

### H. Authorship labels (separate study; pilot running)

Regression-60 and BigCodeBench never name an author (all "no label"). The label study
varies one prompt line: *true* author, *false* × 2 (each model that did not write it;
often "you wrote this"), *no label*; reviewers also list issues.

- **Demo (Nov 1–4, before this run):** 6 drafts × 3 reviewers × 4 labels = 72 reviews.
  Passing drafts: 0 breaks under any label. Failing: 19 fixed, 12 changed-still-failing,
  5 unchanged. All 81 paired tests p = 1.0 after correction. Self-preference hint (told
  "you wrote this" vs "a third model wrote this"): fixed only when told own in 3/6,
  reverse 1/6, same 2/6 — worth testing, not a finding. Gemini left its own drafts
  unchanged 7/8 regardless of label. Caveat: demo GPT reviewer likely had shell tools.
- **Pilot (approved and running 2026-11-22):** 10 problems × 3 writers = 30 drafts (17
  passing, 13 failing), each reviewed 5× per reviewer (true, 2 false, no label, repeated
  no label for a noise floor) = 450 reviews. GPT-5.5 without tools (verified), drafts
  graded with the fence stripped, spending caps Gemini $29 / OpenAI $16. Estimated cost
  Gemini $27–39, GPT-5.5 $8–14, Claude $0. Results pending.
- Not yet run: style-recognition test (can reviewers tell the author unlabeled?), neutral
  label, full study (~$280 hard tier).

## 4. Paper vs. new results at a glance

- **Reproduced, needs reinterpreting:** GPT-5.5 solo 71.6% and the "review helps
  GPT-5.5" gains (+18.1 / +12.9 pp) are correct as graded, but mostly a formatting
  (fence) effect; on correctness +5.2 pp (n.s.) and 0.
- **Corrected (actual error):** GPT-5.5 costs ~45% too high; cost-effectiveness ranking
  flips to GPT-5.5 solo.
- **Reinforced:** AO worse than A — explained directly by GPT-5.5 breaking Claude's
  working drafts. AA adds nothing — Claude leaves its own drafts alone. The paper's
  scope warning (nothing protects a good draft from a worse rewrite) is shown to happen.
- **Partly revised:** "no ranking of reviewers" still holds at the pipeline level, but on
  fixed drafts GPT-5.5 breaks most (both benchmarks), Claude fixes most (BCB), Claude vs
  Gemini on breaks not separable; the writer still matters.
- **New:** direct reviewer-effect measurement; break rates; rewriting mechanism; one-line
  minimal-edit fix; stability; fix rates; third model and second benchmark.
- **Still open (as in the paper):** findings-only review with human adjudication,
  reviewers with tools/tests, multiple writer samples per task, multi-file code.

**One sentence:** the paper's statistics stand as graded, but its main story (review
improves GPT-5.5's code) is mostly a formatting effect; the better-supported story is
that a rewrite-style review pass often breaks working code, the choice of reviewer
matters, and asking for minimal edits largely prevents it.

---

## 5. Caveats and limitations

- **Contamination:** LCB problems dated Jan–Apr 2025. Training cutoffs: Claude Opus 4.7
  Jan 2026, GPT-5.5 Dec 2025, Gemini 3.1 Pro Jan 2025. Claude/GPT may have seen the
  problems; Gemini almost certainly not. Evidence the effect is small (not proof):
  Gemini, without exposure, out-solved both (56 vs 54 and 52) — argues against a large
  advantage, but ability differences could hide a small one. BCB (mid-2024, before all
  cutoffs) is the equal-exposure comparison, and the reviewer pattern holds there.
- **Possible follow-up:** swap in `gemini-4-neon` (GA, cutoff March 2026) to close the
  training-date gap; rerun all Gemini parts (~$40–60). First confirm API access and that
  it is a comparable tier. Gemini 3.1 Pro was chosen (2026-11-01) as Google's flagship
  Pro model; cutoff was not considered then.
- One review per draft in the main run (plus one GPT-5.5 repeat); one writer sample per
  task.
- Significance tests chosen after seeing the data — a guide, not confirmatory.
- Gemini is a preview model. Claude/GPT-5.5 LCB drafts were written with older CLI
  versions (the paper's); reviews used current CLIs.
- The grader's per-test time limit did not stop one hung program (abc388_f); such
  programs were capped and counted as too slow, the same rule as Stage 2.
- BigCodeBench differs from LCB in grader, task type and selection (network tasks
  excluded), so report the two side by side, do not pool.
- BigCodeBench Gemini has 78 drafts, not 80: bcb_303 (Gemini CLI error) and bcb_428
  (every attempt invalid: "Model stream ended with malformed function call").
- "Unusable" output means no program to grade (CLI error, timeout, nothing extracted),
  not bad syntax; bad syntax is graded and fails. The paper had unusable outputs on the
  hard slice only (Claude conditions 15–17 of 82, mostly Claude CLI errors; GPT-5.5
  conditions 2–6); its headline uses only the 116 tasks gradable in all six conditions.
- The paper-code rerun (item 1) used Python 3.14; the paper's Python version is
  unrecorded. Otherwise identical code, configs and grading flow.

## 6. Status and next steps

- All work committed locally on `bigcodebench-check` (not pushed).
- Authorship-label pilot running (450 reviews); results to follow.
- **Raise with coauthors before the paper is used or submitted:** (1) the GPT-5.5 solo
  score counts formatting as failure, which removes most of the claimed review benefit;
  (2) the GPT-5.5 cost tables are inflated, which flips the cost-effectiveness claim.
- Optional: retry the 2 missing Gemini BCB drafts (cents); Gemini 4 Neon rerun.
