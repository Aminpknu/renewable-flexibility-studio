"""Build expanding issue-time EAC acceptance calibration without participant identities."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from engine.multiservice_acceptance import (
    AcceptanceLookupConfig, add_acceptance_bins, aggregate_acceptance_orders,
    predict_acceptance_ratio,
)
from engine.multiservice_forecast import build_multiservice_forecast_features

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "build_sources" / "stage13"
HISTORY = ROOT / "data" / "neso_multiservice_forecast_history.csv"
CALIBRATION_OUT = ROOT / "data" / "neso_multiservice_acceptance_calibration.csv"
CALIBRATION_APRIL_OUT = ROOT / "data" / "neso_multiservice_acceptance_calibration_april.csv"
MANIFEST_OUT = ROOT / "data" / "neso_multiservice_acceptance_calibration_manifest.json"
VALIDATION_OUT = ROOT / "outputs" / "multiservice" / "stage13_acceptance_validation.csv"
SUMMARY_OUT = ROOT / "outputs" / "multiservice" / "stage13_acceptance_summary.json"
MONTHS = ["202604", "202605", "202606"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reference_prices() -> pd.DataFrame:
    history = pd.read_csv(HISTORY)
    features = build_multiservice_forecast_features(history)
    return features[["product", "delivery_start_utc", "price_lag1"]].rename(
        columns={"price_lag1": "prior_same_window_price"}
    ).dropna().drop_duplicates(["product", "delivery_start_utc"])


def _load_month(month: str, reference: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    path = RAW_DIR / f"sell_{month}.csv"
    columns = [
        "basketID", "orderType", "loopedBasketID", "auctionProduct",
        "priceLimit", "quantity", "acceptanceRatio", "deliveryStart",
    ]
    frame = pd.read_csv(path, usecols=columns, low_memory=False)
    basket_counts = frame.groupby("basketID", dropna=False).size()
    frame["basket_rows"] = frame["basketID"].map(basket_counts)
    frame = frame.loc[frame["orderType"].eq("PARENT") & frame["loopedBasketID"].isna()].copy()
    frame["quantity_mw"] = pd.to_numeric(frame["quantity"], errors="coerce")
    frame["price_limit"] = pd.to_numeric(frame["priceLimit"], errors="coerce")
    frame["acceptance_ratio"] = pd.to_numeric(frame["acceptanceRatio"], errors="coerce")
    frame["delivery_start_utc"] = pd.to_datetime(frame["deliveryStart"], utc=True, errors="coerce")
    frame["product"] = frame["auctionProduct"].astype(str)
    frame = frame.loc[
        frame["quantity_mw"].gt(0)
        & frame["price_limit"].notna()
        & frame["acceptance_ratio"].notna()
        & frame["delivery_start_utc"].notna()
    ].copy()
    frame = frame.merge(reference, on=["product", "delivery_start_utc"], how="inner", validate="many_to_one")
    broad = frame.copy()
    strict = frame.loc[frame["basket_rows"].eq(1)].copy()
    return strict, broad


def _aggregate_month(month: str, strict: pd.DataFrame, broad: pd.DataFrame) -> pd.DataFrame:
    pieces = [
        aggregate_acceptance_orders(strict, "standalone_parent"),
        aggregate_acceptance_orders(broad, "nonlooped_parent"),
    ]
    result = pd.concat(pieces, ignore_index=True)
    result["source_month"] = month
    return result


def _validation_bins(strict: pd.DataFrame) -> pd.DataFrame:
    work = add_acceptance_bins(strict)
    work["acceptance_squared"] = work["acceptance_ratio"] ** 2
    return work.groupby(["product", "margin_bin", "quantity_bin"], observed=True, as_index=False).agg(
        orders=("acceptance_ratio", "size"),
        acceptance_sum=("acceptance_ratio", "sum"),
        acceptance_squared_sum=("acceptance_squared", "sum"),
    )


def _score_validation(
    validation_month: str,
    validation: pd.DataFrame,
    calibration: pd.DataFrame,
    config: AcceptanceLookupConfig,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    product_prior = calibration.loc[calibration["sample_class"].eq("standalone_parent")].groupby("product").agg(
        prior_orders=("orders", "sum"), prior_accepted=("accepted_fraction_sum", "sum")
    )
    for row in validation.itertuples(index=False):
        margin_mid = {
            "<-10": -15.0, "-10:-5": -7.5, "-5:-2": -3.5, "-2:-1": -1.5,
            "-1:-0.5": -0.75, "-0.5:0": -0.25, "0:0.5": 0.25, "0.5:1": 0.75,
            "1:2": 1.5, "2:5": 3.5, ">5": 7.5,
        }[str(row.margin_bin)]
        quantity_mid = {"0:1": 1.0, "1:5": 3.0, "5:10": 7.5, "10:25": 17.5, ">25": 30.0}[str(row.quantity_bin)]
        probability, meta = predict_acceptance_ratio(
            calibration, str(row.product), margin_mid, quantity_mid, 0.0, config
        )
        if str(row.product) in product_prior.index:
            prior_row = product_prior.loc[str(row.product)]
            baseline = float(prior_row.prior_accepted / prior_row.prior_orders)
        else:
            baseline = 0.0
        actual_mean = float(row.acceptance_sum / row.orders)
        brier_sum = float(row.orders * probability**2 - 2.0 * probability * row.acceptance_sum + row.acceptance_squared_sum)
        baseline_brier_sum = float(row.orders * baseline**2 - 2.0 * baseline * row.acceptance_sum + row.acceptance_squared_sum)
        rows.append({
            "validation_month": validation_month, "product": str(row.product),
            "margin_bin": str(row.margin_bin), "quantity_bin": str(row.quantity_bin),
            "orders": int(row.orders), "actual_acceptance_mean": actual_mean,
            "predicted_acceptance": probability, "product_baseline_acceptance": baseline,
            "brier_sum": brier_sum, "baseline_brier_sum": baseline_brier_sum,
            "lookup_level": str(meta["level"]), "lookup_orders": int(meta["orders"]),
        })
    return pd.DataFrame(rows)


def _summarise_validation(scored: pd.DataFrame) -> dict[str, object]:
    total_orders = int(scored["orders"].sum())
    brier = float(scored["brier_sum"].sum() / total_orders)
    baseline_brier = float(scored["baseline_brier_sum"].sum() / total_orders)
    weighted_calibration_mae = float(
        (scored["orders"] * (scored["predicted_acceptance"] - scored["actual_acceptance_mean"]).abs()).sum()
        / total_orders
    )
    by_product: dict[str, object] = {}
    for product, group in scored.groupby("product"):
        orders = int(group["orders"].sum())
        by_product[str(product)] = {
            "orders": orders,
            "actual_acceptance_pct": float(100.0 * (group["orders"] * group["actual_acceptance_mean"]).sum() / orders),
            "predicted_acceptance_pct": float(100.0 * (group["orders"] * group["predicted_acceptance"]).sum() / orders),
            "brier_score": float(group["brier_sum"].sum() / orders),
            "baseline_brier_score": float(group["baseline_brier_sum"].sum() / orders),
        }
    return {
        "orders": total_orders, "brier_score": brier,
        "product_baseline_brier_score": baseline_brier,
        "brier_improvement_vs_product_baseline_pct": 100.0 * (1.0 - brier / baseline_brier) if baseline_brier > 0 else 0.0,
        "weighted_calibration_mae": weighted_calibration_mae,
        "by_product": by_product,
    }


def main() -> None:
    reference = _reference_prices()
    month_aggregates: dict[str, pd.DataFrame] = {}
    strict_validation: dict[str, pd.DataFrame] = {}
    raw_sha: dict[str, str] = {}
    for month in MONTHS:
        path = RAW_DIR / f"sell_{month}.csv"
        print(f"processing {month}", flush=True)
        strict, broad = _load_month(month, reference)
        month_aggregates[month] = _aggregate_month(month, strict, broad)
        strict_validation[month] = _validation_bins(strict)
        raw_sha[path.name] = _sha256(path)
        print(f"  strict={len(strict):,}; broad={len(broad):,}", flush=True)
        del strict, broad

    config = AcceptanceLookupConfig()
    scored_parts: list[pd.DataFrame] = []
    may_calibration = month_aggregates["202604"].copy()
    may_calibration.to_csv(CALIBRATION_APRIL_OUT, index=False)
    scored_parts.append(_score_validation("202605", strict_validation["202605"], may_calibration, config))
    june_calibration = pd.concat([month_aggregates["202604"], month_aggregates["202605"]], ignore_index=True)
    june_calibration = june_calibration.groupby(
        ["sample_class", "product", "margin_bin", "quantity_bin"], as_index=False, observed=True
    ).agg(orders=("orders", "sum"), accepted_fraction_sum=("accepted_fraction_sum", "sum"))
    scored_parts.append(_score_validation("202606", strict_validation["202606"], june_calibration, config))
    scored = pd.concat(scored_parts, ignore_index=True)
    VALIDATION_OUT.parent.mkdir(parents=True, exist_ok=True)
    scored.to_csv(VALIDATION_OUT, index=False)
    june_calibration.to_csv(CALIBRATION_OUT, index=False)
    summary = {
        "schema_version": "1.0",
        "stage": "13_issue_time_acceptance_calibration",
        "training_rule": "May uses April only; June uses April+May",
        "order_proxy": "non-looped PARENT; standalone parent-only basket preferred by hierarchy",
        "identity_fields_retained": False,
        "features": ["product", "bid price minus previous same-product/window clearing price", "quantity bin"],
        "validation": _summarise_validation(scored),
        "lookup_config": {
            "minimum_cell_orders": config.minimum_cell_orders,
            "minimum_margin_orders": config.minimum_margin_orders,
            "smoothing_strength": config.smoothing_strength,
        },
        "raw_source_sha256": raw_sha,
        "counterfactual_boundary": (
            "The model estimates acceptance for a hypothetical simple BESS offer from historical comparable orders; "
            "it cannot identify the exact counterfactual merit-order outcome for an asset that was not present."
        ),
    }
    SUMMARY_OUT.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    calibration_text = june_calibration.to_csv(index=False, lineterminator="\n")
    april_text = may_calibration.to_csv(index=False, lineterminator="\n")
    manifest = {
        "schema_version": "1.0", "source": "NESO EAC Sell Orders monthly archives",
        "rights": "NESO Open Data Licence", "months_used": MONTHS[:2],
        "april_only_output_rows": int(len(may_calibration)),
        "april_only_output_sha256": hashlib.sha256(april_text.encode("utf-8")).hexdigest(),
        "april_may_output_rows": int(len(june_calibration)),
        "april_may_output_sha256": hashlib.sha256(calibration_text.encode("utf-8")).hexdigest(),
        "raw_source_sha256": {key: raw_sha[key] for key in ["sell_202604.csv", "sell_202605.csv"]},
        "participant_or_unit_identifiers_retained": False,
        "purpose": "issue-time acceptance lookup for June 2026 and later screening",
    }
    MANIFEST_OUT.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
