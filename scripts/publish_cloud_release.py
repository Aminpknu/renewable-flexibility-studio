"""Publish the validated Studio cloud release to S3 and verify it."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from cloud.s3_publish import publish_release, verify_release


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", default=os.getenv("RFS_S3_BUCKET", ""))
    parser.add_argument("--prefix", default=os.getenv("RFS_S3_PREFIX", "renewable-flexibility-studio"))
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--revision", default=os.getenv("RFS_RELEASE_REVISION", "manual"))
    args = parser.parse_args()
    if not args.bucket:
        parser.error("--bucket or RFS_S3_BUCKET is required")

    manifest = publish_release(
        Path(args.root),
        args.bucket,
        prefix=args.prefix,
        revision=args.revision,
    )
    verification = verify_release(manifest, args.bucket)
    print(json.dumps({"manifest": manifest, "verification": verification}, indent=2))


if __name__ == "__main__":
    main()
