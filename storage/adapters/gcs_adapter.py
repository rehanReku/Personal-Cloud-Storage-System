from typing import Dict, Any, Optional, Tuple, BinaryIO
from storage.base import BaseStorageAdapter, StorageError, TemporaryUnavailableError

class GCSStorageAdapter(BaseStorageAdapter):
    """Google Cloud Storage Adapter baseline (Phase 3 contract implementation)."""
    
    def __init__(self, bucket_name: str, project_id: str = "demo-project"):
        self.bucket_name = bucket_name
        self.project_id = project_id

    def health_check(self) -> Dict[str, Any]:
        return {
            "status": "degraded",
            "latency_ms": 0.0,
            "message": f"Google Cloud Storage bucket '{self.bucket_name}' (Pending GCS service account key)",
            "code": "configuration_required"
        }

    def get_storage_metrics(self) -> Dict[str, Any]:
        return {"object_count": 0, "total_size_bytes": 0, "formatted_size": "0 B"}

    def list_objects(self, prefix: str = "", cursor: Optional[str] = None) -> Dict[str, Any]:
        return {"objects": [], "next_cursor": None}

    def put_object(self, file_stream: BinaryIO, object_key: str, content_type: Optional[str] = None) -> Dict[str, Any]:
        raise TemporaryUnavailableError("GCS credentials not configured.")

    def head_object(self, object_key: str) -> Dict[str, Any]:
        raise TemporaryUnavailableError("GCS credentials not configured.")

    def get_object(self, object_key: str, range_header: Optional[str] = None) -> Tuple[BinaryIO, Dict[str, Any]]:
        raise TemporaryUnavailableError("GCS credentials not configured.")

    def delete_object(self, object_key: str) -> bool:
        return True

    def get_capabilities(self) -> Dict[str, bool]:
        return {"read": True, "write": True, "delete": True, "list": True, "range_read": True}
