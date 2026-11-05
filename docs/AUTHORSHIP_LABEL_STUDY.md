# Follow-up Study: Authorship Labels in Cross-Model Review

**Status:** design fixed; demo run only. Drafted 2026-10-17. Updated 2026-11-04 to the
three-model design with both false labels.

This page describes a follow-up experiment: what it asks, how it is designed, what it
adds to the repository, and what it leaves untouched. The hypotheses and primary
metrics are fixed here before the full run. Items marked **TBD** are open decisions.

Nothing here changes the paper's results or the frozen runs under `results/raw/`.

## Research question

Does a reviewer behave differently depending on who it is told wrote the code?

The original study's reviewer prompt (`harness/prompts/reviewer_lcb.txt`) contains no
authorship information. The reviewer sees only the problem, the starter code and the
parsed draft. This study adds one line naming an author and measures whether that line
alone changes the review.

Hypotheses, stated as directions to test, not as expected results:

- **H1, self-preference:** a reviewer is more lenient (leaves more unchanged, edits
  less, regresses fewer passing drafts) when told the draft is its own.
- **H2, deference:** a reviewer edits less when told the draft is by a model it treats
  as stronger.
- **H3, skepticism:** a reviewer edits more when told the draft is by a model it treats
  as weaker.

H2 and H3 predict opposite signs for the same contrast. The study estimates the
direction and size of each label effect per reviewer and does not assume either one.

## Design

### Models

Three model families act both as writers and as reviewers:

| Family | Model | CLI | Label string |
|---|---|---|---|
| Claude | `claude-opus-4-7` | Claude Code | `Claude` |
| GPT | `gpt-5.5` | Codex CLI | `GPT/Codex` |
| Gemini | `gemini-3.1-pro-preview` | Gemini CLI | `Gemini` |

All reviewers run at high reasoning effort with no tools
(`experiments/configs/label_study.yaml`).

### Drafts are reused, not regenerated

Every label condition reviews identical code. Only the reviewer calls are new.

- **Draft source:** each writer's solo drafts (`B1_claude_solo`, `B2_gpt55_solo`,
  `B3_gemini_solo`), already graded. The solo record's `passed` is the draft's own
  outcome. Drafts are listed in a manifest (for the demo,
  `experiments/configs/label_demo_drafts.yaml`).
- **Fully crossed:** every draft is reviewed by all three reviewers under every label,
  so all comparisons, across labels and across reviewers, are made on the same program.

### Labels

For each draft and each reviewer there are **four reviews**, identical except for one
line of the prompt:

| Label condition | Line shown to the reviewer |
|---|---|
| **True** | the real author: "This code was written by &lt;writer&gt;." |
| **False → model A** | "This code was written by &lt;A&gt;.", where A is one of the two models that did not write it |
| **False → model B** | the same, naming the other model that did not write it |
| **No label** | no line |

Since there are three models, every draft has exactly two wrong authors, and **each one
gets its own false-label review**. There is no random choice of which false name to
use.

For a given reviewer, one of the two wrong names is often the reviewer itself. Example
for Claude reviewing a GPT draft:

| Label condition | Claude is told |
|---|---|
| True | "written by GPT/Codex" |
| False → Gemini | "written by Gemini" (another model) |
| False → Claude | "written by Claude" (told it wrote the code itself) |
| No label | nothing |

Each record stores the model named (`labeled_family`) and whether it was the reviewer
itself (`label_relation`: `self`, `other` or `none`).

### Cells

N drafts × 3 reviewers × 4 label conditions = **12 reviewer calls per draft**.

The demo used 6 drafts (one passing and one failing from each writer), so 72 reviews.

### Contrasts

| Contrast | What it isolates |
|---|---|
| True vs. no label | whether naming the real author changes the review |
| False → self vs. false → other, same draft | **self-preference (H1)**, with both labels equally wrong; the cleanest test |
| True vs. each false label | whether the stated author matters, holding the code fixed |
| Self-labeled vs. other-labeled, pooled | H1 across all label conditions |
| Labeled as a given model (e.g. "Gemini") vs. no label, across drafts | H2/H3: how a reviewer treats a named model |

### Earlier version (demo of 2026-11-02)

The first demo run gave each draft only **one** false label, chosen per writer and
reviewer pair with a fixed seed (`label_seed: 20261101`). That mixed "told it is
another model" with "told it is the reviewer's own" and could not tell which wrong name
caused a result. Those 18 reviews are kept and reused: each one counts as the
false-label review for the model it actually named (it is saved under the old name
`L_<writer>_by_<reviewer>_false`). The 18 missing false-label reviews were added on
2026-11-04 under `L_<writer>_by_<reviewer>_false_<model named>`.

### Prompt construction

- `reviewer_lcb.txt` is not modified.
- The template `harness/prompts/reviewer_lcb_label_study.txt` adds an `{author_label}`
  line before `SUBMITTED SOLUTION:` and asks for an `<issues>` list before the
  `<solution>`.
- The label is filled in before the draft, so text inside a draft cannot collide with a
  placeholder.
- Every record stores the full reviewer prompt's SHA-256 and the template's SHA-256.

Tests (`tests/test_label_study.py`) enforce:

1. Prompts for different labels differ only in the label line.
2. True and false prompts differ only in the model name.
3. Every draft and reviewer gets a true, a no-label, and one false label for **each**
   wrong model, and never a false label naming the real author.
4. An older single-false-label record is reused only for the model it named.

**Known residual differences:**

- The no-label condition has no label line at all, so labeled vs. no label also
  measures whether a label line is present. The cleanest label contrasts are between
  labeled conditions (true vs. false, false → self vs. false → other). An optional
  neutral label ("written by an AI model") would isolate the presence effect.
- The no-label condition uses the label-study template, not the paper's exact reviewer
  prompt, because it also asks for an `<issues>` list.

### Self-identity

Each CLI tells its model what it is (Claude Code says Claude; Codex says it is an
OpenAI/Codex agent; Gemini CLI says Gemini). It is not verified that each reviewer
identifies with its label string, in particular that GPT-5.5 reads "GPT/Codex" as
itself. The review text is checked for mentions of the stated author.

## Metrics

For each reviewer × writer × label condition:

**Outcome of each review**, one of three:

- **Fixed:** the draft failed, and the returned code passes.
- **Changed, still fails** (on failing drafts) or **changed, still passes** (on passing
  drafts): the reviewer edited the code, but the outcome did not change.
- **Unchanged:** the returned code is the draft exactly (after normalization).
- **Regression:** the draft passed, and the returned code fails.

**Primary** (sensitive on every draft, not only failing ones):

- **Unchanged rate.**
- **Edit size:** changed-line count between draft and returned code.
- **Issues reported:** the number of items in the `<issues>` list.

**Secondary** (low power, see Limitations): fix rate on failing drafts, regression rate
on passing drafts. Invalid outputs (CLI error, timeout, parse failure) are reported
separately and not counted as regressions.

**Tests:**

- McNemar tests on the same drafts for the binary outcomes. **Each false label is
  tested separately** (`false_claude`, `false_gpt`, `false_gemini`), never pooled into
  one "false" group in the paired tests.
- Wilcoxon signed-rank tests on paired edit size (**TBD**, needs the full sample).
- Benjamini–Hochberg correction across all contrasts
  (`analysis/statistical_tests.py`).

**Noise floor:** the no-label condition is run twice on the same drafts (**TBD**). The
between-run flip rate is the baseline a label effect has to exceed.

## Side test: can reviewers recognize the author?

If a reviewer can tell who wrote a draft from its style, the no-label condition is not
truly blind, and a false label may be seen through.

- Prompt: a forced choice, "Which model wrote this solution: Claude, GPT or Gemini?",
  answered with one word and no review.
- Sample: about 40 drafts per writer, balanced, shown to each reviewer.
- Report: accuracy against the 1-in-3 chance level, a binomial test, and the confusion
  matrix (catches a reviewer that always answers the same model).
- Not built yet. If accuracy is well above chance, the no-label condition is read as
  "implicitly labeled" and the false labels as possibly detectable, and the results say
  so.

## Repository

| Path | Purpose |
|---|---|
| `experiments/configs/label_study.yaml` | Reviewers, template, seed |
| `experiments/configs/label_demo_drafts.yaml` | Draft manifest for the demo |
| `harness/prompts/reviewer_lcb_label_study.txt` | Labeled reviewer template |
| `experiments/run_label_study.py` | Builds the cells, runs reviewer-only calls with checkpointing and resume, grades the results |
| `analysis/label_study_metrics.py` | Summary tables and paired tests |
| `tests/test_label_study.py` | Prompt, label-assignment and metric tests |
| `results/raw/demo_labels/` | Demo records |
| `results/processed/label_study_demo_*.csv` | Demo tables |

Output tables:

- `_summary.csv`: per reviewer × writer × label (`true`, `false`, `none`), both false
  labels pooled.
- `_by_false_label.csv`: per reviewer × writer × label condition, with each false label
  separate (`true`, `false_claude`, `false_gpt`, `false_gemini`, `none`).
- `_self_vs_other.csv`: per reviewer × writer × relation (`self`, `other`, `none`).
- `_paired_tests.csv`: McNemar tests of each label condition against no label.

Records reuse the `TaskRecord` schema. The source draft is copied into
`writer_artifact`, and writer cost is 0, so it is not counted twice. `extra` holds
`source_record`, `draft_sha256`, `writer_family`, `reviewer_family`, `label_arm`,
`labeled_family`, `label_text`, `label_relation`, `draft_unchanged`, `diff_lines`,
`issue_count` and `issues`.

Cell order is shuffled across labels and reviewers, so rate limits or drift over time do
not line up with one label.

Run the demo with `bash scripts/run_demo.sh labels`. It resumes where it stopped.

## What stays untouched

- `results/raw/lcb_hard_full/` and `results/raw/lcb_medium_100/` are read-only inputs.
  The runner refuses a checkpoint path inside either directory.
- `experiments/run_experiment.py`, `harness/prompts/reviewer_lcb.txt`,
  `harness/prompts/writer_lcb.txt` and `experiments/configs/all_conditions.yaml` are
  unchanged.
- The paper's processed tables are not regenerated or overwritten.

## Scale and cost

At the demo's rates (Gemini about $0.26 and GPT-5.5 about $0.12 per review; Claude on
a subscription):

| Run | Drafts | Reviewer calls | Est. Gemini + GPT cost |
|---|---|---|---|
| Demo | 6 | 72 | ~$9 |
| Pilot: 10 tasks × 3 writers | 30 | 360 | ~$45 |
| Hard tier, 61 tasks × 3 writers | 183 | 2,196 | ~$280 |
| Pooled 116 tasks × 3 writers | 348 | 4,176 | ~$530 |

Each reviewer does a third of the calls. Claude's share (1,392 calls on the pooled set)
may hit subscription usage limits; the runner stops cleanly and resumes. Estimates are
re-checked against `experiments/configs/pricing.yaml` and the pilot's actual spend
before the full run.

Pilot tasks are hand-picked so that every writer has failing drafts in the sample.

## Plan and decision points

1. ~~Environment, runner, prompts, analysis, tests.~~ Done.
2. ~~Demo run (6 drafts).~~ Done 2026-11-02; extended to both false labels 2026-11-04.
3. **Style test.**
4. **Pilot.** Report cost, invalid outputs, the noise floor and any problems.
   *Decision point:* go or no-go on the hard tier, and whether to add a neutral label.
5. **Hard tier**, then optionally medium for the pooled 116.

## Limitations

- **Power:** few drafts fail for the strongest writers, so fix rates rest on few cases.
  This is why unchanged rate, edit size and issue count are primary.
- **One sample per cell:** reviewer outputs are stochastic. Without the repeated
  no-label run, label effects cannot be separated from run-to-run noise.
- **Environment drift:** CLI versions, and possibly model serving, have changed since
  the original runs, and Gemini is a preview model. Only comparisons within this study
  are valid.
- **Same transfer boundary as the paper** (see [SCOPE.md](SCOPE.md)): fixed prompts,
  high effort, a single static rewrite-only review, no tools, and single-file Python
  tasks scored by hidden tests.
- **What a label effect would mean:** it shows the reviewer conditions on stated
  authorship in this prompt format. It does not show how labels act in real workflows,
  where authorship usually comes through commit metadata or context rather than one
  line.

## Open decisions (TBD)

- [ ] Repeat the no-label condition in the pilot to measure the noise floor
- [ ] Add a neutral label ("written by an AI model")
- [ ] Scope after the pilot: hard tier only, or pooled 116
