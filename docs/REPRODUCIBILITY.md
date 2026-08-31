# Reproducibility and run identity

Each `output/<run>/run.json` records:

- complete non-secret pipeline identity, including system-prompt SHA-256, system role,
  `extra_body`, retry policy, and command adapter arguments;
- model and provider;
- dataset repository, requested revision, resolved Hugging Face commit, and a SHA-256 digest
  over all task prompts, inputs, and expected answers;
- exact task ids, attempt count, concurrency, and creation time.

Each answer artifact records the pipeline hash, task-prompt hash, and effective-prompt hash.
A saved answer is reusable only when the dataset, pipeline, and effective-prompt hashes match.
This prevents a result produced with different inputs or settings from silently entering a
resumed run.

## Fair comparisons

Keep these constant when comparing models:

- resolved dataset commit and dataset SHA-256;
- system prompt and task prompts;
- scorer identity;
- attempt count;
- sampling and reasoning configuration.

Report missing and failed attempts as zero rather than dropping them. Keep raw answer artifacts
and `run.json` with the result. Never edit a model answer after generation.

## Output layout

```text
output/
  my-model/
    run.json
    answers/task_0001/attempt_1.json
    evaluations/task_0001/attempt_1.json
    summary.json
    report.html
  leaderboard.html
```

The `output/` directory is ignored by Git. Review artifacts before sharing them.
