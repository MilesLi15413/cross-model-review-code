# Limited Demo Run: Gemini, Authorship Labels, and Help Requests

**Date:** 2026-11-01 to 2026-11-02. **Branch:** `limited-demo-run`.

This was a small demonstration, not the full experiment. It answers three questions:

1. Does Gemini work in the existing writer → reviewer workflow?
2. Is the authorship-label test built, and does it run end to end?
3. Does the harness detect and count a model's requests for human help?

All three answers are **yes**. The samples are far too small to support any scientific
conclusion about the models: they show the tools work, not what the full experiment
would find.

Nothing in the paper's frozen results (`results/raw/` from the original runs) was changed.

## Setup

| Model | Exact ID | Accessed through | Reasoning effort |
|---|---|---|---|
| Claude | `claude-opus-4-7` | Claude Code 2.1.316, Pro subscription | high |
| GPT | `gpt-5.5` | Codex CLI 0.163.0, prepaid OpenAI API key | high |
| Gemini | `gemini-3.1-pro-preview` | Gemini CLI 0.65.0, prepaid Gemini API key | thinking level HIGH |

Problems come from LiveCodeBench, the same benchmark as the paper (AtCoder problems
plus LeetCode-style problems). All code was graded with the paper's grader
(`analysis/lcb_eval_runner.py`). Every saved record includes the CLI version, model ID,
effort setting and a hash of the exact prompt.

## 1. Gemini in the workflow

Gemini was added as a writer, a reviewer, and a solo baseline. That makes six new
conditions: B3 (Gemini alone), C5–C8 (Gemini paired with Claude or GPT in either role)
and C9 (Gemini reviewing Gemini). The paper's six original conditions were not changed.

**Sample:** 2 problems, 12 model calls.

- **Hard problem abc392_f:** run under B3 and C5–C9. Every condition failed it. The
  paper's six original conditions failed it too, so this says the problem is hard, not
  that Gemini is broken.
- **Problem 3801:** run with Gemini alone (B3). Gemini passed.

**What worked:** all 12 calls succeeded on the first try, with no errors and no
unreadable answers. Gemini ran at HIGH thinking with no tools available, and made 0
tool calls.

**Observed (anecdotal):** in C9, Gemini returned its own draft unchanged. In four other
pairings the reviewer changed the code but did not fix it.

## 2. Authorship-label test

**The question it is built for:** does a reviewer treat the same code differently
depending on who it is told wrote it?

**Design:** we reused 6 existing drafts, one passing and one failing from each writer.
They cover 3 different problems.

| Writer | Failing draft | Passing draft |
|---|---|---|
| Claude | abc394_f | 3801 |
| GPT-5.5 | 3801 | abc394_f |
| Gemini | abc392_f | 3801 |

Each of the 3 reviewers reviewed each of the 6 drafts 3 times. The code was identical
each time; only one line of the prompt changed:

- **True label:** names the real author.
- **False label:** names a different model.
- **No label:** names no author.

3 reviewers × 6 drafts × 3 labels = **54 reviews**. Each reviewer also had to list the
problems it found inside `<issues>` tags.

**What worked:** all 54 reviews were valid, with 0 parse failures, 0 errors and 0
missing issue lists. Every measurement was produced: unchanged rate, size of the edit,
number of issues, fix rate on failing drafts, regression rate on passing drafts, and a
McNemar test comparing each label with the no-label version.

**Results.** Each cell covers one failing draft, reviewed 3 times:

| Reviewer → failing draft by | Claude | GPT-5.5 | Gemini |
|---|---|---|---|
| **Claude** | fixed 3/3 | fixed with true and no label; left unchanged with the false label | fixed 0/3 |
| **GPT-5.5** | fixed only with the true label | fixed 3/3 | fixed 0/3 |
| **Gemini** | fixed with true and no label; not with the false label | fixed 3/3 | returned unchanged 3/3 |

- No reviewer broke a passing draft (0 regressions).
- Gemini returned all 6 of its own drafts unchanged, under every label.
- All 54 p-values were 1.0.

**How to read this:** the sample cannot show whether bias exists. Each comparison
rests on a single draft, so a different result under one label could be ordinary
run-to-run variation. Twice, a reviewer fixed a draft under the true label but not under
the false one. That is worth testing in a full run, not a finding.

## 3. Human-help-request tracking

**Design:** each model wrote code on its own for 5 problems (3 hard, 2 medium), so 15
calls. The prompt told it to write `<help_request type="...">reason</help_request>`
whenever it was unsure or needed help, using one of four types:
`unclear_instructions`, `missing_information`, `wants_execution` or `other`. It was told
nobody would answer, and to still deliver a solution.

The harness counts:

- tagged requests, by type,
- untagged requests, meaning plain-English phrases such as "could you clarify",
- broken tags,
- replies that contain no code.

**Main sample result:** 0 requests from any model on all 15 problems. Every reply
contained code. Pass rates were Claude 3/5, GPT-5.5 2/5 and Gemini 2/5.

**Positive control:** to check that real requests are caught, each model got one
problem with its key rule removed. The problem says a "good" pair is defined "in the
attached figure", and there is no figure.

| Model | What it wrote (tagged `missing_information`) |
|---|---|
| Claude | "The 'condition described in the attached figure' is not provided, so I cannot know what makes a pair 'good'." |
| GPT-5.5 | "The attached figure defining a good pair is unavailable, so I assume the condition is \|i−j\| = A_i + A_j." |
| Gemini | "The problem statement mentions an attached figure that describes the condition for a good pair, but the figure is missing." |

All three requests were caught and labeled correctly. There were no broken tags, and
every model still gave code.

**How to read this:** the tracker works. On clear benchmark problems the models do not
ask for help, so in a full study help requests may be rare unless the problems are
designed to need them.

## Limitations and caveats

- **Tiny samples:** results show that the tools work, not how the models behave.
- **Newer CLI versions:** the paper used Claude Code 2.1.50 and Codex CLI
  0.125.0-alpha.3; this demo used 2.1.316 and 0.163.0. Results are not strictly
  comparable with the paper's.
- **Different reviewer prompt:** the "no label" reviews use the new label-study
  prompt, which also asks for an `<issues>` list. That is not the paper's exact
  reviewer prompt.
- **Gemini is a preview model,** and its behavior may change.
- **Gemini's tools:** the Gemini CLI's built-in instructions still mention tools,
  even though all tools are switched off. In earlier testing Gemini once tried a tool
  call, which failed as malformed. In every recorded demo run it made 0 tool calls.
- **Claude cost:** Claude ran on a Pro subscription, so it cost nothing. Its costs at
  API prices are recorded for comparison.
- **A bug found and fixed during the run:** the "usage limit" detector looked for the
  text "429" (the error code for too many requests) in successful replies too. A token
  count such as 14,298 contains that text, and it stopped a run early. Successful
  replies are no longer checked. A test covers this, and the affected review was rerun.

## Cost

| Part | Gemini | GPT-5.5 | Claude |
|---|---|---|---|
| Gemini sample | $1.36 | $0.19 | $0 |
| Authorship test | $4.73 | $2.13 | $0 |
| Help-request sample | $0.71 | $0.51 | $0 |
| Positive control | $0.03 | $0.74 | $0 |
| **Total (about)** | **$6.95** | **$3.75** | **$0** |

The GPT total includes setup test calls.

## Files

- **Configs:** `experiments/configs/three_model_conditions.yaml`,
  `label_study.yaml`, `label_demo_drafts.yaml`, `help_request_conditions.yaml`,
  `help_check_problem.txt`.
- **Prompts:** `harness/prompts/reviewer_lcb_label_study.txt`,
  `harness/prompts/writer_lcb_help.txt`.
- **Runners:** `experiments/run_experiment.py`, `experiments/run_label_study.py`,
  `experiments/run_help_check.py` and `scripts/run_demo.sh`. The demo script runs one
  stage at a time: `bash scripts/run_demo.sh gemini|labels|help`.
- **Raw results:** `results/raw/demo_gemini*`, `results/raw/demo_labels`,
  `results/raw/demo_help`, `results/raw/demo_help_check`.
- **Tables:** `results/processed/demo_gemini_metrics.csv`,
  `label_study_demo_{summary,self_vs_other,paired_tests}.csv`,
  `help_requests_demo_{summary,detail}.csv`, `help_check_demo.csv`.

## Scaling up

- **Authorship test:** a full run would use many drafts per writer, for example drafts
  from the paper's 116 problems. With 3 reviewers × 3 labels, that is about 9 reviews
  per draft, so several thousand calls. At this demo's rates that means roughly
  hundreds of dollars for Gemini and GPT. It should be estimated precisely before
  running.
- **Help requests:** the same scaling applies. Adding problems that deliberately need
  help would make the counts informative.

---

## For Miles: questions your professor may ask

**"So is there authorship bias?"**
We don't know yet. The demo shows the test runs correctly. With one failing draft per
reviewer–writer pair, no result could be statistically significant. A full run is needed.

**"Why only 2 drafts per writer?"**
The goal was to prove the pipeline works for a few dollars. Each draft costs 9 reviews,
so the cost grows quickly with the number of drafts.

**"Why did nobody ask for help?"**
The benchmark problems are fully specified, so there was nothing to ask about. When we
removed a key rule, all three models asked, and the tracker caught every request. So
the tracker works; the problems just don't trigger requests.

**"How do you know the label is the only thing that changes?"**
The prompt template is the same for all three versions except for the one sentence
naming the author. Each record stores a hash of the exact prompt, so you can check it.

**"Are these results comparable with the paper?"**
Not directly. The CLI versions are newer, GPT now runs through the API, and the
label-study reviewer prompt differs from the paper's.

**"Why did Gemini fail abc392_f everywhere?"**
Every model failed that problem in the paper too. It is a hard problem, not a
Gemini-specific failure.

**"Does Gemini get the same setup as the others?"**
Yes, as far as the CLIs allow. It runs at high reasoning, with no tools, the same
prompts, and the same grader.

**"What would the full study cost?"**
Hundreds of dollars for Gemini and GPT at these rates, depending on how many problems
are used. Claude can run on the subscription but may hit usage limits.
