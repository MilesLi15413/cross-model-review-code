# Follow-up Study: Blind vs. Labeled Authorship in Cross-Model Review

**Status:** design, not yet run. Drafted 2026-10-17.

This page describes a planned follow-up experiment: what it asks, how it is designed,
what it changes in the repository, and what it leaves untouched. It is written before
any data is collected, so that the hypotheses and primary metrics are fixed in advance.
Items marked **TBD** are open decisions.

Nothing here changes the paper's results or the frozen runs under `results/raw/`.

## Research question

Does a reviewer behave differently depending on who it is told wrote the code?

The original study's reviewer prompt (`harness/prompts/reviewer_lcb.txt`) contains no
authorship information. The reviewer sees only the problem, the starter code and the
parsed draft. This study adds an explicit authorship label and measures whether the
label alone changes the review.

Hypotheses, stated as directions to test, not as expected results:

- **H1, self-preference:** a reviewer is more lenient (leaves more unchanged, regresses
  fewer passing drafts) when the draft is labeled as its own model's.
- **H2, deference:** a reviewer edits less when the draft is labeled as written by the
  other model, if it treats that model as stronger.
- **H3, skepticism:** a reviewer edits more when the draft is labeled as written by the
  other model, if it treats that model as weaker.

H2 and H3 predict opposite signs for the same contrast. The study estimates the
direction and size of the label effect for each reviewer and does not assume either one.

## Design

### Drafts are reused, not regenerated

Every arm reviews identical code. Only reviewer calls are new.

- **Draft source (TBD, recommended):** one Claude draft and one GPT draft per task,
  taken from the solo conditions (`B1_claude_solo`, `B2_gpt55_solo`). Each draft is
  reviewed by both reviewers under every arm, a fully crossed design.
  - Pro: every comparison, across arms and across reviewers, is made on the same
    program. Solo records already store a scored draft (`passed` is the draft's own
    outcome).
  - Con: the counts do not line up one-to-one with the paper's per-pair transition
    counts, which used each pair's own writer draft (C1–C4).
- **Alternative:** use each pair's own stored draft (`writer_artifact` in C1–C4). Arm
  contrasts within a pair stay clean, but AA and AO review different Claude drafts, so
  reviewers cannot be compared on the same code.

Drafts are re-scored with the current LiveCodeBench evaluator before use, so draft and
final outcomes are judged in the same environment. Any draft whose re-score disagrees
with the stored `passed` value is reported and excluded from transition counts.

### Arms

| Arm | Label shown to the reviewer |
|-----|-----------------------------|
| Blind | none: the current `reviewer_lcb.txt`, byte for byte |
| True | the actual author |
| Swapped | the other model (a Claude draft is labeled GPT-5.5, a GPT draft is labeled Claude Opus 4.7) |

Label strings: `Claude Opus 4.7` and `GPT-5.5`.

The blind arm is rerun on the same drafts rather than reusing the paper's old reviewer
outputs, so all arms are sampled with the same CLI versions, at the same time and the
same way.

### Cells

2 drafts per task (Claude, GPT) × 2 reviewers (Claude, GPT) × 3 arms = **12 reviewer
calls per task**.

For a given reviewer and draft, the True and Swapped arms differ only in whether the
label names the reviewer's own model ("self") or the other model ("other"). The
analysis reports the effect both ways: true vs. swapped, and self-label vs.
other-label.

### Prompt construction

- `reviewer_lcb.txt` is not modified.
- A new template, `harness/prompts/reviewer_lcb_labeled.txt`, is identical to it
  except for the solution header, which becomes
  `SUBMITTED SOLUTION (written by {author_label}):`.
- `{author_label}` is filled in before the problem and the draft are substituted, so
  text inside a problem statement or draft cannot collide with the placeholder.
- Every record stores the full reviewer prompt's SHA-256, as the existing harness does.

Tests enforce these invariants:

1. The blind prompt rebuilt for a stored record reproduces that record's
   `reviewer_prompt_sha256`.
2. A labeled prompt differs from the blind prompt in exactly one line.
3. True and Swapped prompts differ only in the label string.

**Known residual difference:** the blind arm has no label line at all, so blind vs.
labeled also measures whether a label line is present. The cleanest label contrast is
true vs. swapped. An optional fourth arm with a neutral label ("written by an AI
model") would isolate the presence effect; it is not planned unless the pilot shows a
blind-vs-labeled gap.

### Self-identity

The Claude Code CLI tells the model it is Claude, so a "Claude Opus 4.7" label signals
"self" to the Claude reviewer. The Codex CLI identifies itself as an OpenAI/Codex agent,
and it is not verified that it identifies with the string "GPT-5.5". The pilot records
whether each reviewer appears to recognize its own label (for example, from mentions in
the review text).

## Metrics

For each reviewer × draft author × arm:

**Primary** (sensitive on every draft, not just failing ones):

- **Unchanged rate:** share of reviews whose final program is essentially the draft.
  "Essentially unchanged" means equal after stripping comments, docstrings and
  formatting (AST dump comparison).
- **Edit size:** difflib similarity ratio and changed-line count between draft and
  final, after normalization.

**Secondary** (the paper's transition metrics; low power, see Limitations):

- Fix: the draft failed and the final passed.
- Regression: the draft passed and the final failed.
- Kept-pass and kept-fail.
- Invalid outputs (CLI error, timeout, parse failure), reported separately and not
  counted as regressions.

**Tests:**

- McNemar tests between arms on the same drafts, for the binary outcomes.
- Wilcoxon signed-rank tests on paired edit size.
- Benjamini–Hochberg correction across the family of contrasts, matching
  `analysis/statistical_tests.py`.

**Noise floor:** in the pilot, the blind arm is run twice on the same drafts (**TBD**).
The between-run flip rate is the baseline a label effect has to exceed.

## Side test: can reviewers recognize the author?

If a reviewer can tell who wrote a draft from its style, the "blind" arm is not truly
blind.

- Prompt: a short forced choice, "Which model wrote this solution: Claude or GPT?",
  answering with one word and no review.
- Sample: about 40 drafts per writer, balanced, shown to each reviewer.
- Report: balanced accuracy, a binomial test against 50%, and the confusion matrix
  (catches a reviewer that always answers the same model).
- This runs before the main pilot. If accuracy is well above chance, the blind arm is
  read as "implicitly labeled", and the results say so.

## What changes in the repository

New:

| Path | Purpose |
|------|---------|
| `harness/prompts/reviewer_lcb_labeled.txt` | Labeled reviewer template |
| `harness/prompts/author_guess_lcb.txt` | Style-recognition prompt |
| `experiments/configs/authorship_conditions.yaml` | The 12 cells: draft source, reviewer, arm |
| `experiments/run_review_only.py` | Loads stored drafts and runs reviewer-only calls, with checkpointing and resume |
| `analysis/authorship_label_analysis.py` | Transitions, unchanged rate, edit size, paired tests, BH correction |
| `analysis/author_guess_analysis.py` | Style-recognition accuracy |
| `tests/test_review_only.py`, `tests/test_authorship_prompts.py`, `tests/test_authorship_analysis.py` | Tests, including the prompt invariants above |
| `results/raw/authorship_<slice>/` | New raw records |
| `results/processed/authorship_*.csv` | New tables |

Modified:

- `harness/core/pipeline.py`: the reviewer call and its timeout retry move out of
  `TwoPassPipeline._run_task_once` into a shared helper used by both runners. The
  original pipeline's behaviour is unchanged, and the existing tests must still pass.
- `README.md`: one link to this page.

New records reuse the `TaskRecord` schema. The source draft is copied into
`writer_artifact` and writer cost is set to 0, so it is not counted twice. These fields
are added to `extra`:

- `source_record`: path of the record the draft came from
- `draft_sha256`
- `label_arm`: `blind`, `true` or `swapped`
- `label_text`
- `attributed_author`
- `draft_passed_rescored`

Cell order is shuffled across arms rather than run arm by arm, so rate limits or drift
over time do not line up with an arm.

## What stays untouched

- `results/raw/lcb_hard_full/` and `results/raw/lcb_medium_100/` are read-only inputs.
  The new runner refuses a checkpoint path inside either directory.
- `experiments/run_experiment.py`, `harness/prompts/reviewer_lcb.txt`,
  `harness/prompts/writer_lcb.txt` and `experiments/configs/all_conditions.yaml` are
  unchanged.
- The paper's processed tables are not regenerated or overwritten.

## Scale and cost

Estimated from the reviewer costs stored in the original runs (Claude reviewer about
$0.71–1.02 per hard task and about $0.38 per medium task; GPT reviewer about $0.13):

| Run | Reviewer calls | Est. cost |
|-----|----------------|-----------|
| Style test | ~160 | ~$15–30 |
| Pilot: 10 hard tasks × 12 cells, plus a repeated blind arm | ~160 | ~$75 |
| Hard tier, 61 complete-case tasks | 732 | ~$370 |
| Pooled 116 tasks (hard + medium) | 1,392 | ~$540 |

Claude reviews are about 85% of the cost. Estimates are re-checked against
`experiments/configs/pricing.yaml` and the pilot's actual spend before the full run.

Pilot tasks are hand-picked so that both writers have failing drafts in the sample.
On the hard complete case, Claude's solo draft fails on 8 of 61 tasks and GPT's on 25.

## Plan and decision points

1. **Environment:** install the Codex CLI, set up LiveCodeBench via `setup.sh`, confirm
   that `claude-opus-4-7` and `gpt-5.5` still respond, and record CLI versions.
   (Claude Code was 2.1.50 in the original runs and is 2.1.302 now.)
2. **Re-score drafts** and report any disagreement with the stored outcomes.
3. **Implement** the prompts, runner, configs and analysis, with tests.
4. **Style test.**
5. **Pilot.** Report cost, invalid outputs, the noise floor and any problems.
   *Decision point:* go or no-go on the hard tier, and whether to add the neutral-label
   arm.
6. **Hard tier**, then optionally medium for the pooled 116.

## Limitations

- **Power:** on the pooled 116 tasks, Claude's solo drafts fail only 10 times, so fix
  rates for Claude drafts rest on about 10 cases. This is why edit size and unchanged
  rate are primary.
- **One sample per cell:** reviewer outputs are stochastic. Without the repeated blind
  arm, label effects cannot be separated from run-to-run noise.
- **Environment drift:** CLI versions, and possibly model serving, have changed since
  the original runs. Only comparisons within this study are valid. Comparisons with
  the paper's reviewer numbers are not.
- **Same transfer boundary as the paper** (see [SCOPE.md](SCOPE.md)): one model pair,
  fixed prompts, high effort, a single static rewrite-only review, no tools, and
  single-file Python tasks scored by hidden tests.
- **What a label effect would mean:** it shows the reviewer conditions on stated
  authorship in this prompt format. It does not show how labels act in real workflows,
  where authorship usually comes through commit metadata or context rather than one
  header line.

## Open decisions (TBD)

- [ ] Draft source: solo drafts, fully crossed (recommended), or each pair's own drafts
- [ ] Repeat the blind arm in the pilot to measure the noise floor (recommended, about +$15)
- [ ] Permission to install the Codex CLI and clone LiveCodeBench under `external/`
- [ ] Scope after the pilot: hard tier only, or pooled 116
