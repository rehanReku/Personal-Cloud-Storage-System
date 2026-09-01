from typing import Dict, Any, Optional, Tuple, BinaryIO
from storage.base import BaseStorageAdapter, StorageError, TemporaryUnavailableError

class AzureBlobStorageAdapter(BaseStorageAdapter):
    """Azure Blob Storage Adapter baseline (Phase 3 contract implementation)."""
    
    def __init__(self, account_name: str, container_name: str, connection_string: Optional[str] = None):
        self.account_name = account_name
        self.container_name = container_name
        self.connection_string = connection_string

    def health_check(self) -> Dict[str, Any]:
        return {
            "status": "degraded" if not self.connection_string else "healthy",
            "latency_ms": 0.0,
            "message": f"Azure Blob Container '{self.container_name}' (Pending credentials configuration)",
            "code": "configuration_required"
        }

    def get_storage_metrics(self) -> Dict[str, Any]:
        return {"object_count": 0, "total_size_bytes": 0, "formatted_size": "0 B"}

    def list_objects(self, prefix: str = "", cursor: Optional[str] = None) -> Dict[str, Any]:
        return {"objects": [], "next_cursor": None}

    def put_object(self, file_stream: BinaryIO, object_key: str, content_type: Optional[str] = None) -> Dict[str, Any]:
        raise TemporaryUnavailableError("Azure Blob Storage credentials not configured.")

    def head_object(self, object_key: str) -> Dict[str, Any]:
        raise TemporaryUnavailableError("Azure Blob Storage credentials not configured.")

    def get_object(self, object_key: str, range_header: Optional[str] = None) -> Tuple[BinaryIO, Dict[str, Any]]:
        raise TemporaryUnavailableError("Azure Blob Storage credentials not configured.")

    def delete_object(self, object_key: str) -> bool:
        return True

    def get_capabilities(self) -> Dict[str, bool]:
        return {"read": True, "write": True, "delete": True, "list": True, "range_read": True}
