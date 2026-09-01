import time
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError

from storage.adapters.aws_provider import AWSStorageProvider

class ScalewayStorageProvider(AWSStorageProvider):
    """
    Scaleway Object Storage Provider (S3-Compatible).
    Extends AWSStorageProvider to reuse S3-compatible boto3 operations without code duplication.
    Reads credentials from SCW_ACCESS_KEY and SCW_SECRET_KEY.
    """
    
    def __init__(self, bucket_name: str, region_name: str = "fr-par",
                 scw_access_key: Optional[str] = None,
                 scw_secret_key: Optional[str] = None,
                 endpoint_url: Optional[str] = None):
        self.scw_access_key = scw_access_key
        self.scw_secret_key = scw_secret_key
        
        if not endpoint_url:
            endpoint_url = f"https://s3.{region_name}.scw.cloud"
        self.endpoint_url = endpoint_url

        super().__init__(
            bucket_name=bucket_name,
            region_name=region_name,
            aws_access_key_id=scw_access_key,
            aws_secret_access_key=scw_secret_key,
            endpoint_url=endpoint_url
        )

    def health_check(self) -> Dict[str, Any]:
        start = time.time()
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            latency = (time.time() - start) * 1000
            return {
                "status": "healthy",
                "latency_ms": round(latency, 2),
                "message": f"Successfully connected to Scaleway Object Storage bucket '{self.bucket_name}' ({self.region_name})",
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
                "message": f"Scaleway Object Storage health check failed: {str(e)}",
                "code": "error"
            }
