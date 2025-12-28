"""MinIO (S3-compatible) storage client."""
import os
from pathlib import Path
from typing import BinaryIO

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


class MinIOClient:
    """Client for MinIO storage operations."""

    def __init__(self):
        self.endpoint_url = os.environ.get("S3_ENDPOINT_URL", "http://minio:9000")
        self.access_key = os.environ.get("S3_ACCESS_KEY", "minioadmin")
        self.secret_key = os.environ.get("S3_SECRET_KEY", "minioadmin")
        self.bucket_name = os.environ.get("S3_BUCKET", "mindforms")

        self.s3_client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=Config(signature_version="s3v4"),
        )

        self._ensure_bucket()

    def _ensure_bucket(self):
        """Ensure bucket exists, create if not."""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except ClientError:
            self.s3_client.create_bucket(Bucket=self.bucket_name)

    def upload_file(
        self, file_path: Path | str, s3_key: str, content_type: str | None = None
    ) -> str:
        """Upload file to S3 and return the S3 key."""
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        self.s3_client.upload_file(
            str(file_path), self.bucket_name, s3_key, ExtraArgs=extra_args
        )
        return s3_key

    def upload_fileobj(
        self, file_obj: BinaryIO, s3_key: str, content_type: str | None = None
    ) -> str:
        """Upload file object to S3 and return the S3 key."""
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        self.s3_client.upload_fileobj(
            file_obj, self.bucket_name, s3_key, ExtraArgs=extra_args
        )
        return s3_key

    def download_file(self, s3_key: str, local_path: Path | str) -> Path:
        """Download file from S3 to local path."""
        self.s3_client.download_file(self.bucket_name, s3_key, str(local_path))
        return Path(local_path)

    def delete_file(self, s3_key: str):
        """Delete file from S3."""
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
        except ClientError:
            pass  # Ignore if file doesn't exist

    def generate_s3_key(
        self, telegram_user_id: int, event_id: str, filename: str, created_at_utc
    ) -> str:
        """Generate S3 key for event file."""
        year = created_at_utc.year
        month = f"{created_at_utc.month:02d}"
        day = f"{created_at_utc.day:02d}"
        return f"raw/{telegram_user_id}/{year}/{month}/{day}/{event_id}/{filename}"

