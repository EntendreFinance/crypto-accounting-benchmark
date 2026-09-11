from __future__ import annotations

import argparse
import json
from typing import Any

from dotenv import load_dotenv

from .config import discover_pipelines, load_pipeline
from .dataset import download_dataset, task_directories, verify_dataset
from .evaluation import evaluate_run
from .reporting import generate_leaderboard, generate_report
from .runner import run_pipeline
from .scoring import evaluate_answer
from .utils import load_json


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _add_data_dir(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-dir", default="data")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cab", description="Run and evaluate Crypto Accounting Bench"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    dataset = sub.add_parser("dataset", help="download and verify the public dataset")
    dataset_sub = dataset.add_subparsers(dest="dataset_command", required=True)
    download = dataset_sub.add_parser("download", help="download from Hugging Face")
    _add_data_dir(download)
    download.add_argument("--repo-id", default="Entendre/Crypto-Accounting-Bench")
    download.add_argument("--revision", default="main")
    verify = dataset_sub.add_parser("verify", help="validate counts, hashes, rubrics, and accounts")
    _add_data_dir(verify)

    pipelines = sub.add_parser("pipelines", help="inspect model pipeline files")
    pipeline_sub = pipelines.add_subparsers(dest="pipeline_command", required=True)
    listing = pipeline_sub.add_parser("list")
    listing.add_argument("--directory", default="pipelines")
    validate = pipeline_sub.add_parser("validate")
    validate.add_argument("pipeline")

    run = sub.add_parser("run", help="run model inference; existing successful attempts resume")
    run.add_argument("--pipeline", required=True)
    _add_data_dir(run)
    run.add_argument("--output-dir", default="output")
    run.add_argument("--run-name")
    run.add_argument("--attempts", type=int, default=3)
    run.add_argument("--max-concurrent", type=int, default=1)
    run.add_argument("--limit", type=int)
    run.add_argument("--task", action="append", dest="task_ids")

    evaluate = sub.add_parser("evaluate", help="score a completed or partial run")
    evaluate.add_argument("--run-dir", required=True)
    _add_data_dir(evaluate)

    report = sub.add_parser("report", help="generate a self-contained HTML run report")
    report.add_argument("--run-dir", required=True)

    leaderboard = sub.add_parser("leaderboard", help="rank every evaluated run")
    leaderboard.add_argument("--output-dir", default="output")

    benchmark = sub.add_parser("benchmark", help="run, evaluate, report, and update leaderboard")
    benchmark.add_argument("--pipeline", required=True)
    _add_data_dir(benchmark)
    benchmark.add_argument("--output-dir", default="output")
    benchmark.add_argument("--run-name")
    benchmark.add_argument("--attempts", type=int, default=3)
    benchmark.add_argument("--max-concurrent", type=int, default=1)
    benchmark.add_argument("--limit", type=int)
    benchmark.add_argument("--task", action="append", dest="task_ids")

    self_test = sub.add_parser("self-test", help="prove every expected answer scores 1.0")
    _add_data_dir(self_test)
    return parser


def _run_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return run_pipeline(
        load_pipeline(args.pipeline),
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        run_name=args.run_name,
        attempts=args.attempts,
        max_concurrent=args.max_concurrent,
        limit=args.limit,
        task_ids=args.task_ids,
    )


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "dataset":
        if args.dataset_command == "download":
            path = download_dataset(args.data_dir, args.repo_id, args.revision)
            print(f"Dataset downloaded to {path}")
            _print(verify_dataset(path))
        else:
            _print(verify_dataset(args.data_dir))
        return 0

    if args.command == "pipelines":
        if args.pipeline_command == "validate":
            _print(load_pipeline(args.pipeline).public_dict())
            return 0
        for path, item in discover_pipelines(args.directory):
            if isinstance(item, Exception):
                print(f"INVALID  {path}: {item}")
            else:
                print(f"{item.name:<24} {item.provider:<20} {item.model:<30} {path}")
        return 0

    if args.command == "run":
        _print(_run_from_args(args))
        return 0

    if args.command == "evaluate":
        summary = evaluate_run(args.run_dir, args.data_dir)
        _print({key: value for key, value in summary.items() if key != "per_task"})
        return 0

    if args.command == "report":
        print(generate_report(args.run_dir).resolve())
        return 0

    if args.command == "leaderboard":
        print(generate_leaderboard(args.output_dir).resolve())
        return 0

    if args.command == "benchmark":
        result = _run_from_args(args)
        summary = evaluate_run(result["run_dir"], args.data_dir)
        report_path = generate_report(result["run_dir"])
        leaderboard_path = generate_leaderboard(args.output_dir)
        _print(
            {
                "run": result,
                "summary": {key: value for key, value in summary.items() if key != "per_task"},
                "report": str(report_path.resolve()),
                "leaderboard": str(leaderboard_path.resolve()),
            }
        )
        return 0

    if args.command == "self-test":
        failures = []
        for task_dir in task_directories(args.data_dir):
            expected = load_json(task_dir / "expected_answer.json")
            answer = {
                "journalEntry": expected["journalEntry"],
                "assetQuantity": expected["assetQuantity"],
            }
            evaluation = evaluate_answer(answer, expected)
            if evaluation["score"] != 1.0 or not evaluation["passed"]:
                failures.append({"task_id": task_dir.name, **evaluation})
        result = {"tasks": len(task_directories(args.data_dir)), "failures": failures}
        _print(result)
        return 1 if failures else 0

    parser.error("unknown command")
    return 2
