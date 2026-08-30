# Scope, Estimand, and Transfer Boundary

This page states precisely what the study measures, what it does not measure, and how
far the result is meant to travel. It exists because the headline phrasing — Claude
review of Codex drafts helps, the reverse does not — is easy to read as a general
rule about which vendor should review which, and the released evidence supports a
narrower claim than that.

## What the six conditions estimate

Each condition is a **whole pipeline**, sampled independently per task:

| Paper label | Pipeline |
|-------------|----------|
| A | Claude writes, no review |
| O | Codex writes, no review |
| AO | Claude writes, Codex reviews and emits the final program |
| OA | Codex writes, Claude reviews and emits the final program |
| AA | Claude writes, Claude reviews |
| OO | Codex writes, Codex reviews |

A comparison such as OA versus O is therefore a contrast between two stochastic
pipelines run on the same tasks. It is **not** an estimate of what a reviewer does to
a given draft: the reviewed arm and the solo arm each sampled their own writer output,
and those drafts are almost never the same program. On the released hard slice the two
arms shared an identical writer artifact for only a handful of the 82 attempted tasks.

Two consequences follow:

- Writer sampling variance and the review step are not separable in the
  condition-level contrast. Baseline strength and review direction move together.
- The `cross_condition_regression_rate` column in `metrics_*.csv` counts tasks where
  the reviewed pipeline failed and the separately sampled solo pipeline passed. That
  is a pipeline-level transition. It is not evidence that a reviewer broke a
  particular draft.

## What is identified on the same candidate

`analysis/review_transitions.py` reports the quantity the condition-level table
cannot. Every record stores the writer draft its reviewer actually received, so
scoring that draft (`analysis/evaluate_writer_artifacts.py`) yields a genuine
before/after pair on one fixed candidate:

- **reviewer fix**: the draft failed, the post-review program passed;
- **reviewer regression**: the draft passed, the post-review program failed;
- kept-pass and kept-fail for the unchanged outcomes.

These are attributable to the review step. They are still conditional on the draft
distribution the writer produced, and they are not a randomized comparison: nothing
here randomizes the same frozen draft into review and no-review arms.

## Statistical caveats that belong with the headline

- The direct AO versus OA contrast does **not** survive multiplicity correction on the
  pooled 116-task complete case (`p_BH = .1444`). The two cross-model orderings are
  not shown to be statistically separable as standalone conditions on this sample.
- The results that do survive correction are writer-conditional: with Codex as writer,
  adding a reviewer helps (OA vs O, `p_BH ≈ .001`; OO vs O, `p_BH ≈ .022`).
- 116 paired tasks is a bounded controlled sample, not a leaderboard-scale evaluation.

The defensible statement is writer-conditional — *if Codex writes, review helps; if
Claude writes, handing the draft to Codex did not help in this setting* — rather than
a general ordering of the two vendors as reviewers.

## Transfer boundary

The measurement holds for this configuration and is not established outside it:

- **Models**: one model pair and one version each (Claude Opus 4.7, Codex GPT-5.5).
- **Prompts**: one fixed writer prompt and one fixed reviewer prompt.
- **Effort**: the vendors' high reasoning-effort setting for every turn.
- **Review intervention**: a single static pass in which the reviewer must emit a
  replacement program. It cannot report findings for a human to accept or reject, and
  nothing preserves the draft when the reviewer's rewrite is worse.
- **Tools**: the reviewer cannot run tests, read a repository, or use any tool.
- **Tasks**: self-contained single-file Python competitive-programming problems with
  hidden tests, hard and medium LiveCodeBench tiers.
- **Outcome**: hidden-test pass/fail of the final program only. Nothing about
  security, maintainability, review quality, escaped defects, or human review time.

Repository-scale bug fixing, build systems, multi-file review, tool-using reviewers,
and findings-only review workflows are all outside what these numbers measure. A
review pass that reports findings for an owner to adjudicate is a different
intervention from one that silently replaces the draft, and the direction of its
effect is not predicted by this study.

## Planned follow-up

The design that would identify the reviewer's causal contribution, and which this
artifact does not yet implement:

1. Freeze each writer candidate by digest and score it before any review.
2. Randomize that same candidate to arms: no review, findings-only review with owner
   adjudication, and mandatory-rewrite review (the arm studied here).
3. Sample multiple writer seeds per task, so writer variance can be separated from
   reviewer contribution rather than absorbed into the condition contrast.
4. Replicate across repository-scale task classes with realistic tooling, and report
   outcomes beyond hidden-test pass rate: tests, security findings, rework, escaped
   defects, latency, cost, and human adjudication time.

## Related pages

- [RESULTS.md](RESULTS.md) — the tables and how to read them.
- [ARTIFACT.md](ARTIFACT.md) — what the released records contain.
- [REPRODUCIBILITY.md](REPRODUCIBILITY.md) — how to recompute everything.
