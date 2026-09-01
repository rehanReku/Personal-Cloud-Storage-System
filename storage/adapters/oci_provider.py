import time
import urllib3
from typing import Dict, Any, Optional
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from storage.adapters.aws_provider import AWSStorageProvider

# Disable insecure request warnings when SSL verification is bypassed for OCI S3 endpoints
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class OCIStorageProvider(AWSStorageProvider):
    """
    Oracle Cloud Infrastructure (OCI) Object Storage Provider (S3-Compatible).
    Extends AWSStorageProvider to leverage S3-compatible boto3 API operations.
    Supports OCI S3 Compatibility API endpoints with optional namespace and SSL configuration.
    """
    
    def __init__(self, bucket_name: str, region_name: str = "ap-mumbai-1",
                 oci_access_key: Optional[str] = None,
                 oci_secret_key: Optional[str] = None,
                 oci_namespace: Optional[str] = None,
                 endpoint_url: Optional[str] = None,
                 verify_ssl: bool = False):
        self.oci_access_key = oci_access_key
        self.oci_secret_key = oci_secret_key
        self.oci_namespace = oci_namespace
        self.verify_ssl = verify_ssl
        
        if not endpoint_url:
            if oci_namespace:
                endpoint_url = f"https://{oci_namespace}.compat.objectstorage.{region_name}.oraclecloud.com"
            else:
                endpoint_url = f"https://compat.objectstorage.{region_name}.oraclecloud.com"
                
        self.endpoint_url = endpoint_url

        self.bucket_name = bucket_name
        self.region_name = region_name

        session_kwargs = {
            "region_name": region_name,
            "endpoint_url": endpoint_url,
            "verify": verify_ssl,
            "config": Config(
                s3={"addressing_style": "path"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required"
            )
        }
        if oci_access_key and oci_secret_key:
            session_kwargs["aws_access_key_id"] = oci_access_key
            session_kwargs["aws_secret_access_key"] = oci_secret_key

        self.s3_client = boto3.client("s3", **session_kwargs)

    def health_check(self) -> Dict[str, Any]:
        start = time.time()
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            latency = (time.time() - start) * 1000
            return {
                "status": "healthy",
                "latency_ms": round(latency, 2),
                "message": f"Successfully connected to Oracle Cloud Infrastructure (OCI) Object Storage bucket '{self.bucket_name}' ({self.region_name})",
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
                "message": f"OCI Object Storage health check failed: {str(e)}",
                "code": "error"
            }
