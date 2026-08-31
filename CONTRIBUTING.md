# Contributing

Contributions that improve provider adapters, reproducibility, reporting, tests, and
documentation are welcome after publication authorization.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev,openai]"
pytest
ruff check .
```

Do not submit real customer records, private source data, credentials, or attempts to map
synthetic records back to real organizations or transactions.
