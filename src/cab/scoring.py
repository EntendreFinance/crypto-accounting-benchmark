from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

SCORER_ID = "cab-public-deterministic"


def parse_answer(text: str) -> dict[str, Any]:
    """Extract the first complete JSON object from a model response."""
    value = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", value, re.IGNORECASE | re.DOTALL)
    if fence:
        value = fence.group(1).strip()
    start = value.find("{")
    if start < 0:
        raise ValueError("no JSON object in model output")
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(value[start:], start):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                parsed = json.loads(value[start : index + 1])
                if not isinstance(parsed, dict):
                    raise ValueError("model output must be one JSON object")
                return parsed
    raise ValueError("unterminated JSON object")


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def normalize_lines(lines: Any) -> list[tuple[str, str, Decimal, str]]:
    normalized: list[tuple[str, str, Decimal, str]] = []
    if not isinstance(lines, list):
        return normalized
    for row in lines:
        if not isinstance(row, dict):
            continue
        amount = _decimal(row.get("amountBase"))
        if amount is None or amount == 0:
            continue
        side = str(row.get("drCr", "")).strip().title()
        normalized.append(
            (
                str(row.get("ledgerAccountName", "")).strip(),
                side,
                amount,
                str(row.get("currency", "")).strip().upper(),
            )
        )
    return normalized


def _criterion_fact(criterion_id: str, facts: dict[str, bool]) -> bool:
    if "complete" in criterion_id:
        return facts["complete_entry"]
    if any(token in criterion_id for token in ("amount", "valuation", "basis")):
        return facts["amounts"]
    if any(token in criterion_id for token in ("drcr", "direction", "balance_side")):
        return facts["drcr"]
    if any(token in criterion_id for token in ("counter", "proceeds", "acquired", "disposed")):
        return facts["all_expected_accounts"]
    return facts["deciding_account"]


def evaluate_answer(answer: dict[str, Any] | None, expected: dict[str, Any]) -> dict[str, Any]:
    answer = answer or {}
    got = normalize_lines((answer.get("journalEntry") or {}).get("lines"))
    want = normalize_lines(expected.get("journalEntry", {}).get("lines"))
    got_names = {name for name, _, _, _ in got}
    want_names = {name for name, _, _, _ in want}
    key_names = {str(value) for value in expected.get("keyLineAccounts", [])}
    wallet_names = want_names - key_names

    got_sides = {(name, side) for name, side, _, _ in got}
    want_sides = {(name, side) for name, side, _, _ in want}
    got_amounts = {(name, amount) for name, _, amount, _ in got}
    want_amounts = {(name, amount) for name, _, amount, _ in want}
    got_currencies = {(name, currency) for name, _, _, currency in got}
    want_currencies = {(name, currency) for name, _, _, currency in want}
    currencies = {currency for _, _, _, currency in got}
    balanced = bool(got) and all(
        sum(amount for _, side, amount, row_currency in got if side == "Debit" and row_currency == currency)
        == sum(amount for _, side, amount, row_currency in got if side == "Credit" and row_currency == currency)
        for currency in currencies
    )
    expected_quantity = str(expected.get("assetQuantity", "")).strip()
    got_quantity = str(answer.get("assetQuantity", "")).strip()

    facts = {
        "valid_structure": bool(got) and isinstance(answer.get("journalEntry"), dict),
        "balanced": balanced,
        "deciding_account": key_names.issubset(got_names),
        "wallet_account": wallet_names.issubset(got_names),
        "all_expected_accounts": want_names.issubset(got_names),
        "drcr": want_sides.issubset(got_sides),
        "amounts": want_amounts.issubset(got_amounts),
        "currencies": want_currencies.issubset(got_currencies),
        "quantity": got_quantity == expected_quantity,
        "complete_entry": sorted(got) == sorted(want),
    }
    facts["exact_match"] = facts["complete_entry"] and facts["quantity"]

    criteria_results = []
    score = 0.0
    for criterion in expected.get("rubric", {}).get("criteria", []):
        criterion_id = str(criterion.get("id", ""))
        weight = float(criterion.get("weight", 0))
        passed = _criterion_fact(criterion_id, facts)
        score += weight if passed else 0.0
        criteria_results.append(
            {
                "id": criterion_id,
                "label": criterion.get("label", criterion_id),
                "weight": weight,
                "passed": passed,
            }
        )

    failed_gates = []
    gates = {
        "PARSEABLE_REQUIRED_STRUCTURE": facts["valid_structure"],
        "BALANCED_ENTRY": facts["balanced"],
        "ASSET_QUANTITY": facts["quantity"],
        "CURRENCY": facts["currencies"],
    }
    failed_gates.extend(name for name, passed in gates.items() if not passed)
    threshold = float(expected.get("rubric", {}).get("passThreshold", 0.85))
    score = round(score, 6)
    passed = score >= 1.0 and not failed_gates
    return {
        "score": score,
        "pass_threshold": threshold,
        "threshold_met": score >= threshold,
        "pass_eligible": not failed_gates,
        "passed": passed,
        "exact_match": facts["exact_match"],
        "failed_gates": failed_gates,
        "facts": facts,
        "criteria": criteria_results,
    }
