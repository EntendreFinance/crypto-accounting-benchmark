# Pipeline files

One YAML file describes one model configuration. Copy an example, remove `.example` from
the filename, set the model id, and validate it:

```bash
cp pipelines/openai-responses.example.yaml pipelines/my-model.yaml
cab pipelines validate pipelines/my-model.yaml
```

Secrets never belong in YAML. Put API keys in environment variables or a local `.env`
file, which Git ignores.

Supported providers:

- `openai`: OpenAI Responses or Chat Completions through the official SDK.
- `openai_compatible`: any compatible endpoint with a custom `base_url`.
- `command`: any local or remote model CLI that reads a prompt from stdin and prints one
  JSON answer to stdout.

See [the pipeline guide](../docs/PIPELINES.md) for every field and concurrency guidance.
