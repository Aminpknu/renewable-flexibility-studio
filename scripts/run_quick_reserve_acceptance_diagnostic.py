"""Diagnose whether a simple bid<=clearing-price rule identifies QR acceptance."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "quick_reserve" / "quick_reserve_acceptance_diagnostic.json"
SQL_URL = "https://api.neso.energy/api/3/action/datastore_search_sql"
MONTHLY_SELL_ORDER_RESOURCES = {
    "2026-04": "45d867bb-eccb-4a60-8618-74316aafde5a",
    "2026-05": "654c9fcd-9d0b-42c5-bac7-9fa245b5f99d",
    "2026-06": "85272de8-2fd7-4578-ae4b-55da74629841",
}


def _query(resource_id: str) -> list[dict]:
    sql = (
        f'SELECT "orderType", "status", count(*) AS n, '
        f'sum(CASE WHEN "priceLimit" <= "clearingPrice" THEN 1 ELSE 0 END) AS below_clear '
        f'FROM "{resource_id}" WHERE "serviceType"=\'Quick Reserve\' '
        f'GROUP BY "orderType", "status"'
    )
    with urlopen(f"{SQL_URL}?sql={quote(sql)}", timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("success"):
        raise RuntimeError("NESO sell-order aggregate query failed.")
    return payload["result"]["records"]


def _summarise(records: list[dict]) -> dict:
    true_positive = 0
    false_positive = 0
    false_negative = 0
    true_negative = 0
    total = 0
    by_order_type = {}
    for record in records:
        n = int(record["n"])
        below = int(record["below_clear"])
        above = n - below
        status = str(record["status"])
        order_type = str(record["orderType"])
        accepted = status in {"EXECUTED", "PARTIALLY_EXECUTED"}
        if accepted:
            true_positive += below
            false_negative += above
        else:
            false_positive += below
            true_negative += above
        total += n
        bucket = by_order_type.setdefault(order_type, {
            "orders": 0, "accepted_orders": 0,
            "rejected_below_clearing": 0, "accepted_above_clearing": 0,
        })
        bucket["orders"] += n
        if accepted:
            bucket["accepted_orders"] += n
            bucket["accepted_above_clearing"] += above
        else:
            bucket["rejected_below_clearing"] += below
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive > 0 else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative > 0 else 0.0
    )
    accuracy = (
        (true_positive + true_negative) / total if total > 0 else 0.0
    )
    return {
        "orders": total,
        "threshold_rule": "predict accepted if priceLimit <= clearingPrice",
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_negative": true_negative,
        "precision_pct": 100.0 * precision,
        "recall_pct": 100.0 * recall,
        "accuracy_pct": 100.0 * accuracy,
        "by_order_type": by_order_type,
    }


def main() -> None:
    all_records = []
    monthly = {}
    for month, resource_id in MONTHLY_SELL_ORDER_RESOURCES.items():
        records = _query(resource_id)
        monthly[month] = _summarise(records)
        all_records.extend(records)
        print(f"{month}: {monthly[month]['orders']:,} QR sell orders", flush=True)
    combined = _summarise(all_records)
    payload = {
        "schema_version": "1.0",
        "stage": "9_quick_reserve_acceptance_diagnostic",
        "source": "NESO EAC monthly Sell Orders archives",
        "service": "Quick Reserve",
        "months": list(MONTHLY_SELL_ORDER_RESOURCES),
        "monthly_resource_ids": MONTHLY_SELL_ORDER_RESOURCES,
        "combined": combined,
        "monthly": monthly,
        "interpretation": (
            "A simple bid-price threshold is not sufficient to identify QR execution; "
            "basket/substitution/flexible-order constraints can reject orders below clearing."
        ),
        "model_boundary": (
            "No asset-specific auction-acceptance probability is inferred from clearing price alone."
        ),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
