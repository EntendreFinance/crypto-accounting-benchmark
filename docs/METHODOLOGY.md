# How this benchmark was built

This document is the part of Crypto Accounting Bench that generalizes. The rest of
this repository shows you how to *run* an evaluation; this file records the decisions
that produced the dataset, why each one was made, and which of them we would keep if
we started a different benchmark tomorrow.

The generation machinery itself is not public: it reads a production accounting
database. What is transferable is not the code, it is the sequence of decisions.

## 1. Choose a task whose ground truth already exists

The first and most consequential decision was to measure **reproduction of a recorded
treatment**, not correctness in the abstract.

For a crypto transaction there is no single right journal entry. Two organizations
receiving the identical on-chain transfer will book it differently, and both are
defensible. A benchmark that grades against "the correct treatment" therefore grades
against the benchmark author's opinion, and its ceiling is that opinion's quality.

So the target became: *the entry this organization actually recorded, chosen from this
organization's own chart of accounts*. That ground truth already existed in a ledger
before the benchmark did. Nobody had to invent it, and no reviewer has to agree with it
for the measurement to be well-defined.

The cost is stated openly in the dataset card: a different-but-defensible treatment
scores as wrong. That is not a defect to be apologized for, it is the price of a
ground truth that was not authored by the grader.

**Transferable rule.** Prefer a target that some real process already decided over one
your team has to adjudicate. If you must adjudicate, expect your inter-rater agreement
to become the benchmark's ceiling.

## 2. Make the task hard in the intended dimension only

Each task hands the model the transaction evidence and the organization's **complete**
chart of accounts, a median of 569 accounts per task. The model must name accounts
exactly as they appear in that chart.

This concentrates the difficulty on the accounting judgment - which account does this
movement belong in - rather than on recall of an account list the model has never seen.
It also removes an entire class of false failure: a model cannot lose points for
inventing a plausible account name when the acceptable set is supplied in the prompt.

The rest of the entry is deliberately mechanical: two decimal places on base-currency
amounts, full precision on asset quantity, debits equal credits. Those are checkable
without judgment, which is what lets the deterministic scorer in this repository exist
at all.

**Transferable rule.** Separate the reasoning you are measuring from the recall you are
not. Supply the second in the prompt.

## 3. Transform for privacy without destroying the signal

The public dataset is a transformed derivative. Every organization, legal entity,
person, counterparty, venue, bank, account name, account number, address, transaction
identifier, asset ticker, chain, amount, quantity and timestamp is replaced by a
synthetic value, consistently across the whole dataset.

The rule that made this workable: **replace identity, preserve class**.

A synthetic ticker still declares what kind of asset it is, because the asset class is
what the accounting turns on. The dataset documents its own vocabulary - `st` is a
liquid-staking receipt, `w` is wrapped, `br` is bridged, `gv` is a vault share - so a
model can still reason about the economics of a staking receipt without any real ticker
being present. Synthetic chains likewise keep their structural class: independent L1,
EVM rollup, UTXO model, settlement chain.

Consistency matters as much as replacement. The same real entity maps to the same
synthetic value everywhere, so relationships across tasks survive: records sharing a
transaction group still share it, intercompany counterparties still resolve to the same
synthetic legal entity, and tax-lot rows still reconcile against the transaction they
belong to.

Two things follow, both stated on the dataset card. Records must not be read as factual
statements about any real party, and readers must not attempt correlation against
public chain data. Technical transformation is a privacy control, not a publication
authorization - those are separate decisions, made by different people.

**Transferable rule.** Decide explicitly which properties are load-bearing for the
reasoning and which are merely identifying. Randomize the second class consistently,
and write the mapping rules down where users can audit them.

## 4. Admit tasks by rule, and record what you rejected

Not every ledger entry makes a usable task. Candidates were pulled from real postings
and then filtered. The filters, in the order they mattered:

**No unresolvable ambiguity.** If the evidence in the task supported two treatments
equally well, the task was dropped rather than shipped with an arbitrary answer. A task
whose answer cannot be reached from what the model can see is not measuring reasoning,
it is measuring luck. Every task in this dataset is marked
`inferable_from_visible_evidence` for exactly this reason: the ones that were not
inferable did not survive admission.

**No near-duplicate decisions.** Tasks were grouped by the accounting decision they
actually test - the deciding non-wallet account plus the entry shape - and the number
admitted per group was capped. Without a cap, the easiest and most numerous pattern in a
production ledger dominates the dataset, and a model that learns one convention scores
well on a benchmark that looks large. This cap, not the size of the source ledger, is
what limited the dataset to 118 tasks. Expanding the dataset meant finding new *kinds*
of decisions, not more rows.

**Evidence must support the deciding line.** The hard half of every task is
`keyLineAccounts`, the non-wallet account that encodes the treatment. A candidate was
admitted only when some signal in the visible evidence supported that account: a
counterparty the organization's records resolve to a known legal entity, a contract and
function pair, a recurrence profile, tax-lot rows showing cost basis relieved. Tasks
where the deciding account was knowable only from outside the record were rejected.

The consequence is visible in the dataset statistics and is worth reading as a feature
rather than an accident: coverage is uneven. Organizations contribute unequal numbers
of tasks, and rubric families range from 37 tasks down to 5. That is what a rule-based
admission process produces from real data. The alternative - synthesizing filler tasks to balance
the table - would have made the distribution prettier and the benchmark weaker.

**Transferable rule.** Write admission rules before you scale, cap by the decision under
test rather than by surface form, and publish the resulting imbalance instead of hiding
it.

## 5. Freeze a weighted rubric per task

Every task carries its own rubric: ordered binary criteria with weights summing to 1.0,
frozen with the task and shipped inside `expected_answer.json`.

Per-task rather than global, because the criteria that matter differ by transaction. A
swap needs both legs and the disposal; a fee needs the expense account and the fee
quantity; a realized gain or loss needs the gain account and a correct basis relief. A
single global rubric would either omit these or carry criteria that are vacuous for most
tasks.

Weighted rather than all-or-nothing, because partial credit is genuinely informative
here: a model that picks the right treatment account but the wrong side has failed
differently from one that picked an unrelated account, and a benchmark that reports both
as zero tells you less.

Frozen rather than computed at scoring time, because a rubric that can be regenerated is
a rubric that can be quietly retuned after seeing results. Freezing it and hashing the
task is what makes a published score checkable by someone who did not run it.

The headline `Pass@k` metric requires one attempt with the full 100% rubric score
**and** every required gate. The stored 85% threshold remains a diagnostic for individual
attempts; it does not define `Pass@k`. The gate list is in
[EVALUATION.md](EVALUATION.md). Gates prevent structurally invalid or unbalanced entries
from counting as successful even when their accounting rubric score is strong.

**Transferable rule.** Weight for diagnosis, gate for validity, and freeze both before
you look at model outputs.

## 6. Decide what the model may see, once, and enforce it mechanically

`prompt.md` is the entire model-visible surface. `expected_answer.json` is
evaluator-only, and the runner never places it in a provider request.

Leakage control here follows a **disclose, do not suppress** rule. Source values that a
real accountant would see are passed through verbatim even when they are unhelpful or
messy. `transactionType` is the clearest case: it is the label the source application
displays, it is an open vocabulary, it is sometimes absent or `UNKNOWN`, and the dataset
card states plainly that it is not a reliable guide to the treatment. Deleting it would
have made the task cleaner and less real. Silently correcting it would have leaked the
answer.

The inverse error is worth naming too: a field that *is* the answer must not appear in
the evidence under a different name. Admission checked for this, which is why each task
records which signals support the answer in `reasoningEvidence` - a reviewer can see
exactly what the answer was supposed to be derivable from.

**Transferable rule.** Give the model the messy real input and document the mess. Never
tidy an input in a direction that narrows the answer.

## 7. Ship a scorer weaker than your own, and say so

The upstream research pipeline scores rubric criteria with an LLM judge. This public
dataset ships a deterministic scorer that resolves the same weighted structure from
exact account, side, amount, currency and quantity comparisons.

These do not produce identical numbers, and the documentation says so: the deterministic
scorer is a **faithful lower bound**. A judge can credit a correct treatment expressed
through a different-but-defensible account in the same chart; mechanical equality
cannot. Published comparisons must name which scorer produced them.

Shipping the weaker scorer publicly is deliberate. It is fully reproducible, requires no
model access, costs nothing, and cannot drift between runs or between users. A
judge-based score that nobody outside the project can reproduce is not a public
benchmark result, it is a claim about one.

Both entry points self-test the same way: score the expected answers and require 1.0.
That single check catches most scorer regressions, because any normalization bug severe
enough to matter will usually break exact reproduction of the answer key first.

**Transferable rule.** If your internal metric is not reproducible by a stranger, publish
a reproducible one alongside it, state the relationship, and let readers cite the one
they can verify.

## 8. Validate before freezing, not after publishing

Before a task was admitted it had to survive automated checks:

- the entry balances, per currency;
- every account named exists in that task's chart of accounts, character for character;
- the rubric's weights sum to 1.0 and its criteria are all resolvable;
- the expected answer scores 1.0 under the shipped scorer;
- amounts carry exactly two decimals and quantities are unrounded;
- no identity-bearing value survived the transformation.

The last two produced the most defects in practice. Decimal handling in particular is
worth designing early: base amounts are fixed at two decimals while asset quantities
must stay full-precision, and a single default rounding context applied to both will
silently corrupt quantities in a way no balance check detects.

Identity and integrity are recorded so a result can be audited later. `manifest.json`
carries per-file checksums, the runner records the dataset SHA-256 in `run.json`, and
every stored answer records the SHA-256 of the exact prompt that produced it. A resumed
run reuses a saved attempt only when both hashes match. This makes the exact dataset and prompt identity independently checkable.

**Transferable rule.** Every property you assert in your dataset card should have a check
that fails when it stops being true.

## 9. Report the limits in the same document as the results

The dataset card's limitations section names the imbalance, the synthetic transformation,
the single-convention answer key, the name-based grading, and the lower-bound scorer -
in specific, quantified terms.

This is a research-quality decision, not a modesty ritual. A reviewer who finds an
unstated limitation discounts everything else in the document. A reviewer who finds it
already stated, with a number attached, reads the rest as careful work.

## A checklist for your own benchmark

1. Is your ground truth something a real process already decided, or something your team
   adjudicated? If the latter, measure and publish your agreement rate.
2. Have you supplied in the prompt everything the task should not be testing recall of?
3. Which fields are load-bearing for the reasoning, and which are merely identifying? Can
   you defend the split in writing?
4. What is your admission rule, and what does the distribution look like after you apply
   it? Publish that distribution.
5. Are you capping by surface form or by the decision under test?
6. Is your rubric frozen and hashed before you see model outputs?
7. Do you have validity gates separate from partial-credit scoring?
8. Can a stranger reproduce your headline number with no model access? If not, what can
   they reproduce?
9. Does every claim on your dataset card have a check behind it?
10. Which limitation would most embarrass you if a reviewer found it first? Write that one
    down yourself.

## What we would do differently

**Balance earlier.** The per-decision cap was introduced after a large tranche of tasks
already existed, so the imbalance was inherited rather than designed. Applying the cap
from the first task would have produced a smaller but more evenly distributed dataset at
the same effort.

**Grade by account identity, not account name.** Answers are matched on
`ledgerAccountName`, so an equally valid account under a different name in the same chart
scores as wrong. Grading against a stable account identifier, with the name as display
only, would remove a class of false negatives that has nothing to do with accounting
skill.

**Record solvability at finer grain.** Every dataset task is
`inferable_from_visible_evidence`, which is a true statement and a coarse one. Some tasks
turn on a single decisive signal and others require combining several, and the dataset
cannot currently tell you which is which. That distinction is the most useful thing a
difficulty label could carry, and it should have been captured at admission time.
