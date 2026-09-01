import os
import io
import time
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, BinaryIO

from storage.base import (
    BaseStorageAdapter,
    StorageError,
    NotFoundError,
    TemporaryUnavailableError
)

class FakeStorageAdapter(BaseStorageAdapter):
    """
    Local filesystem-backed or in-memory mock storage adapter.
    Used for local testing, backup replication, and zero-cost local demonstrations.
    """
    
    def __init__(self, location_name: str, root_dir: str, simulated_unhealthy: bool = False):
        self.location_name = location_name
        self.root_dir = os.path.join(root_dir, location_name)
        os.makedirs(self.root_dir, exist_ok=True)
        self.simulated_unhealthy = simulated_unhealthy

    def set_simulated_unhealthy(self, unhealthy: bool):
        """Simulate primary location outage for fallback testing."""
        self.simulated_unhealthy = unhealthy

    def health_check(self) -> Dict[str, Any]:
        start = time.time()
        time.sleep(0.01) # slight latency simulation
        latency = (time.time() - start) * 1000
        
        if self.simulated_unhealthy:
            return {
                "status": "unhealthy",
                "latency_ms": round(latency, 2),
                "message": f"Simulated outage on storage location '{self.location_name}'",
                "code": "simulated_outage"
            }
        
        return {
            "status": "healthy",
            "latency_ms": round(latency, 2),
            "message": f"Fake storage location '{self.location_name}' active at {self.root_dir}",
            "code": "ok"
        }

    def get_storage_metrics(self) -> Dict[str, Any]:
        total_size = 0
        count = 0
        for root, _, files in os.walk(self.root_dir):
            for file in files:
                full_path = os.path.join(root, file)
                total_size += os.path.getsize(full_path)
                count += 1
        from storage.base import format_bytes
        return {
            "object_count": count,
            "total_size_bytes": total_size,
            "formatted_size": format_bytes(total_size)
        }

    def list_objects(self, prefix: str = "", cursor: Optional[str] = None) -> Dict[str, Any]:
        if self.simulated_unhealthy:
            raise TemporaryUnavailableError(f"Location '{self.location_name}' is currently offline (Simulated Outage).")
            
        objects = []
        for root, _, files in os.walk(self.root_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, self.root_dir).replace("\\", "/")
                if rel_path.startswith(prefix):
                    stat = os.stat(full_path)
                    with open(full_path, "rb") as f:
                        etag = hashlib.md5(f.read()).hexdigest()
                    objects.append({
                        "key": rel_path,
                        "size": stat.st_size,
                        "last_modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                        "etag": etag
                    })
        return {"objects": objects, "next_cursor": None}

    def put_object(self, file_stream: BinaryIO, object_key: str, content_type: Optional[str] = None) -> Dict[str, Any]:
        if self.simulated_unhealthy:
            raise TemporaryUnavailableError(f"Location '{self.location_name}' is currently offline (Simulated Outage).")
            
        dest_path = os.path.join(self.root_dir, object_key)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        
        content = file_stream.read()
        with open(dest_path, "wb") as f:
            f.write(content)
            
        checksum = hashlib.md5(content).hexdigest()
        return {
            "object_key": object_key,
            "size": len(content),
            "etag": checksum,
            "checksum": checksum
        }

    def head_object(self, object_key: str) -> Dict[str, Any]:
        if self.simulated_unhealthy:
            raise TemporaryUnavailableError(f"Location '{self.location_name}' is currently offline (Simulated Outage).")
            
        dest_path = os.path.join(self.root_dir, object_key)
        if not os.path.exists(dest_path):
            raise NotFoundError(f"Object '{object_key}' not found in location '{self.location_name}'.")
            
        stat = os.stat(dest_path)
        with open(dest_path, "rb") as f:
            checksum = hashlib.md5(f.read()).hexdigest()
            
        return {
            "object_key": object_key,
            "size": stat.st_size,
            "content_type": "application/octet-stream",
            "etag": checksum,
            "last_modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
        }

    def get_object(self, object_key: str, range_header: Optional[str] = None) -> Tuple[BinaryIO, Dict[str, Any]]:
        if self.simulated_unhealthy:
            raise TemporaryUnavailableError(f"Location '{self.location_name}' is currently offline (Simulated Outage).")
            
        dest_path = os.path.join(self.root_dir, object_key)
        if not os.path.exists(dest_path):
            raise NotFoundError(f"Object '{object_key}' not found in location '{self.location_name}'.")
            
        with open(dest_path, "rb") as f:
            content = f.read()
            
        checksum = hashlib.md5(content).hexdigest()
        metadata = {
            "object_key": object_key,
            "size": len(content),
            "content_type": "application/octet-stream",
            "etag": checksum
        }
        return io.BytesIO(content), metadata

    def delete_object(self, object_key: str) -> bool:
        if self.simulated_unhealthy:
            raise TemporaryUnavailableError(f"Location '{self.location_name}' is currently offline (Simulated Outage).")
            
        dest_path = os.path.join(self.root_dir, object_key)
        if os.path.exists(dest_path):
            os.remove(dest_path)
        return True

    def get_capabilities(self) -> Dict[str, bool]:
        return {
            "read": True,
            "write": True,
            "delete": True,
            "list": True,
            "range_read": True,
            "presigned_download": False,
            "versioning": False
        }
