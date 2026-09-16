"""Airflow DAG for publishing validated Studio bundles to Amazon S3.

Large data stays in files/S3. Only compact manifest metadata is passed between
Airflow tasks, keeping orchestration separate from storage.
"""

from __future__ import annotations

from datetime import timedelta
import os
from pathlib import Path

import pendulum
from airflow.sdk import dag, task

from cloud.s3_publish import DEFAULT_ARTIFACTS, build_release_manifest, publish_release, verify_release


ROOT = Path(
    os.getenv("RFS_PROJECT_ROOT", str(Path(__file__).resolve().parents[2]))
).resolve()
BUCKET = os.getenv("RFS_S3_BUCKET", "").strip()
PREFIX = os.getenv("RFS_S3_PREFIX", "renewable-flexibility-studio").strip("/")


@dag(
    dag_id="rfs_validated_bundle_to_s3",
    schedule="0 5 * * *",
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    catchup=False,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["rfs", "aws", "s3"],
)
def rfs_cloud_pipeline():
    @task
    def validate_bundle():
        return build_release_manifest(
            ROOT,
            DEFAULT_ARTIFACTS,
            revision=os.getenv("RFS_RELEASE_REVISION", "unknown"),
        )

    @task
    def publish_bundle(_validated_manifest):
        if not BUCKET:
            raise ValueError("RFS_S3_BUCKET must be configured for this DAG")
        return publish_release(
            ROOT,
            BUCKET,
            prefix=PREFIX,
            artifacts=DEFAULT_ARTIFACTS,
            revision=os.getenv("RFS_RELEASE_REVISION", "unknown"),
        )

    @task
    def verify_bundle(published_manifest):
        if not BUCKET:
            raise ValueError("RFS_S3_BUCKET must be configured for this DAG")
        return verify_release(published_manifest, BUCKET)

    validated = validate_bundle()
    published = publish_bundle(validated)
    verify_bundle(published)


rfs_validated_bundle_to_s3 = rfs_cloud_pipeline()
