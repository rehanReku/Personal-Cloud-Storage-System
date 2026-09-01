import time
import io
from typing import Dict, Any, Optional, Tuple, BinaryIO
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError

from storage.base import (
    StorageProvider,
    StorageError,
    NotFoundError,
    AuthenticationError,
    PermissionDeniedError,
    TemporaryUnavailableError,
    format_bytes
)

class AWSStorageProvider(StorageProvider):
    """AWS S3 Storage Provider wrapping boto3 calls into normalized StorageProvider contract."""
    
    def __init__(self, bucket_name: str, region_name: str = "ap-south-1",
                 aws_access_key_id: Optional[str] = None,
                 aws_secret_access_key: Optional[str] = None,
                 endpoint_url: Optional[str] = None):
        self.bucket_name = bucket_name
        self.region_name = region_name
        
        session_kwargs = {
            "region_name": region_name,
            "config": Config(
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required"
            )
        }
        if aws_access_key_id and aws_secret_access_key:
            session_kwargs["aws_access_key_id"] = aws_access_key_id
            session_kwargs["aws_secret_access_key"] = aws_secret_access_key
            
        if endpoint_url:
            session_kwargs["endpoint_url"] = endpoint_url
            
        self.s3_client = boto3.client("s3", **session_kwargs)


    def _handle_client_error(self, e: ClientError, key: str = "") -> Exception:
        code = e.response.get("Error", {}).get("Code", "")
        msg = e.response.get("Error", {}).get("Message", str(e))
        if code in ("NoSuchKey", "404", "NoSuchBucket"):
            return NotFoundError(f"S3 key '{key}' or bucket '{self.bucket_name}' not found: {msg}", raw_error=e)
        elif code in ("AccessDenied", "403"):
            return PermissionDeniedError(f"Access denied for S3 bucket '{self.bucket_name}': {msg}", raw_error=e)
        elif code in ("InvalidAccessKeyId", "SignatureDoesNotMatch", "ExpiredToken"):
            return AuthenticationError(f"S3 authentication failed: {msg}", raw_error=e)
        elif code in ("SlowDown", "503", "ServiceUnavailable"):
            return TemporaryUnavailableError(f"S3 service temporarily unavailable: {msg}", raw_error=e)
        return StorageError(f"S3 operational error [{code}]: {msg}", code=code, raw_error=e)

    def health_check(self) -> Dict[str, Any]:
        start = time.time()
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            latency = (time.time() - start) * 1000
            return {
                "status": "healthy",
                "latency_ms": round(latency, 2),
                "message": f"Successfully connected to AWS S3 bucket '{self.bucket_name}' ({self.region_name})",
                "code": "ok"
            }
        except ClientError as e:
            latency = (time.time() - start) * 1000
            err = self._handle_client_error(e)
            return {
                "status": "unhealthy",
                "latency_ms": round(latency, 2),
                "message": str(err),
                "code": getattr(err, "code", "unhealthy")
            }
        except Exception as e:
            latency = (time.time() - start) * 1000
            return {
                "status": "unhealthy",
                "latency_ms": round(latency, 2),
                "message": f"AWS S3 health check failed: {str(e)}",
                "code": "error"
            }

    def get_storage_usage(self) -> Dict[str, Any]:
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            total_size = 0
            count = 0
            for page in paginator.paginate(Bucket=self.bucket_name):
                for obj in page.get('Contents', []):
                    total_size += obj['Size']
                    count += 1
            return {
                "object_count": count,
                "total_size_bytes": total_size,
                "formatted_size": format_bytes(total_size)
            }
        except Exception:
            return {"object_count": 0, "total_size_bytes": 0, "formatted_size": "0 B"}

    def list_files(self, prefix: str = "", cursor: Optional[str] = None) -> Dict[str, Any]:
        try:
            kwargs = {"Bucket": self.bucket_name, "Prefix": prefix, "MaxKeys": 100}
            if cursor:
                kwargs["ContinuationToken"] = cursor
            
            resp = self.s3_client.list_objects_v2(**kwargs)
            objects = []
            for item in resp.get("Contents", []):
                objects.append({
                    "key": item["Key"],
                    "size": item["Size"],
                    "last_modified": item["LastModified"].isoformat(),
                    "etag": item.get("ETag", "").strip('"')
                })
            
            next_token = resp.get("NextContinuationToken")
            return {"objects": objects, "next_cursor": next_token}
        except ClientError as e:
            raise self._handle_client_error(e)
        except Exception as e:
            raise StorageError(f"Failed to list S3 objects: {str(e)}", raw_error=e)

    def upload_file(self, file_stream: BinaryIO, object_key: str, content_type: Optional[str] = None) -> Dict[str, Any]:
        try:
            extra_args = {}
            if content_type:
                extra_args["ContentType"] = content_type
                
            self.s3_client.upload_fileobj(file_stream, self.bucket_name, object_key, ExtraArgs=extra_args if extra_args else None)
            
            head = self.get_file_metadata(object_key)
            return {
                "object_key": object_key,
                "size": head["size"],
                "etag": head["etag"],
                "checksum": head["etag"]
            }
        except ClientError as e:
            raise self._handle_client_error(e, key=object_key)
        except Exception as e:
            raise StorageError(f"S3 upload_file failed for '{object_key}': {str(e)}", raw_error=e)

    def get_file_metadata(self, object_key: str) -> Dict[str, Any]:
        try:
            resp = self.s3_client.head_object(Bucket=self.bucket_name, Key=object_key)
            return {
                "object_key": object_key,
                "size": resp["ContentLength"],
                "content_type": resp.get("ContentType", "application/octet-stream"),
                "etag": resp.get("ETag", "").strip('"'),
                "last_modified": resp.get("LastModified").isoformat() if resp.get("LastModified") else ""
            }
        except ClientError as e:
            raise self._handle_client_error(e, key=object_key)
        except Exception as e:
            raise StorageError(f"S3 get_file_metadata failed for '{object_key}': {str(e)}", raw_error=e)

    def download_file(self, object_key: str, range_header: Optional[str] = None) -> Tuple[BinaryIO, Dict[str, Any]]:
        try:
            kwargs = {"Bucket": self.bucket_name, "Key": object_key}
            if range_header:
                kwargs["Range"] = range_header
                
            resp = self.s3_client.get_object(**kwargs)
            body_bytes = resp["Body"].read()
            metadata = {
                "object_key": object_key,
                "size": resp.get("ContentLength", len(body_bytes)),
                "content_type": resp.get("ContentType", "application/octet-stream"),
                "etag": resp.get("ETag", "").strip('"')
            }
            return io.BytesIO(body_bytes), metadata
        except ClientError as e:
            raise self._handle_client_error(e, key=object_key)
        except Exception as e:
            raise StorageError(f"S3 download_file failed for '{object_key}': {str(e)}", raw_error=e)

    def delete_file(self, object_key: str) -> bool:
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=object_key)
            return True
        except ClientError as e:
            raise self._handle_client_error(e, key=object_key)
        except Exception as e:
            raise StorageError(f"S3 delete_file failed for '{object_key}': {str(e)}", raw_error=e)

    def create_folder(self, folder_path: str) -> bool:
        try:
            key = folder_path.strip("/") + "/"
            self.s3_client.put_object(Bucket=self.bucket_name, Key=key, Body=b"")
            return True
        except ClientError as e:
            raise self._handle_client_error(e, key=folder_path)
        except Exception as e:
            raise StorageError(f"S3 create_folder failed for '{folder_path}': {str(e)}", raw_error=e)

    def get_capabilities(self) -> Dict[str, bool]:
        return {
            "read": True,
            "write": True,
            "delete": True,
            "list": True,
            "create_folder": True,
            "range_read": True,
            "presigned_download": True,
            "versioning": True
        }

    # Backward-compatibility aliases
    get_object = download_file
    put_object = upload_file
    delete_object = delete_file
    list_objects = list_files
    head_object = get_file_metadata
    get_storage_metrics = get_storage_usage

