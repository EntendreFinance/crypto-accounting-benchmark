from __future__ import annotations

from copy import deepcopy

from conftest import EXPECTED, MODEL_ANSWER

from cab.scoring import evaluate_answer, parse_answer


def test_parse_answer_accepts_fenced_json() -> None:
    parsed = parse_answer('Here is the answer:\n```json\n{"journalEntry":{"lines":[]}}\n```')
    assert parsed["journalEntry"]["lines"] == []


def test_expected_answer_scores_one_and_passes() -> None:
    result = evaluate_answer(MODEL_ANSWER, EXPECTED)
    assert result["score"] == 1.0
    assert result["passed"] is True
    assert result["exact_match"] is True
    assert result["failed_gates"] == []


def test_diagnostic_threshold_does_not_count_as_pass() -> None:
    answer = deepcopy(MODEL_ANSWER)
    answer["journalEntry"]["lines"][0]["amountBase"] = "999.99"
    answer["journalEntry"]["lines"][1]["amountBase"] = "999.99"
    result = evaluate_answer(answer, EXPECTED)
    assert result["score"] == 0.85
    assert result["threshold_met"] is True
    assert result["passed"] is False
    assert result["exact_match"] is False
    assert result["failed_gates"] == []


def test_full_score_still_requires_every_gate() -> None:
    answer = deepcopy(MODEL_ANSWER)
    answer["assetQuantity"] = "2.500"
    result = evaluate_answer(answer, EXPECTED)
    assert result["score"] == 1.0
    assert result["pass_eligible"] is False
    assert result["passed"] is False
    assert "ASSET_QUANTITY" in result["failed_gates"]


def test_balancing_is_enforced_per_currency() -> None:
    answer = deepcopy(MODEL_ANSWER)
    answer["journalEntry"]["lines"].extend(
        [
            {
                "ledgerAccountName": "X0001: Extra",
                "drCr": "Debit",
                "amountBase": "5.00",
                "currency": "CHF",
            },
            {
                "ledgerAccountName": "X0002: Extra",
                "drCr": "Credit",
                "amountBase": "5.00",
                "currency": "USD",
            },
        ]
    )
    result = evaluate_answer(answer, EXPECTED)
    assert result["facts"]["balanced"] is False
    assert "BALANCED_ENTRY" in result["failed_gates"]


def test_line_order_does_not_affect_exact_match() -> None:
    answer = deepcopy(MODEL_ANSWER)
    answer["journalEntry"]["lines"].reverse()
    assert evaluate_answer(answer, EXPECTED)["exact_match"] is True
