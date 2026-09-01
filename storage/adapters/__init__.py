from storage.base import StorageProvider
from storage.adapters.aws_provider import AWSStorageProvider
from storage.adapters.scaleway_provider import ScalewayStorageProvider
from storage.adapters.oci_provider import OCIStorageProvider
from storage.adapters.s3_adapter import S3StorageAdapter

__all__ = [
    "StorageProvider",
    "AWSStorageProvider",
    "ScalewayStorageProvider",
    "OCIStorageProvider",
    "S3StorageAdapter"
]
