# Crypto Accounting Bench

Can a language model read one crypto-asset transaction and reproduce the **journal entry an
organization actually recorded** for it?

This repository is the toolkit that answers that question for *your* model. You point it at a
model, it runs 118 tasks, scores the answers deterministically, and writes an HTML report plus a
local leaderboard. It has no opinions of its own about accounting: the ground truth is what a
real ledger recorded, and the scorer only checks whether the model reproduced it.

- **This repository** — the runner, the scorer, the reports, the tests.
- **[The dataset on Hugging Face](https://huggingface.co/datasets/Entendre/Crypto-Accounting-Bench)** —
  118 tasks with prompts, expected answers, rubrics, and a manifest. Downloaded by one command
  below; nothing from it is stored in this repository.

---

## Table of contents

1. [What the model is asked to do](#1-what-the-model-is-asked-to-do)
2. [Install it](#2-install-it)
3. [Point it at a model](#3-point-it-at-a-model)
4. [Run the benchmark](#4-run-the-benchmark)
5. [Read the results](#5-read-the-results)
6. [How scoring works](#6-how-scoring-works)
7. [Reproducibility](#7-reproducibility)
8. [Command reference](#8-command-reference)
9. [Troubleshooting](#9-troubleshooting)
10. [What this benchmark does not measure](#10-what-this-benchmark-does-not-measure)

---

## 1. What the model is asked to do

Each task gives the model two things and nothing else:

1. **The transaction evidence** — what moved, on which chain, in which direction, at which
   timestamp, with the base-currency valuation, plus any linked records, subledger state, and
   tax-lot evidence that existed at the time.
2. **The organization's own chart of accounts** — often several hundred accounts, with their
   exact names. The answer must use those names, character for character.

The model returns one JSON object:

```json
{
  "journalEntry": {
    "lines": [
      { "ledgerAccountName": "A0177: Wallet — Treasury", "drCr": "Debit",
        "amountBase": "12436231.71", "currency": "USD" },
      { "ledgerAccountName": "I0022: Contract Receipts", "drCr": "Credit",
        "amountBase": "12436231.71", "currency": "USD" }
    ]
  },
  "assetQuantity": "58071869.8487894582"
}
```

Every part is graded: which accounts, which side of each account, the base-currency amount, the
currency, the full-precision asset quantity, and whether the set of lines is complete — no
missing lines and no invented ones.

**Why this is hard, and why it is fair.** There is no universally correct journal entry for a
crypto transaction. Two organizations receiving the identical transfer will book it differently,
and both are defensible. So the benchmark does not grade against a textbook. It grades against
what *this* organization recorded, using *this* organization's accounts — a ground truth that
existed in a ledger before the benchmark did. The model's job is inference from evidence, not
agreement with an opinion.

The consequence is worth stating plainly: a genuinely defensible alternative treatment scores as
wrong when it differs from the recorded one. That is a deliberate trade for a ground truth nobody
had to invent.

---

## 2. Install it

You need Git and Python 3.10 or newer. No API key yet.

```bash
git clone https://github.com/EntendreFinance/crypto-accounting-benchmark.git
cd crypto-accounting-benchmark

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[openai]"
```

Now get the dataset and prove the installation is sound:

```bash
cab dataset download     # ~500 files into data/, which stays untracked
cab dataset verify       # task count, ids, checksums, rubric weights, chart membership
cab self-test            # every expected answer must score 100% and clear every gate
```

`cab self-test` is the one that matters. It feeds each task's own recorded answer through the
scorer and asserts a perfect score. If it passes, the dataset and the scorer agree, and any score
below 100% afterwards belongs to the model rather than to the harness:

```json
{ "tasks": 118, "failures": [] }
```

---

## 3. Point it at a model

A model is described by one YAML file in `pipelines/`. Three adapters cover most cases; copy the
closest example and edit it.

**An OpenAI-compatible endpoint** — OpenRouter, Together, vLLM, Ollama, anything speaking
`/chat/completions`. This is the shortest path for most models:

```yaml
name: my-model
provider: openai_compatible
model: vendor/model-id
base_url: https://openrouter.ai/api/v1
api_key_env: OPENROUTER_API_KEY    # the variable NAME, never the key itself
api: chat_completions
system_prompt: prompts/system.md
max_tokens: 8192
temperature: 0
json_mode: true
timeout_seconds: 600
retries: 5
```

**The official OpenAI SDK** — copy `pipelines/openai-responses.example.yaml`, which sets
`provider: openai`, `api: responses`, and `reasoning_effort`.

**Anything else at all** — `provider: command` runs a program you write. The runner sends the
prompt on stdin and reads one JSON object from stdout, so a local model, a research prototype, or
a shell script all work the same way. Start from `examples/model_command.py`.

Secrets are read only from the environment variable named by `api_key_env`. A key is never read
from the YAML, never written into run metadata, and never appears in a report.

Check the file before spending tokens:

```bash
export OPENROUTER_API_KEY="..."        # PowerShell: $env:OPENROUTER_API_KEY="..."
cab pipelines validate pipelines/my-model.yaml
```

That prints the exact identity that will be recorded with your results, with no secret in it. Full
field reference: [docs/PIPELINES.md](docs/PIPELINES.md).

---

## 4. Run the benchmark

Try three tasks first. This costs almost nothing and catches a broken adapter immediately:

```bash
cab run --pipeline pipelines/my-model.yaml --attempts 1 --limit 3
```

Then the real thing — 118 tasks, three attempts each, four requests in flight:

```bash
cab benchmark --pipeline pipelines/my-model.yaml --attempts 3 --max-concurrent 4
```

`benchmark` is just the four steps in order: `run`, `evaluate`, `report`, `leaderboard`. Run them
separately whenever you want to re-score or re-render without calling the model again.

**Why three attempts.** One sample cannot separate a model that does not know the answer from a
model that knows it and sampled badly. Three attempts let `Pass@3` and `Best@3` say which.

**Interrupting is safe.** Every attempt is written to disk as it completes. Re-run the same command
and finished attempts are reused; only the missing ones are called. A saved attempt is reused only
when the dataset, the pipeline, and the effective prompt all still hash the same, so a result
produced under different settings can never silently join a resumed run.

---

## 5. Read the results

```text
output/my-model/
├── run.json          # what ran: dataset commit, pipeline identity, task ids, prompt hashes
├── answers/          # every raw response and parsed answer, one file per attempt
├── evaluation.json   # per-task, per-attempt scores, failed gates, criterion detail
├── summary.json      # the headline metrics
└── report.html       # all of the above, readable
output/leaderboard.html   # every scored run on this machine, ranked
```

Open `report.html` for one model and `leaderboard.html` to compare models. The leaderboard is
rebuilt from `output/*/summary.json`, so it picks up new runs automatically and never uploads
anything.

The headline metrics, over `k` attempts per task:

| Metric | What it means |
|---|---|
| **Mean Score** | Average rubric score across every expected attempt. Missing and failed attempts count as zero, so an unreliable model cannot hide behind its good runs. The primary metric, and the one the leaderboard is ordered by. |
| **Best@k** | Each task's strongest attempt, averaged. The model's ceiling. |
| **Pass@k** | Share of tasks where at least one attempt earned the full rubric score *and* cleared every required gate. The most demanding of the three. |
| **Exact@k** | Share of tasks where an attempt matched the complete recorded entry exactly, after normalization. |
| **Deciding account@k** | Share of tasks where an attempt found every key non-wallet account — the accounts that carry the accounting judgment. |
| **Wallet account@k** | Share of tasks where an attempt found every expected wallet or counter account. |
| **Amount@k**, **Dr/Cr@k**, **Quantity@k**, **Balanced@k** | Component diagnostics. These tell you *how* a model failed. |

The diagnostics are where the value is. A model with high `Deciding account@k` and low `Amount@k`
understands the treatment and fumbles arithmetic. The reverse means it computes cleanly and books
to the wrong account. Those two failures need completely different fixes.

`report.html` also breaks every metric down by rubric family — `TRANSFER`, `INCOME_EXPENSE`,
`INTERCOMPANY`, `SWAP`, `FEE` and `REALIZED_GAIN_LOSS`, whose `_A` and `_B` labels carry the
same criteria and weights — and lists every task, so you can open a specific failure and see
which gate it missed.

---

## 6. How scoring works

Each task ships with a frozen weighted rubric whose criterion weights total exactly 1.0. The
scorer resolves each criterion mechanically, by exact comparison of account names, sides, amounts,
currencies, quantities, and the complete set of lines. No model sits in the scoring path, so the
same answers always produce the same score.

Four **gates** apply on top of the weights. An attempt that misses any of them cannot pass, no
matter how much rubric weight it collected:

| Gate | Requirement |
|---|---|
| `PARSEABLE_REQUIRED_STRUCTURE` | The response contains one JSON object with journal-entry lines. |
| `BALANCED_ENTRY` | Debits equal credits, per currency. |
| `ASSET_QUANTITY` | The asset quantity matches at full precision. |
| `CURRENCY` | Each line carries the correct currency. |

Two honest limits on these numbers:

**This scorer is a lower bound.** Mechanical equality cannot credit a correct treatment expressed
through a different but defensible account, which a rubric-guided judge can. The four gates above
are also a subset: the paper's protocol runs seven ([docs/EVALUATION.md](docs/EVALUATION.md)), so
a `Pass@k` from here is a lower bound in the gates as well as in the rubric. Report it as the
*public deterministic lower-bound scorer*, and expect a judge to score the same answers slightly
higher.

**The answer key is public.** It has to be, for anyone to reproduce a score. That makes your
numbers self-reported educational results, not a ranking that proves anything about a model you
did not run yourself. A trustworthy public ranking needs a private holdout, governed separately.

Full definitions: [docs/EVALUATION.md](docs/EVALUATION.md). How the dataset itself was designed,
and which of those decisions transfer to a different benchmark:
[docs/METHODOLOGY.md](docs/METHODOLOGY.md).

---

## 7. Reproducibility

During inference the runner sends the model exactly one thing: the task's `prompt.md`, prefixed by
your system prompt. It never sends, quotes, or copies `expected_answer.json`. Scoring happens
afterwards, from files on disk.

Every run records what produced it — dataset repository, requested revision, resolved Hugging Face
commit, a SHA-256 over all task prompts, inputs and expected answers, the complete non-secret
pipeline identity, and the prompt hashes. To pin a snapshot, pass the commit the downloader
printed:

```bash
cab dataset download --revision <commit-sha>
```

When comparing two models, hold the dataset commit, the system prompt, the attempt count, and the
sampling configuration constant. The leaderboard checks the first and the third for you, and marks
any row that came from a different snapshot rather than quietly ranking it alongside the others.
Details: [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md).

---

## 8. Command reference

```text
cab dataset download [--repo-id ID] [--revision REV] [--data-dir DIR]
cab dataset verify [--data-dir DIR]
cab self-test [--data-dir DIR]

cab pipelines list [--directory DIR]
cab pipelines validate PIPELINE.yaml

cab run --pipeline FILE [--attempts K] [--max-concurrent N]
        [--run-name NAME] [--limit N] [--task TASK_ID ...]
cab evaluate --run-dir DIR [--data-dir DIR]
cab report --run-dir DIR
cab leaderboard [--output-dir DIR]
cab benchmark --pipeline FILE [the same run options]
```

Repository layout:

```text
data/        populated by `cab dataset download`; untracked
pipelines/   your model configurations
prompts/     the system instruction sent with every task
output/      answers, scores, and reports; untracked
src/cab/     runner, scorer, reporting, CLI
docs/        evaluation, pipelines, methodology, reproducibility
tests/       offline unit and end-to-end tests
```

Development setup and contribution rules: [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 9. Troubleshooting

**Every attempt fails with a JSON parse error.** The model is wrapping the answer in prose. Set
`json_mode: true`, lower `temperature`, or raise `max_tokens` — a truncated response is
unparseable JSON. `output/<run>/answers/*/attempt_1.json` keeps the raw text, so read what the
model actually said before changing anything.

**Windows: the download fails with a file-not-found error partway through.** The dataset paths
crossed the 260-character limit. Clone closer to the drive root, such as `C:\cab`, or pass a
shorter `--data-dir`.

**A `command` adapter written in something other than Python.** Decode stdin as UTF-8 explicitly.
Task prompts contain em dashes and non-breaking spaces, and a locale default such as Windows
cp1252 corrupts them without raising an error, so the model silently sees a different prompt.
Python adapters need no special handling: the runner sets `PYTHONIOENCODING` for the child.

**Rate limits or timeouts.** Lower `--max-concurrent`, raise `retries` and `timeout_seconds`, then
re-run the same command. Completed attempts are reused, so a resumed run only calls what is
missing.

**`cab run` refuses to start, citing a different pipeline or dataset.** That output directory
belongs to a different configuration, and the resume guard is doing its job. Pass
`--run-name my-model-v2` for a fresh one.

**Slow, and the prompts are large.** Each prompt carries a full chart of accounts, so prompts run
to tens of thousands of tokens. Raise `--max-concurrent` if your provider allows it, and stay on
`--limit` while you are still adjusting settings.

---

## 10. What this benchmark does not measure

It does not test market prediction, trading, tax preparation, audit, month-end close, or authority
to post entries in production. A high score means a model reproduced recorded journal entries on
118 historical tasks. It is not deployment approval, and nothing here is accounting advice.

The dataset records are transformed derivatives of production accounting evidence. Names,
identifiers, addresses, assets, chains, amounts, quantities, prices, and timestamps are synthetic;
the accounting relationships between them are real, which is the only reason the tasks are
solvable. Do not read a record as a factual statement about any real party, and do not attempt
re-identification or public-chain correlation. Automated privacy checks reduce disclosure risk but
cannot prove anonymity against someone holding the source ledger.

To report a privacy or security concern, see [SECURITY.md](SECURITY.md).

## License

The code in this repository is licensed under the [Apache License 2.0](LICENSE).

The dataset is licensed separately, under
[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/): share and adapt with
attribution, for non-commercial purposes. The two licenses are independent, so a permitted
use of this runner is not by itself a permitted use of the data.

## Citation

The paper is not on a preprint server, so no DOI or arXiv identifier is asserted. Cite the
paper and the dataset:

```
Kareem Khattab, Omar Khattab, and Mohamed Ibrahem.
Crypto Accounting Bench: Evaluating Frontier and Open-Weight Models on
Crypto-Asset Accounting Tasks. Entendre Finance, September 2026.
```

```bibtex
@misc{crypto_accounting_bench_2026,
  title        = {Crypto Accounting Bench: Evaluating Frontier and Open-Weight
                  Models on Crypto-Asset Accounting Tasks},
  author       = {Khattab, Kareem and Khattab, Omar and Ibrahem, Mohamed},
  year         = {2026},
  month        = sep,
  institution  = {Entendre Finance},
  note         = {Public benchmark dataset and evaluation set},
  howpublished = {\url{https://huggingface.co/datasets/Entendre/Crypto-Accounting-Bench}}
}
```

Record both the Hugging Face dataset revision and the Git commit of this runner, and name the
scorer that produced any result you report.
