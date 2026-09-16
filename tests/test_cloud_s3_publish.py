from io import BytesIO
import json

from cloud.s3_publish import build_release_manifest, publish_release, verify_release


class FakeS3:
    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, **kwargs):
        payload = Body if isinstance(Body, bytes) else bytes(Body)
        self.objects[(Bucket, Key)] = payload
        return {"ETag": "fake"}

    def head_object(self, Bucket, Key):
        payload = self.objects[(Bucket, Key)]
        return {"ContentLength": len(payload)}

    def get_object(self, Bucket, Key):
        payload = self.objects[(Bucket, Key)]
        return {"Body": BytesIO(payload)}


def _make_release_files(root):
    paths = (
        "data/latest_forecast.csv",
        "data/latest_forecast_manifest.json",
    )
    (root / "data").mkdir()
    (root / paths[0]).write_text("x,y\n1,2\n", encoding="utf-8")
    (root / paths[1]).write_text(json.dumps({"status": "CURRENT"}), encoding="utf-8")
    return paths


def test_build_release_manifest_has_checksum_and_size(tmp_path):
    paths = _make_release_files(tmp_path)
    manifest = build_release_manifest(tmp_path, paths, revision="abc123")
    assert manifest["artifact_count"] == 2
    assert manifest["revision"] == "abc123"
    assert len(manifest["artifacts"][0]["sha256"]) == 64
    assert manifest["artifacts"][0]["size_bytes"] > 0


def test_publish_and_verify_release_with_fake_s3(tmp_path):
    paths = _make_release_files(tmp_path)
    s3 = FakeS3()
    manifest = publish_release(
        tmp_path,
        "example-bucket",
        prefix="rfs",
        artifacts=paths,
        revision="abc123",
        client=s3,
    )
    assert ("example-bucket", "rfs/data/latest_forecast.csv") in s3.objects
    assert ("example-bucket", "rfs/manifests/latest.json") in s3.objects

    verification = verify_release(manifest, "example-bucket", client=s3)
    assert verification["status"] == "VALID"
    assert verification["count"] == 2
    assert verification["checksums_verified"] is True
