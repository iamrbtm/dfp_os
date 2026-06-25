from __future__ import annotations

import io
import mimetypes
import os
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from flask import abort, current_app, send_file


def storage_backend() -> str:
    return str(current_app.config.get("FILE_STORAGE_BACKEND", "local")).strip().lower()


def using_s3_storage() -> bool:
    return storage_backend() == "s3"


def is_s3_reference(reference: str | None) -> bool:
    return bool(reference and str(reference).startswith("s3://"))


def parse_s3_reference(reference: str) -> tuple[str, str]:
    parsed = urlparse(reference)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    if not bucket or not key:
        raise ValueError(f"Invalid S3 storage reference: {reference}")
    return bucket, key


def build_s3_reference(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key}"


def storage_reference_name(reference: str | None) -> str:
    if not reference:
        return ""
    if is_s3_reference(reference):
        _, key = parse_s3_reference(reference)
        return Path(key).name
    return Path(reference).name


def storage_reference_extension(reference: str | None) -> str:
    return Path(storage_reference_name(reference)).suffix.lower()


def content_type_for_name(filename: str, default: str = "application/octet-stream") -> str:
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or default


def _s3_client():
    endpoint_url = current_app.config.get("S3_ENDPOINT_URL")
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=current_app.config.get("S3_REGION", "us-east-1"),
        aws_access_key_id=current_app.config.get("S3_ACCESS_KEY"),
        aws_secret_access_key=current_app.config.get("S3_SECRET_KEY"),
        config=BotoConfig(s3={"addressing_style": "path"}),
        use_ssl=bool(current_app.config.get("S3_USE_SSL", False)),
    )


def ensure_bucket(bucket: str) -> None:
    if not bucket or not using_s3_storage():
        return
    client = _s3_client()
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)


def bootstrap_object_storage() -> None:
    if not using_s3_storage():
        return
    if not current_app.config.get("S3_AUTO_CREATE_BUCKETS", True):
        return
    try:
        for bucket in (
            current_app.config.get("RECEIPT_STORAGE_BUCKET"),
            current_app.config.get("MARKET_DOCUMENTS_BUCKET"),
            current_app.config.get("PRODUCT_ASSETS_BUCKET"),
        ):
            if bucket:
                ensure_bucket(bucket)
    except Exception as exc:  # pragma: no cover - startup safety fallback
        current_app.logger.warning("Object storage bootstrap skipped: %s", exc)


def upload_file_to_storage(
    local_path: str | Path,
    *,
    bucket: str,
    key: str,
    local_root: str | Path,
    content_type: str | None = None,
) -> str:
    source = Path(local_path)
    if using_s3_storage():
        ensure_bucket(bucket)
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type
        _s3_client().upload_file(str(source), bucket, key, ExtraArgs=extra_args or None)
        return build_s3_reference(bucket, key)

    destination = Path(local_root) / key
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
    return str(destination.resolve())


def upload_bytes_to_storage(
    data: bytes,
    *,
    bucket: str,
    key: str,
    local_root: str | Path,
    content_type: str | None = None,
) -> str:
    if using_s3_storage():
        ensure_bucket(bucket)
        kwargs = {"Bucket": bucket, "Key": key, "Body": data}
        if content_type:
            kwargs["ContentType"] = content_type
        _s3_client().put_object(**kwargs)
        return build_s3_reference(bucket, key)

    destination = Path(local_root) / key
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return str(destination.resolve())


def download_storage_bytes(reference: str) -> bytes:
    if is_s3_reference(reference):
        bucket, key = parse_s3_reference(reference)
        try:
            response = _s3_client().get_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"NoSuchBucket", "NoSuchKey", "404"}:
                abort(404)
            current_app.logger.exception("S3 object download failed for %s", reference)
            raise
        return response["Body"].read()
    return Path(reference).read_bytes()


def delete_storage_reference(reference: str | None) -> None:
    if not reference:
        return
    if is_s3_reference(reference):
        bucket, key = parse_s3_reference(reference)
        _s3_client().delete_object(Bucket=bucket, Key=key)
        return
    path = Path(reference)
    if path.exists():
        path.unlink()


def materialize_storage_reference(
    reference: str,
    *,
    suffix: str | None = None,
    working_dir: str | Path | None = None,
) -> tuple[str, bool]:
    if is_s3_reference(reference):
        tmp_dir = Path(working_dir) if working_dir else Path(tempfile.mkdtemp(prefix="dfpos-storage-"))
        tmp_dir.mkdir(parents=True, exist_ok=True)
        extension = suffix or storage_reference_extension(reference)
        tmp_file = tmp_dir / f"object{extension}"
        tmp_file.write_bytes(download_storage_bytes(reference))
        return str(tmp_file), True
    return reference, False


def send_storage_reference(
    reference: str,
    *,
    download_name: str | None = None,
    mimetype: str | None = None,
    as_attachment: bool = False,
):
    storage_name = storage_reference_name(reference)
    response_download_name = download_name or storage_name or "download"
    response_mimetype = mimetype or content_type_for_name(response_download_name)
    if is_s3_reference(reference):
        return send_file(
            io.BytesIO(download_storage_bytes(reference)),
            download_name=response_download_name,
            mimetype=response_mimetype,
            as_attachment=as_attachment,
        )
    return send_file(
        reference,
        download_name=download_name,
        mimetype=mimetype,
        as_attachment=as_attachment,
    )


def product_asset_key(product_id: int, category: str, filename: str) -> str:
    return f"products/{product_id}/{category}/{filename}"


def variant_asset_key(product_id: int, variant_id: int, category: str, filename: str) -> str:
    return f"products/{product_id}/variants/{variant_id}/{category}/{filename}"


def product_storage_key(product_id: int, filename: str, *, variant_id: int | None = None) -> str:
    if variant_id is not None:
        return f"products/{product_id}/variants/{variant_id}/models/{filename}"
    return f"products/{product_id}/models/{filename}"


def converted_storage_key(product_id: int, filename: str, *, variant_id: int | None = None) -> str:
    if variant_id is not None:
        return f"products/{product_id}/variants/{variant_id}/converted/{filename}"
    return f"products/{product_id}/converted/{filename}"


def gcode_storage_key(product_id: int, filename: str, *, variant_id: int | None = None) -> str:
    if variant_id is not None:
        return f"products/{product_id}/variants/{variant_id}/gcode/{filename}"
    return f"products/{product_id}/gcode/{filename}"


def image_storage_key(product_id: int, filename: str, *, variant_id: int | None = None) -> str:
    if variant_id is not None:
        return f"products/{product_id}/variants/{variant_id}/images/{filename}"
    return f"products/{product_id}/images/{filename}"
