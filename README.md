# LLM Pair-Programming Benchmark

Benchmark writer/reviewer pairings across Claude Opus 4.7 and GPT-5.5 using the Claude Code CLI and Codex CLI, with reasoning effort pinned explicitly to `high` for both models.

| Condition | Writer | Reviewer |
|-----------|--------|----------|
| B1 | Claude Opus 4.7 | — |
| B2 | GPT-5.5 | — |
| C1 | Claude Opus 4.7 | GPT-5.5 |
| C2 | GPT-5.5 | Claude Opus 4.7 |
| C3 | Claude Opus 4.7 | Claude Opus 4.7 |
| C4 | GPT-5.5 | GPT-5.5 |

Benchmarks:
- Phase 1: LiveCodeBench
- Phase 2: SWE-bench Verified

## Requirements

- Python `3.10+`
- Claude Code CLI with `claude-opus-4-7` access
- Codex CLI with `gpt-5.5` access
- Docker for SWE-bench evaluation

The harness fails fast on older Python versions. Use `python3.10` (or any `3.10+` interpreter on your PATH) for all commands below.

## Setup

```bash
./setup.sh
```

The setup script:
- checks for Python `3.10+`
- installs Python requirements with `python3 -m pip`
- clones `external/livecodebench` and `external/swebench`
- prints the CLI versions it finds

Manual smoke tests:

```bash
claude --model claude-opus-4-7 --print --output-format json --no-session-persistence "Reply exactly with OK"
codex exec --model gpt-5.5 --skip-git-repo-check --json "Reply exactly with OK"
```

For the commands below, replace `python3.10` with whichever 3.10+ interpreter you want to use.

## Config Layout

- Shared writer/reviewer conditions live in [experiments/configs/all_conditions.yaml](/Users/shawn/Documents/llm-claude-codex-pair-coding-benchmark/experiments/configs/all_conditions.yaml)
- Benchmark-specific settings are auto-loaded from:
  - [experiments/configs/livecodebench.yaml](/Users/shawn/Documents/llm-claude-codex-pair-coding-benchmark/experiments/configs/livecodebench.yaml)
  - [experiments/configs/swebench.yaml](/Users/shawn/Documents/llm-claude-codex-pair-coding-benchmark/experiments/configs/swebench.yaml)

`experiments/run_experiment.py` runs a live preflight once per checkpoint directory unless `--skip-preflight` is passed.

All benchmark conditions pin `effort: high` explicitly for both writer and reviewer turns. Claude runs with `--effort high`, and Codex runs with `-c model_reasoning_effort="high"` so local CLI defaults do not leak into benchmark results.

Claude Code subprocesses set `CLAUDE_CODE_MAX_OUTPUT_TOKENS` to at least `200000` so long hard-task responses are not rejected by the CLI's lower default output cap. If the variable is already set higher in your shell, the harness preserves your explicit value.

## Phase 1: LiveCodeBench

Run the 10-task pilot:

```bash
python3.10 experiments/run_experiment.py \
  --benchmark livecodebench \
  --tasks experiments/configs/lcb_pilot_10.txt \
  --checkpoint results/raw/lcb_pilot/
```

If `experiments/configs/lcb_pilot_10.txt` does not exist yet, `run_experiment.py` will auto-sample 10 tasks and create it before starting.

If local LiveCodeBench task JSON files are not present under `external/livecodebench/data`, the runner will fetch the requested task rows from Hugging Face and print which `test*.jsonl` shard files it is scanning during `Loading benchmark tasks...`.

Pilot gates:

```bash
python3.10 analysis/compute_metrics.py --input results/raw/lcb_pilot/ --report
```

Revisit pilot checkpoints and outputs:

```bash
python3.10 analysis/show_results.py --input results/raw/lcb_pilot/
python3.10 analysis/show_results.py --input results/raw/lcb_pilot/ --task abc387_a
python3.10 analysis/show_results.py --input results/raw/lcb_pilot/ --condition C1_claude_writes_gpt55_reviews --task abc387_a --artifact
```

This refreshes `results/raw/lcb_pilot/index.json` and writes a task-level table to `results/processed/lcb_pilot/tasks.csv`.

Full run:

```bash
python3.10 experiments/run_experiment.py \
  --benchmark livecodebench \
  --tasks experiments/configs/lcb_100.txt \
  --checkpoint results/raw/lcb_full/
```

If `--tasks` is omitted entirely, the runner defaults to `experiments/configs/lcb_100.txt` for LiveCodeBench and auto-generates it when missing.

Hard-only run:

```bash
python3.10 experiments/run_experiment.py \
  --benchmark livecodebench \
  --lcb-difficulty hard \
  --checkpoint results/raw/lcb_hard_100/
```

This defaults to `experiments/configs/lcb_hard_100.txt` and auto-generates a hard-only task list when missing.

LiveCodeBench evaluation now uses the upstream custom-output format in a condition-level batch step.

## Phase 2: SWE-bench Verified

Collect model outputs only:

```bash
python3.10 experiments/run_experiment.py \
  --benchmark swebench \
  --tasks experiments/configs/sweb_pilot_10.txt \
  --checkpoint results/raw/sweb_pilot/ \
  --skip-eval
```

Missing SWE-bench task files are auto-generated the same way, based on the count encoded in the filename such as `sweb_pilot_10.txt` or `sweb_50.txt`.

Run Docker evaluation separately:

```bash
python3.10 harness/benchmarks/swebench/batch_eval.py \
  --inputs results/raw/sweb_pilot/ \
  --output results/raw/sweb_pilot_eval/
```

The batch evaluator emits official prediction objects with `instance_id`, `model_name_or_path`, and `model_patch`, then writes evaluated record copies under `results/raw/.../records/`.

## Resume Flow

Usage and rate limits no longer pause the run. The runner waits indefinitely with capped exponential backoff:

```text
60s → 120s → 300s → 600s → 900s → 900s ...
```

The terminal prints the blocked CLI/model, next retry number, and wait duration. `PAUSED` is reserved for explicit future manual-pause flows, not normal usage-limit handling.

If a run is interrupted for another reason and a `PAUSED` file exists, resume with confirmation:

Resume with confirmation:

```bash
python3.10 experiments/run_experiment.py --resume results/raw/lcb_full/
```

Non-interactive resume:

```bash
python3.10 experiments/run_experiment.py --resume results/raw/lcb_full/ --confirm-resume
```

On resume, the runner now automatically reruns checkpoint records that previously ended in `cli_error=true` or `timed_out=true`. Successful inference records are still reused, even if a later batch-evaluation step has not populated `passed` yet.

## Analysis

Metrics:

```bash
python3.10 analysis/compute_metrics.py \
  --input results/raw/lcb_full/ \
  --output results/processed/lcb_metrics.csv \
  --json-output results/processed/lcb_metrics.json \
  --report
```

Browse a raw run without opening JSON files manually:

```bash
python3.10 analysis/show_results.py --input results/raw/lcb_full/
python3.10 analysis/show_results.py --input results/raw/lcb_full/ --task <task_id>
python3.10 analysis/show_results.py --input results/raw/lcb_full/ --condition <condition_id> --task <task_id> --artifact
```

Pairwise tests and SPD bootstrap CIs:

```bash
python3.10 analysis/statistical_tests.py \
  --input results/raw/lcb_full/ \
  --output results/processed/lcb_stats.csv \
  --spd-output results/processed/lcb_spd_ci.csv
```

Asymmetry analysis:

```bash
python3.10 analysis/asymmetry_analysis.py \
  --input results/raw/lcb_full/ \
  --output results/processed/lcb_asymmetry.csv
```

Plots:

```bash
python3.10 analysis/plots.py \
  --metrics results/processed/lcb_metrics.csv \
  --output results/processed/figures/
```

## Tests

Run the local unit suite:

```bash
python3.10 -m unittest discover -s tests -v
```

These tests cover:
- CLI parsing and pause handling
- `<solution>` parsing and confidence-note extraction
- config merge and checkpoint idempotency helpers
- LiveCodeBench and SWE-bench payload helpers

## Repository Notes

- Per-task result JSONs now include raw stdout/stderr, prompt hashes, CLI versions, timestamps, parse metadata, and writer confidence metadata.
- `parse_rate` is measured from whether the evaluated turn actually returned `<solution>` tags, not whether fallback extraction succeeded.
- `experiments/run_experiment.py` is the only entrypoint that enforces Python `3.10+`; the unit tests are intentionally lightweight enough to run on this machine’s older interpreter.
