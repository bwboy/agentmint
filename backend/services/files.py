"""File storage service — S3-compatible (MinIO for dev, OSS for prod).

Uploaded files get a UUID-prefixed key inside the bucket. URLs returned are
either presigned (for private buckets) or direct (when the bucket is public).
"""
import uuid
import mimetypes
from pathlib import PurePosixPath
from typing import BinaryIO

import boto3
from botocore.client import Config

from config import settings


def _client():
    if settings.file_store == "oss":
        # Aliyun OSS exposes an S3-compatible endpoint
        return boto3.client(
            "s3",
            endpoint_url=f"https://{settings.oss_endpoint}",
            aws_access_key_id=settings.oss_access_key_id,
            aws_secret_access_key=settings.oss_access_key_secret,
            config=Config(signature_version="s3v4"),
        )
    return boto3.client(
        "s3",
        endpoint_url=settings.minio_endpoint,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def _bucket() -> str:
    return settings.oss_bucket if settings.file_store == "oss" else settings.minio_bucket


def ensure_bucket():
    """Create the bucket if it does not exist (no-op for OSS — buckets are
    provisioned via the console)."""
    if settings.file_store != "minio":
        return
    s3 = _client()
    try:
        s3.head_bucket(Bucket=_bucket())
    except Exception:
        try:
            s3.create_bucket(Bucket=_bucket())
        except Exception as e:
            print(f"[files] could not create bucket {_bucket()}: {e}")


def detect_kind(mime: str) -> str:
    if mime.startswith("image/"): return "image"
    if mime.startswith("video/"): return "video"
    if mime.startswith("audio/"): return "audio"
    if mime in ("text/csv",) or mime.endswith("spreadsheetml.sheet"): return "spreadsheet"
    if mime.startswith("text/") or mime in ("application/json", "application/xml"): return "code"
    if mime in ("application/pdf",) or "wordprocessingml" in mime or "presentationml" in mime: return "document"
    return "other"


def upload(stream: BinaryIO, filename: str, content_type: str | None = None) -> dict:
    """Upload a file. Returns metadata dict including a fetchable URL."""
    ensure_bucket()
    ext = PurePosixPath(filename).suffix
    key = f"uploads/{uuid.uuid4().hex}{ext}"
    mime = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

    s3 = _client()
    s3.upload_fileobj(stream, _bucket(), key, ExtraArgs={"ContentType": mime})

    if settings.file_store == "oss":
        url = f"https://{_bucket()}.{settings.oss_endpoint}/{key}"
    else:
        url = object_url(key)

    return {
        "id": f"f_{uuid.uuid4().hex[:8]}",
        "key": key,
        "filename": filename,
        "mime": mime,
        "type": detect_kind(mime),
        "url": url,
    }


def object_url(key: str) -> str:
    public_base = (settings.public_api_base_url or "").rstrip("/")
    safe_key = str(key or "").lstrip("/")
    return f"{public_base}/api/files/object/{safe_key}"


def get_object(key: str):
    safe_key = str(key or "").lstrip("/")
    if not safe_key or ".." in PurePosixPath(safe_key).parts:
        raise ValueError("invalid file key")
    s3 = _client()
    return s3.get_object(Bucket=_bucket(), Key=safe_key)
