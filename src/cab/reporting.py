from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment

from .utils import load_json

_ENV = Environment(autoescape=True)
_ENV.filters["pct"] = lambda value: f"{100 * float(value):.1f}%"
_ENV.filters["score"] = lambda value: f"{100 * float(value):.1f}"

_STYLE = """
:root { color-scheme: dark; --bg:#07111f; --panel:#0d1b2c; --line:#213552;
  --text:#e8f0fb; --muted:#92a7c2; --blue:#58a6ff; --green:#42d392;
  --red:#ff7b72; --amber:#f2cc60; }
* { box-sizing:border-box; } body { margin:0; font:15px/1.5 Inter,ui-sans-serif,system-ui,
  -apple-system,Segoe UI,sans-serif; color:var(--text); background:var(--bg); }
main { width:min(1180px,calc(100% - 32px)); margin:0 auto; padding:48px 0 72px; }
h1 { margin:0; font-size:clamp(30px,5vw,52px); letter-spacing:-.035em; }
h2 { margin:38px 0 14px; font-size:24px; } p { color:var(--muted); }
.eyebrow { color:var(--blue); font-weight:700; text-transform:uppercase; letter-spacing:.12em; }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:28px 0; }
.card,.panel,details { border:1px solid var(--line); background:var(--panel); border-radius:14px; }
.card { padding:18px; } .card strong { display:block; font-size:27px; letter-spacing:-.03em; }
.card span,.meta { color:var(--muted); font-size:13px; }
.panel { padding:20px; overflow:auto; } table { width:100%; border-collapse:collapse; }
th,td { padding:11px 12px; text-align:left; border-bottom:1px solid var(--line); white-space:nowrap; }
th { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.06em; }
tr:last-child td { border-bottom:0; } a { color:var(--blue); text-decoration:none; }
.good { color:var(--green); } .bad { color:var(--red); } .warn { color:var(--amber); }
.bar { height:8px; border-radius:99px; background:#142641; overflow:hidden; margin-top:8px; }
.bar i { display:block; height:100%; background:linear-gradient(90deg,var(--blue),var(--green)); }
details { margin:10px 0; padding:0 16px; } summary { cursor:pointer; padding:14px 0; font-weight:700; }
.attempts { display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:10px; padding:0 0 16px; }
.attempt { border:1px solid var(--line); border-radius:10px; padding:12px; }
code { color:#c9d8f2; } footer { margin-top:42px; color:var(--muted); font-size:13px; }
@media(max-width:700px){ main{width:min(100% - 20px,1180px);padding-top:28px} th,td{padding:9px 8px} }
"""

_REPORT_TEMPLATE = _ENV.from_string(
    """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ s.run_name }} · Crypto Accounting Bench</title><style>{{ style }}</style></head>
<body><main><div class="eyebrow">Crypto Accounting Bench</div>
<h1>{{ s.pipeline.model }}</h1>
<p>Run <code>{{ s.run_name }}</code> · {{ s.tasks }} tasks · {{ s.attempts_per_task }} attempts per task ·
public deterministic scorer · self-reported educational result</p>
<div class="cards">
  {% for label,key in [('Mean Score','mean_score'),('Best@k','best_at_k'),('Pass@k','pass_at_k'),('Exact@k','exact_at_k'),('Deciding account@k','deciding_account_at_k'),('Amount@k','amount_at_k')] %}
  <div class="card"><strong>{{ s[key]|pct }}</strong><span>{{ label }}</span><div class="bar"><i style="width:{{ s[key]|score }}%"></i></div></div>
  {% endfor %}
</div>
<h2>Run identity</h2><div class="panel"><table><tbody>
<tr><th>Provider</th><td>{{ s.pipeline.provider }}</td><th>Model</th><td>{{ s.pipeline.model }}</td></tr>
<tr><th>Dataset commit</th><td><code>{{ (s.dataset.resolved_revision or 'local')[:16] }}…</code></td><th>Dataset SHA-256</th><td><code>{{ s.dataset.dataset_sha256[:16] }}…</code></td></tr>
<tr><th>Completed</th><td>{{ s.attempts_completed }}/{{ s.attempts_expected }}</td><th>Generated</th><td>{{ s.completed_at }}</td></tr>
</tbody></table></div>
<h2>Performance by rubric family</h2><div class="panel"><table><thead><tr><th>Family</th><th>Tasks</th><th>Best@k</th><th>Pass@k</th><th>Exact@k</th></tr></thead><tbody>
{% for family,row in s.by_family.items() %}<tr><td><code>{{ family }}</code></td><td>{{ row.tasks }}</td><td>{{ row.best_at_k|pct }}</td><td>{{ row.pass_at_k|pct }}</td><td>{{ row.exact_at_k|pct }}</td></tr>{% endfor %}
</tbody></table></div>
<h2>Task details</h2>
{% for task in s.per_task %}<details><summary>{{ task.task_id }} · {{ task.family }} ·
<span class="{{ 'good' if task.passed_at_k else 'bad' }}">{{ 'PASS' if task.passed_at_k else 'FAILED' }}</span> · best {{ task.best_score|pct }}</summary>
<div class="attempts">{% for a in task.attempts %}<div class="attempt"><strong>Attempt {{ a.attempt }}</strong><br>
<span class="{{ 'good' if a.passed else 'bad' }}">{{ 'PASS' if a.passed else 'FAILED' }}</span> · {{ a.score|pct }}
{% if a.error %}<p class="bad"><code>{{ a.error }}</code></p>{% endif %}
{% if a.failed_gates %}<p>Gates: <code>{{ a.failed_gates|join(', ') }}</code></p>{% endif %}
</div>{% endfor %}</div></details>{% endfor %}
<footer>The public answer key makes this a self-reported educational result, not an anti-cheating
official leaderboard submission. Scores reflect reproduction of the recorded entry, not general
accounting advice. Report the scorer as <code>{{ s.score_source }}</code>.</footer>
</main></body></html>"""
)

_LEADERBOARD_TEMPLATE = _ENV.from_string(
    """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Leaderboard · Crypto Accounting Bench</title><style>{{ style }}</style></head>
<body><main><div class="eyebrow">Crypto Accounting Bench</div><h1>Leaderboard</h1>
<p>{{ rows|length }} run{{ '' if rows|length == 1 else 's' }} scored on this machine with the
public deterministic scorer. The answer key is public, so treat these as your own numbers, not
as a ranking anyone else has verified.</p>
{% if comparable is false %}
<div class="panel"><p class="warn" style="margin:0">These runs do not all use the same dataset
snapshot or attempt count, so the rows are not directly comparable. Mismatches are marked below.</p></div>
{% endif %}
<div class="panel"><table><thead><tr><th>#</th><th>Model</th><th>Mean</th><th>Pass@k</th>
<th>Exact@k</th><th>Tasks × k</th><th></th></tr></thead><tbody>
{% for row in rows %}<tr>
<td>{{ loop.index }}</td>
<td><strong>{{ row.pipeline.model }}</strong><br><span class="meta">{{ row.run_name }} · {{ row.pipeline.provider }}</span></td>
<td>{{ row.mean_score|pct }}<div class="bar"><i style="width:{{ row.mean_score|score }}%"></i></div></td>
<td>{{ row.pass_at_k|pct }}</td>
<td>{{ row.exact_at_k|pct }}</td>
<td>{{ row.tasks }} × {{ row.attempts_per_task }}{% if not row.comparable %}
<br><span class="warn meta">different snapshot</span>{% endif %}</td>
<td><a href="{{ row.report_path }}">Report</a></td>
</tr>{% endfor %}
{% if not rows %}<tr><td colspan="7">No scored runs yet. Run <code>cab benchmark --pipeline
pipelines/my-model.yaml</code> first.</td></tr>{% endif %}
</tbody></table></div>
{% if rows %}<footer>Dataset <code>{{ baseline_sha[:12] }}</code>{% if baseline_revision %} at
commit <code>{{ baseline_revision[:12] }}</code>{% endif %}. Built from
<code>output/*/summary.json</code>; re-run <code>cab leaderboard</code> after any new run. Nothing
is uploaded.</footer>{% endif %}
</main></body></html>"""
)


def generate_report(run_dir: str | Path) -> Path:
    run_path = Path(run_dir)
    summary = load_json(run_path / "summary.json")
    output = run_path / "report.html"
    output.write_text(_REPORT_TEMPLATE.render(s=summary, style=_STYLE), encoding="utf-8")
    return output


def generate_leaderboard(output_dir: str | Path = "output") -> Path:
    root = Path(output_dir)
    rows: list[dict[str, Any]] = []
    for summary_path in sorted(root.glob("*/summary.json")):
        try:
            row = load_json(summary_path)
        except (OSError, json.JSONDecodeError):
            continue
        row["report_path"] = f"{summary_path.parent.name}/report.html"
        rows.append(row)
    rows.sort(key=lambda row: (-float(row.get("mean_score", 0)), row.get("run_name", "")))

    # Rows are only comparable against the same dataset snapshot and attempt count.
    # The top row sets the baseline; anything different is marked rather than hidden.
    def signature(row: dict[str, Any]) -> tuple[str, Any]:
        return (
            str(row.get("dataset", {}).get("dataset_sha256", "")),
            row.get("attempts_per_task"),
        )

    baseline = signature(rows[0]) if rows else ("", None)
    for row in rows:
        row["comparable"] = signature(row) == baseline
    comparable = all(row["comparable"] for row in rows)

    output = root / "leaderboard.html"
    root.mkdir(parents=True, exist_ok=True)
    output.write_text(
        _LEADERBOARD_TEMPLATE.render(
            rows=rows,
            style=_STYLE,
            comparable=comparable,
            baseline_sha=baseline[0],
            baseline_revision=(
                rows[0].get("dataset", {}).get("resolved_revision") if rows else None
            ),
        ),
        encoding="utf-8",
    )
    return output
