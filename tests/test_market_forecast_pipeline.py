from __future__ import annotations

import hashlib
import json

import pandas as pd

import scripts.run_market_forecast_pipeline as pipeline


def _write_bundle(csv_path, manifest_path, target: str, created: str) -> None:
    start = pd.Timestamp(target, tz="UTC")
    frame = pd.DataFrame({
        "forecast_created_utc": [created] * 48,
        "settlement_date": [target] * 48,
        "settlement_period": range(1, 49),
        "valid_time_utc": pd.date_range(start, periods=48, freq="30min"),
        "forecast_market_index_price_gbp_per_mwh": [80.0] * 48,
        "naive_market_index_price_gbp_per_mwh": [75.0] * 48,
    })
    text = frame.to_csv(index=False, lineterminator="\n")
    csv_path.write_text(text, encoding="utf-8", newline="")
    manifest = {
        "schema_version": "1.1", "target_date": target,
        "forecast_created_utc": created, "period_count": 48,
        "target_start_utc": start.isoformat(),
        "issued_before_target_start": pd.Timestamp(created) <= start,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def _redirect_paths(monkeypatch, tmp_path, target: str) -> None:
    monkeypatch.setattr(pipeline, "DATA", tmp_path)
    monkeypatch.setattr(pipeline, "RENEWABLE", tmp_path / "renewable.csv")
    monkeypatch.setattr(pipeline, "LATEST_CSV", tmp_path / "latest.csv")
    monkeypatch.setattr(pipeline, "LATEST_MANIFEST", tmp_path / "latest.json")
    monkeypatch.setattr(pipeline, "LAST_VALID_CSV", tmp_path / "last.csv")
    monkeypatch.setattr(pipeline, "LAST_VALID_MANIFEST", tmp_path / "last.json")
    monkeypatch.setattr(pipeline, "STATUS_PATH", tmp_path / "status.json")
    monkeypatch.setattr(pipeline, "load_latest_forecast", lambda _path: object())
    monkeypatch.setattr(pipeline, "latest_target_date", lambda _frame: target)


def test_pipeline_retains_valid_bundle_when_refresh_fails(monkeypatch, tmp_path) -> None:
    target = "2099-01-02"
    _redirect_paths(monkeypatch, tmp_path, target)
    _write_bundle(
        pipeline.LATEST_CSV, pipeline.LATEST_MANIFEST,
        target, "2099-01-03T08:00:00Z",
    )
    before = pipeline.LATEST_CSV.read_text(encoding="utf-8")

    def failing_builder(*_args, **_kwargs):
        raise RuntimeError("temporary market API failure")

    result = pipeline.run_pipeline(builder=failing_builder)
    assert result["pipeline_status"] == "FALLBACK_RETAINED"
    assert pipeline.LATEST_CSV.read_text(encoding="utf-8") == before
    assert "temporary market API failure" in result["refresh_error"]


def test_pipeline_publishes_candidate_and_archives_previous(monkeypatch, tmp_path) -> None:
    target = "2099-01-02"
    _redirect_paths(monkeypatch, tmp_path, target)
    _write_bundle(
        pipeline.LATEST_CSV, pipeline.LATEST_MANIFEST,
        "2099-01-01", "2098-12-31T18:00:00Z",
    )

    def builder(csv_path, manifest_path, *, target_date):
        _write_bundle(csv_path, manifest_path, target_date, "2099-01-01T18:00:00Z")
        return {"target_date": target_date}

    result = pipeline.run_pipeline(builder=builder)
    assert result["pipeline_status"] == "PUBLISHED"
    assert result["bundle_health"]["status"] == "LIVE"
    latest = json.loads(pipeline.LATEST_MANIFEST.read_text(encoding="utf-8"))
    archived = json.loads(pipeline.LAST_VALID_MANIFEST.read_text(encoding="utf-8"))
    assert latest["target_date"] == target
    assert archived["target_date"] == "2099-01-01"


def test_pipeline_never_replaces_live_issue_with_reconstruction(monkeypatch, tmp_path) -> None:
    target = "2099-01-02"
    _redirect_paths(monkeypatch, tmp_path, target)
    _write_bundle(
        pipeline.LATEST_CSV, pipeline.LATEST_MANIFEST,
        target, "2099-01-01T18:00:00Z",
    )
    before = pipeline.LATEST_CSV.read_text(encoding="utf-8")

    def builder(csv_path, manifest_path, *, target_date):
        _write_bundle(csv_path, manifest_path, target_date, "2099-01-03T08:00:00Z")
        return {"target_date": target_date}

    result = pipeline.run_pipeline(builder=builder)
    assert result["pipeline_status"] == "RETAINED_LIVE_BUNDLE"
    assert pipeline.LATEST_CSV.read_text(encoding="utf-8") == before


def test_replace_with_retry_handles_transient_permission_error(monkeypatch, tmp_path) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"
    source.write_text("new", encoding="utf-8")
    destination.write_text("old", encoding="utf-8")
    original_replace = pipeline.os.replace
    calls = {"count": 0}

    def flaky_replace(src, dst):
        calls["count"] += 1
        if calls["count"] < 3:
            raise PermissionError("transient file lock")
        return original_replace(src, dst)

    monkeypatch.setattr(pipeline.os, "replace", flaky_replace)
    monkeypatch.setattr(pipeline.time, "sleep", lambda _seconds: None)
    pipeline._replace_with_retry(source, destination)
    assert destination.read_text(encoding="utf-8") == "new"
    assert calls["count"] == 3
