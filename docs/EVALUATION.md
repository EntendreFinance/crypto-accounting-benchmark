# Evaluation methodology

Crypto Accounting Bench measures whether a model can reconstruct the complete journal entry
recorded by an organization for a crypto-asset transaction. It is descriptive, not normative:
another defensible treatment can score as wrong when it differs from the recorded treatment.

## Model-visible and evaluator-only data

During inference the runner sends only `prompt.md`. It never sends or copies
`expected_answer.json` into a provider request. Evaluation happens after the response is saved.

The expected answers are publicly downloadable. That makes local scores reproducible, but it
also makes them self-reported educational results rather than proof that a participant avoided
the answer key.

## Public deterministic scorer

Every task contains a frozen weighted rubric whose criterion weights total 1.0. The public
scorer resolves those criteria mechanically from exact account, side, amount, currency,
quantity, and complete-entry comparisons.

This scorer is a reproducible lower bound on the rubric-guided judge used in the research
pipeline. A judge can credit a correct treatment expressed through a different but defensible
account; mechanical equality cannot. Report it as the **public deterministic lower-bound
scorer**.

## Pass@k

An attempt counts toward `Pass@k` only when both conditions hold on that same attempt:

1. the frozen rubric score is the full **100%**; and
2. every required gate passes.

The required gates are:

- parseable JSON with the required structure;
- balanced debits and credits within each currency;
- exact full-precision asset quantity;
- correct currency.

The `passThreshold` value stored with each rubric remains an attempt-level 85% diagnostic. It
does not define the paper's `Pass@k` metric.

Those four are the gates this scorer computes from the answer alone. The paper's protocol runs
seven, decomposed differently: parseable output, balance, the required journal structure,
quantity consistency, wallet-custody correctness, a check that the task's reference entry is
gradeable, and a material-accounting gate read from frozen judge verdicts. Currency is a
diagnostic there rather than a gate, and this scorer folds parseability and structure into one
check. A `Pass@k` from this scorer is therefore a lower bound on the paper's in the gates as
well as in the rubric.

## Metrics

- **Mean Score**: average weighted rubric score over every expected attempt. Missing or failed
  attempts stay in the denominator with score zero.
- **Best@k**: average of each task's strongest rubric score over `k` attempts.
- **Pass@k**: share of tasks with at least one full-score, gate-eligible attempt.
- **Exact@k**: share of tasks with at least one normalized complete-entry exact match.
- **Deciding account@k**: share of tasks where at least one attempt selects every deciding
  account.
- **Wallet account@k**, **Amount@k**, **Dr/Cr@k**, **Quantity@k**, and **Balanced@k**:
  component diagnostics over the same attempts.

Line order and exact-zero template lines do not affect matching. Account names, sides,
currencies, non-zero amounts, and quantities are otherwise exact.

## Three attempts

The paper evaluates three independent attempts per task. With 118 tasks, each evaluated model
therefore produces 354 attempts. The paper evaluates 12 models, for 4,248 evaluations in total.
Do not compare `@k` metrics from runs using different values of `k` as if they were identical.

## Leaderboard trust

`cab leaderboard` creates a local comparison and displays the dataset hash and attempt count
needed to identify comparable rows. Since the public answer key is available, it is not an
anti-cheating official leaderboard. A trusted public ranking requires a separately governed
private holdout and controlled scoring.
