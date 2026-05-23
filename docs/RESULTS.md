# Results Summary

The paper reports two complementary views:

- **Complete-case analysis:** tasks for which all six conditions produced valid evaluated answers.
- **Reliability-inclusive analysis:** all attempted tasks, with invalid outputs treated as failures.

## Complete-Case Metrics

Complete-case analysis uses 61 shared hard LiveCodeBench tasks.

| Paper label | Repository condition | Passed | Pass rate | Cost/task | Latency/task | Score/$ | Regression rate |
|-------------|----------------------|--------|-----------|-----------|--------------|---------|-----------------|
| A | `B1_claude_solo` | 53/61 | 86.9% | $0.282 | 108.5s | 3.08 | -- |
| O | `B2_gpt55_solo` | 36/61 | 59.0% | $0.242 | 54.3s | 2.44 | -- |
| AO | `C1_claude_writes_gpt55_reviews` | 46/61 | 75.4% | $0.404 | 127.0s | 1.87 | 16.4% |
| OA | `C2_gpt55_writes_claude_reviews` | 53/61 | 86.9% | $0.496 | 145.7s | 1.75 | 6.6% |
| AA | `C3_claude_writes_claude_reviews` | 55/61 | 90.2% | $0.469 | 167.7s | 1.92 | 1.6% |
| OO | `C4_gpt55_writes_gpt55_reviews` | 49/61 | 80.3% | $0.352 | 91.6s | 2.28 | 8.2% |

Main complete-case takeaways:

- Claude review of Codex drafts improved pass rate from 59.0% to 86.9%.
- Codex review of Claude drafts reduced pass rate from 86.9% to 75.4%.
- Claude review of Claude drafts had the highest complete-case pass rate, but with higher cost and latency than Claude solo.
- Codex review of Codex drafts was the cheapest reviewed condition and substantially improved over Codex solo.

## Reliability-Inclusive View

The frozen run attempted 82 hard LiveCodeBench tasks. Invalid outputs include CLI errors, timeouts, parse failures, budget failures, or empty final artifacts.

| Paper label | Repository condition | Evaluated | Passed | Invalid | Success rate (`passed / 82`) | Valid rate |
|-------------|----------------------|-----------|--------|---------|-------------------------------|------------|
| A | `B1_claude_solo` | 65 | 55 | 17 | 67.1% | 79.3% |
| O | `B2_gpt55_solo` | 78 | 44 | 4 | 53.7% | 95.1% |
| AO | `C1_claude_writes_gpt55_reviews` | 67 | 48 | 15 | 58.5% | 81.7% |
| OA | `C2_gpt55_writes_claude_reviews` | 76 | 62 | 6 | 75.6% | 92.7% |
| AA | `C3_claude_writes_claude_reviews` | 67 | 60 | 15 | 73.2% | 81.7% |
| OO | `C4_gpt55_writes_gpt55_reviews` | 80 | 60 | 2 | 73.2% | 97.6% |

Reliability-inclusive analysis changes the deployment ranking: Codex output reviewed by Claude has the strongest overall success rate, while Codex self-review has the strongest validity rate among reviewed conditions.

## Pairwise Tests

Selected complete-case McNemar results:

| Comparison | First only | Second only | p-value | BH-adjusted p-value |
|------------|------------|-------------|---------|---------------------|
| OA vs O | 21 | 4 | 0.000911 | 0.004555 |
| OO vs O | 18 | 5 | 0.010622 | 0.035157 |
| AO vs A | 3 | 10 | 0.092285 | 0.197448 |
| AO vs OA | 4 | 11 | 0.118469 | 0.197448 |
| AA vs A | 3 | 1 | 0.625000 | 0.721154 |
| AA vs AO | 10 | 1 | 0.011719 | 0.035157 |

Full tables are in:

- `results/processed/stats_complete_case.csv`
- `results/processed/spd_ci_complete_case.csv`
- `results/processed/stats_all.csv`
- `results/processed/spd_ci_all.csv`

## Recompute These Results

```bash
bash scripts/reproduce_paper_tables.sh
```

The recomputation uses token counts in raw records and pricing assumptions from `experiments/configs/pricing.yaml`.
