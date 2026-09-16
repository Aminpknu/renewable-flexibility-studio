"""Publish validated Studio artefacts to S3 with checksums and provenance.

This module is optional: the core Dash application does not depend on S3. It is
used by the cloud/Airflow path to publish compact, versioned evidence bundles.
Credentials are never stored in the repository.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Optional


DEFAULT_ARTIFACTS = (
    "data/latest_forecast.csv",
    "data/latest_forecast_manifest.json",
    "data/latest_forecast_summary.json",
    "data/latest_market_price_forecast.csv",
    "data/latest_market_price_forecast_manifest.json",
    "data/market_forecast_pipeline_status.json",
    "outputs/probabilistic/stage14_summary.json",
    "outputs/reserve_planning_validation.json",
    "outputs/market_optimisation/pre_delivery_strategy_summary.json",
    "outputs/multiservice/stage13_issue_time_multiservice_summary.json",
    "outputs/market_investment/market_investment_summary.json",
    "outputs/project_finance/project_finance_summary.json",
    "outputs/risk_value/stage6b_default_summary.json",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_release_manifest(
    root: Path,
    artifacts: Iterable[str] = DEFAULT_ARTIFACTS,
    *,
    revision: Optional[str] = None,
) -> dict[str, Any]:
    root = Path(root).resolve()
    entries = []
    for relative in artifacts:
        path = (root / relative).resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Required cloud artefact is missing: {relative}")
        entries.append(
            {
                "path": relative.replace("\\", "/"),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    return {
        "schema_version": "rfs-cloud-release-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "revision": revision or os.getenv("RFS_RELEASE_REVISION", "unknown"),
        "artifact_count": len(entries),
        "artifacts": entries,
    }


def _build_s3_client():
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - deployment extra
        raise RuntimeError("boto3 is required for S3 publishing") from exc

    profile = os.getenv("RFS_AWS_PROFILE") or os.getenv("AWS_PROFILE") or None
    region = os.getenv("RFS_AWS_REGION", os.getenv("AWS_REGION", "eu-west-2"))
    kwargs = {"region_name": region}
    if profile:
        kwargs["profile_name"] = profile
    session = boto3.Session(**kwargs)
    endpoint_url = os.getenv("RFS_S3_ENDPOINT_URL") or os.getenv("AWS_ENDPOINT_URL_S3") or None
    client_kwargs = {"endpoint_url": endpoint_url} if endpoint_url else {}
    return session.client("s3", **client_kwargs)


def _object_key(prefix: str, relative_path: str) -> str:
    clean_prefix = prefix.strip("/")
    clean_relative = relative_path.replace("\\", "/").lstrip("/")
    return f"{clean_prefix}/{clean_relative}" if clean_prefix else clean_relative


def publish_release(
    root: Path,
    bucket: str,
    *,
    prefix: str = "renewable-flexibility-studio",
    artifacts: Iterable[str] = DEFAULT_ARTIFACTS,
    revision: Optional[str] = None,
    client: Any = None,
) -> dict[str, Any]:
    if not bucket or not str(bucket).strip():
        raise ValueError("S3 bucket name is required")
    root = Path(root).resolve()
    manifest = build_release_manifest(root, artifacts, revision=revision)
    s3 = client or _build_s3_client()

    for item in manifest["artifacts"]:
        path = root / item["path"]
        key = _object_key(prefix, item["path"])
        s3.put_object(
            Bucket=str(bucket),
            Key=key,
            Body=path.read_bytes(),
            ServerSideEncryption="AES256",
        )
        item["s3_key"] = key

    manifest_key = _object_key(prefix, "manifests/latest.json")
    manifest["s3_manifest_key"] = manifest_key
    s3.put_object(
        Bucket=str(bucket),
        Key=manifest_key,
        Body=json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"),
        ContentType="application/json",
        ServerSideEncryption="AES256",
    )
    return manifest


def verify_release(
    manifest: dict[str, Any],
    bucket: str,
    *,
    client: Any = None,
) -> dict[str, Any]:
    s3 = client or _build_s3_client()
    checked = []
    for item in manifest.get("artifacts", []):
        key = item.get("s3_key")
        if not key:
            raise ValueError("Manifest artefact is missing s3_key")
        head = s3.head_object(Bucket=str(bucket), Key=str(key))
        if int(head.get("ContentLength", -1)) != int(item["size_bytes"]):
            raise ValueError(f"S3 size mismatch for {key}")
        remote = s3.get_object(Bucket=str(bucket), Key=str(key))["Body"].read()
        remote_sha256 = hashlib.sha256(remote).hexdigest()
        if remote_sha256 != item["sha256"]:
            raise ValueError(f"S3 checksum mismatch for {key}")
        checked.append(str(key))
    return {
        "status": "VALID",
        "checked_objects": checked,
        "count": len(checked),
        "checksums_verified": True,
    }
