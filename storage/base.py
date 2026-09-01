import abc
from typing import Dict, Any, Optional, Tuple, BinaryIO

class StorageError(Exception):
    """Base exception for all storage operations."""
    def __init__(self, message: str, code: str = "storage_error", raw_error: Optional[Exception] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.raw_error = raw_error

class NotFoundError(StorageError):
    def __init__(self, message: str = "Requested object not found", raw_error: Optional[Exception] = None):
        super().__init__(message, code="not_found", raw_error=raw_error)

class AuthenticationError(StorageError):
    def __init__(self, message: str = "Storage authentication failed", raw_error: Optional[Exception] = None):
        super().__init__(message, code="authentication_failed", raw_error=raw_error)

class PermissionDeniedError(StorageError):
    def __init__(self, message: str = "Permission denied for storage location", raw_error: Optional[Exception] = None):
        super().__init__(message, code="permission_denied", raw_error=raw_error)

class TemporaryUnavailableError(StorageError):
    def __init__(self, message: str = "Storage location temporarily unavailable", raw_error: Optional[Exception] = None):
        super().__init__(message, code="temporary_unavailable", raw_error=raw_error)

def format_bytes(size: float) -> str:
    if size <= 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"

class StorageProvider(abc.ABC):
    """Abstract storage provider interface for object storage providers (AWS S3, Scaleway Object Storage, etc.)."""
    
    @abc.abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """
        Check connectivity and health of the storage location.
        Returns:
            dict: {
                "status": "healthy" | "degraded" | "unhealthy",
                "latency_ms": float,
                "message": str,
                "code": str
            }
        """
        pass

    def get_storage_usage(self) -> Dict[str, Any]:
        """Calculate total storage usage and object count for the storage location."""
        if type(self).get_storage_metrics != StorageProvider.get_storage_metrics:
            return self.get_storage_metrics()
        raise NotImplementedError("Storage provider must implement get_storage_usage or get_storage_metrics.")

    def get_storage_metrics(self) -> Dict[str, Any]:
        """Alias for get_storage_usage for backward compatibility."""
        if type(self).get_storage_usage != StorageProvider.get_storage_usage:
            return self.get_storage_usage()
        return {"object_count": 0, "total_size_bytes": 0, "formatted_size": "0 B"}

    def list_files(self, prefix: str = "", cursor: Optional[str] = None) -> Dict[str, Any]:
        """List objects/files in the storage location under prefix."""
        if type(self).list_objects != StorageProvider.list_objects:
            return self.list_objects(prefix=prefix, cursor=cursor)
        raise NotImplementedError("Storage provider must implement list_files or list_objects.")

    def list_objects(self, prefix: str = "", cursor: Optional[str] = None) -> Dict[str, Any]:
        """Alias for list_files for backward compatibility."""
        if type(self).list_files != StorageProvider.list_files:
            return self.list_files(prefix=prefix, cursor=cursor)
        return {"objects": [], "next_cursor": None}

    def upload_file(self, file_stream: BinaryIO, object_key: str, content_type: Optional[str] = None) -> Dict[str, Any]:
        """Upload object data."""
        if type(self).put_object != StorageProvider.put_object:
            return self.put_object(file_stream, object_key, content_type)
        raise NotImplementedError("Storage provider must implement upload_file or put_object.")

    def put_object(self, file_stream: BinaryIO, object_key: str, content_type: Optional[str] = None) -> Dict[str, Any]:
        """Alias for upload_file for backward compatibility."""
        if type(self).upload_file != StorageProvider.upload_file:
            return self.upload_file(file_stream, object_key, content_type)
        raise NotImplementedError("Storage provider must implement upload_file or put_object.")

    def get_file_metadata(self, object_key: str) -> Dict[str, Any]:
        """Retrieve object metadata."""
        if type(self).head_object != StorageProvider.head_object:
            return self.head_object(object_key)
        raise NotImplementedError("Storage provider must implement get_file_metadata or head_object.")

    def head_object(self, object_key: str) -> Dict[str, Any]:
        """Alias for get_file_metadata for backward compatibility."""
        if type(self).get_file_metadata != StorageProvider.get_file_metadata:
            return self.get_file_metadata(object_key)
        raise NotImplementedError("Storage provider must implement get_file_metadata or head_object.")

    def download_file(self, object_key: str, range_header: Optional[str] = None) -> Tuple[BinaryIO, Dict[str, Any]]:
        """Retrieve object data stream and headers."""
        if type(self).get_object != StorageProvider.get_object:
            return self.get_object(object_key, range_header)
        raise NotImplementedError("Storage provider must implement download_file or get_object.")

    def get_object(self, object_key: str, range_header: Optional[str] = None) -> Tuple[BinaryIO, Dict[str, Any]]:
        """Alias for download_file for backward compatibility."""
        if type(self).download_file != StorageProvider.download_file:
            return self.download_file(object_key, range_header)
        raise NotImplementedError("Storage provider must implement download_file or get_object.")

    def delete_file(self, object_key: str) -> bool:
        """Delete object."""
        if type(self).delete_object != StorageProvider.delete_object:
            return self.delete_object(object_key)
        raise NotImplementedError("Storage provider must implement delete_file or delete_object.")

    def delete_object(self, object_key: str) -> bool:
        """Alias for delete_file for backward compatibility."""
        if type(self).delete_file != StorageProvider.delete_file:
            return self.delete_file(object_key)
        raise NotImplementedError("Storage provider must implement delete_file or delete_object.")


    def create_folder(self, folder_path: str) -> bool:
        """Create a virtual folder / prefix in object storage."""
        return True

    @abc.abstractmethod
    def get_capabilities(self) -> Dict[str, bool]:
        """
        Return dictionary of supported features (e.g. range_read, presigned_urls, versioning).
        """
        pass


# Backward compatibility alias
BaseStorageAdapter = StorageProvider

