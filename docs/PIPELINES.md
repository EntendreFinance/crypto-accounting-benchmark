# Model pipelines

## Quickest route: an OpenAI-compatible endpoint

```yaml
name: my-model
provider: openai_compatible
model: provider/model-id
base_url: https://provider.example/v1
api_key_env: PROVIDER_API_KEY
api: chat_completions
system_prompt: prompts/system.md
max_tokens: 8192
max_tokens_parameter: max_tokens
temperature: 0
json_mode: true
timeout_seconds: 600
retries: 5
```

Install the optional SDK and run:

```bash
pip install -e ".[openai]"
cab benchmark --pipeline pipelines/my-model.yaml --attempts 3 --max-concurrent 8
```

## OpenAI Responses API

Set `provider: openai` and `api: responses`. `reasoning_effort` is forwarded only when it is
present. Use a model id and reasoning setting supported by your account; the repository does
not hard-code a current-model recommendation.

Provider-specific request fields may be placed in `extra_body`. They are part of the run
identity and are recorded in `run.json`, so never put credentials, tokens, private headers,
or other secrets there. Secrets belong only in the environment variable named by
`api_key_env`.

## Any model through a command

The command provider is the universal adapter. It gives the combined system and task prompt
to the process on stdin. The process must write one answer JSON object to stdout and return
exit code zero.

```yaml
name: local-model
provider: command
model: my-local-model
command: [python, adapters/my_model.py]
system_prompt: prompts/system.md
timeout_seconds: 900
retries: 1
```

This works with a local inference server, a vendor CLI, a shell-free Python adapter, or an
internal gateway. The runner launches the argument list directly; it does not use a shell.

### Text encoding

The prompt is written to the child process as UTF-8, and its stdout is read back as UTF-8.
Task prompts contain non-ASCII characters -- em dashes and non-breaking spaces -- so an
adapter that decodes stdin with a locale default corrupts them without raising an error, and
the model then answers a subtly different prompt.

The runner sets `PYTHONIOENCODING=utf-8` and `PYTHONUTF8=1` in the child environment, so a
Python adapter can call `sys.stdin.read()` directly. An adapter in another language must
decode stdin as UTF-8 itself. On Windows this matters in practice: the default there is the
console code page, not UTF-8.

## Concurrency

`--max-concurrent N` controls the number of task-attempt calls in flight:

```bash
# Safe starting point
cab run --pipeline pipelines/my-model.yaml --attempts 3 --max-concurrent 2

# Increase after observing the provider's rate and concurrency limits
cab run --pipeline pipelines/my-model.yaml --attempts 3 --max-concurrent 8
```

Start with 2-4. Increase gradually while watching rate limits, latency, and spend. The runner
retries transient timeouts, connection errors, HTTP 429 responses, and 5xx responses with
exponential backoff. Provider-side quotas still apply.

Concurrency changes throughput, not the task or score. It is recorded in `run.json`.

## Resume behavior

Repeat the identical command to resume. Successful attempts are skipped only when the
dataset, complete non-secret pipeline identity, and effective prompt hashes all match.
Changing the system prompt, `extra_body`, model settings, or command arguments invalidates
reuse. Failed attempts are retried into a new immutable `retry_N` artifact. Existing answers
are never overwritten.

If the pipeline, dataset, task set, or attempt plan changes, choose a new run name:

```bash
cab benchmark --pipeline pipelines/my-model-v2.yaml --run-name my-model-v2
```
