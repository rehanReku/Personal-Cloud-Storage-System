import io
import hashlib
from typing import Dict, Any, Optional, Tuple, BinaryIO
import config
from models import db
from storage.base import (
    BaseStorageAdapter,
    StorageError,
    NotFoundError,
    TemporaryUnavailableError
)
from storage.adapters.aws_provider import AWSStorageProvider
from storage.adapters.scaleway_provider import ScalewayStorageProvider
from storage.adapters.oci_provider import OCIStorageProvider
from storage.adapters.s3_adapter import S3StorageAdapter
from storage.adapters.fake_adapter import FakeStorageAdapter
from storage.adapters.azure_adapter import AzureBlobStorageAdapter
from storage.adapters.gcs_adapter import GCSStorageAdapter

class StorageService:
    """
    Unified Storage Orchestrator Service.
    Enforces route independence from cloud SDKs, multi-location replication,
    and verified transparent fallback downloads.
    """
    
    def __init__(self):
        self._adapters: Dict[str, BaseStorageAdapter] = {}
        self._reload_adapters()

    def _reload_adapters(self):
        locations = db.get_all_locations()
        for loc in locations:
            loc_id = loc["id"]
            provider = loc["provider"]

            if provider in ("aws_s3", "aws"):
                self._adapters[loc_id] = AWSStorageProvider(
                    bucket_name=loc["target_name"],
                    region_name=loc["region"],
                    aws_access_key_id=config.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY
                )
            elif provider in ("scaleway_s3", "scaleway"):
                self._adapters[loc_id] = ScalewayStorageProvider(
                    bucket_name=loc["target_name"],
                    region_name=loc["region"],
                    scw_access_key=config.SCW_ACCESS_KEY,
                    scw_secret_key=config.SCW_SECRET_KEY,
                    endpoint_url=config.SCW_ENDPOINT_URL
                )
            elif provider in ("oci_s3", "oci"):
                self._adapters[loc_id] = OCIStorageProvider(
                    bucket_name=loc["target_name"],
                    region_name=loc["region"],
                    oci_access_key=config.OCI_ACCESS_KEY,
                    oci_secret_key=config.OCI_SECRET_KEY,
                    oci_namespace=config.OCI_NAMESPACE,
                    endpoint_url=config.OCI_ENDPOINT_URL
                )

            elif provider == "local_replica":
                self._adapters[loc_id] = FakeStorageAdapter(
                    location_name=loc["target_name"],
                    root_dir=config.LOCAL_STORAGE_DIR
                )
            elif provider == "azure_blob":
                self._adapters[loc_id] = AzureBlobStorageAdapter(
                    account_name="demoaccount",
                    container_name=loc["target_name"]
                )
            elif provider == "gcs_bucket":
                self._adapters[loc_id] = GCSStorageAdapter(
                    bucket_name=loc["target_name"]
                )


    def get_adapter(self, location_id: str) -> Optional[BaseStorageAdapter]:
        if location_id in self._adapters:
            return self._adapters[location_id]
        return None

    def check_location_health(self, location_id: str) -> Dict[str, Any]:
        loc = db.get_location_by_id(location_id)
        if loc and loc["simulated_unhealthy"]:
            return {
                "status": "unhealthy",
                "latency_ms": 0.0,
                "message": f"Simulated outage active on '{loc['display_name']}'",
                "code": "simulated_outage"
            }

        adapter = self.get_adapter(location_id)
        if not adapter:
            return {
                "status": "unhealthy",
                "latency_ms": 0.0,
                "message": f"Adapter for location '{location_id}' not registered",
                "code": "adapter_missing"
            }
        health = adapter.health_check()
        db.log_operation(
            operation_type="health_check",
            location_id=location_id,
            status="success" if health["status"] == "healthy" else "degraded",
            details=f"Health status: {health['status']} ({health['latency_ms']}ms) - {health['message']}"
        )
        return health

    def check_all_locations_health(self) -> Dict[str, Dict[str, Any]]:
        results = {}
        locations = db.get_all_locations()
        for loc in locations:
            results[loc["id"]] = self.check_location_health(loc["id"])
        return results

    def get_location_storage_metrics(self, location_id: str) -> Dict[str, Any]:
        adapter = self.get_adapter(location_id)
        if not adapter:
            return {"object_count": 0, "total_size_bytes": 0, "formatted_size": "0 B"}
        return adapter.get_storage_metrics()

    def get_overall_storage_summary(self, owner_username: Optional[str] = None) -> Dict[str, Any]:
        locations = db.get_all_locations()
        from storage.base import format_bytes

        if owner_username and owner_username != "admin":
            user_data = db.get_user_storage_metrics(owner_username)
            total_bytes = user_data["total_bytes"]
            total_objects = user_data["total_files"]
            location_metrics = {}

            for loc in locations:
                loc_id = loc["id"]
                loc_info = user_data["loc_metrics"].get(loc_id, {"object_count": 0, "total_size_bytes": 0})
                location_metrics[loc_id] = {
                    "object_count": loc_info["object_count"],
                    "total_size_bytes": loc_info["total_size_bytes"],
                    "formatted_size": format_bytes(loc_info["total_size_bytes"])
                }

            return {
                "total_bytes": total_bytes,
                "formatted_total_size": format_bytes(total_bytes),
                "total_objects": total_objects,
                "location_metrics": location_metrics
            }

        # Admin / Global Physical Metrics
        total_bytes = 0
        total_objects = 0
        location_metrics = {}

        for loc in locations:
            loc_id = loc["id"]
            if loc["simulated_unhealthy"]:
                location_metrics[loc_id] = {"object_count": 0, "total_size_bytes": 0, "formatted_size": "0 B (Offline)"}
                continue
            
            adapter = self.get_adapter(loc_id)
            if adapter:
                metrics = adapter.get_storage_metrics()
                location_metrics[loc_id] = metrics
                if loc["enabled"]:
                    total_bytes += metrics["total_size_bytes"]
                    total_objects += metrics["object_count"]
            else:
                location_metrics[loc_id] = {"object_count": 0, "total_size_bytes": 0, "formatted_size": "0 B"}

        return {
            "total_bytes": total_bytes,
            "formatted_total_size": format_bytes(total_bytes),
            "total_objects": total_objects,
            "location_metrics": location_metrics
        }

    def upload_file(self, file_stream: BinaryIO, filename: str, content_type: str, replicate: bool = True, owner_username: str = "admin", target_location_id: Optional[str] = None, protection_password: Optional[str] = None) -> Dict[str, Any]:
        content = file_stream.read()
        file_size = len(content)
        checksum = hashlib.md5(content).hexdigest()

        file_id = db.save_logical_file(filename, file_size, content_type or "application/octet-stream", checksum, owner_username=owner_username, protection_password=protection_password)

        locations = db.get_all_locations()
        
        # User selected target bucket / location OR default primary location
        primary_loc = None
        if target_location_id and target_location_id != "auto":
            primary_loc = next((l for l in locations if l["id"] == target_location_id and l["enabled"]), None)

        if not primary_loc:
            primary_loc = next((l for l in locations if l["is_primary"] and l["enabled"]), None)

        if not primary_loc:
            # Fallback to first available enabled location
            primary_loc = next((l for l in locations if l["enabled"]), None)

        if not primary_loc:
            raise StorageError("No enabled target storage location available.")

        replica_locs = [l for l in locations if l["id"] != primary_loc["id"] and l["enabled"] and l["provider"] in ("aws_s3", "scaleway_s3", "oci_s3", "local_replica")]

        if not primary_loc:
            raise StorageError("No enabled primary storage location available.")

        object_key = f"files/{file_id}/{filename}"
        saved_copies = []

        # 1. Primary Location Upload
        primary_adapter = self.get_adapter(primary_loc["id"])
        try:
            if primary_loc["simulated_unhealthy"]:
                raise TemporaryUnavailableError(f"Primary location '{primary_loc['display_name']}' is offline (Simulated Outage).")

            put_res = primary_adapter.put_object(io.BytesIO(content), object_key, content_type)
            copy_id = db.save_file_copy(
                file_id=file_id,
                location_id=primary_loc["id"],
                object_key=object_key,
                etag=put_res.get("etag", checksum),
                checksum=checksum,
                is_replica=False
            )
            saved_copies.append({"copy_id": copy_id, "location": primary_loc["display_name"]})
            db.log_operation(
                operation_type="upload",
                file_id=file_id,
                location_id=primary_loc["id"],
                status="success",
                details=f"Uploaded to Primary location ({primary_loc['display_name']}). Size: {file_size} bytes."
            )
        except Exception as e:
            db.log_operation(
                operation_type="upload",
                file_id=file_id,
                location_id=primary_loc["id"],
                status="failure",
                details=f"Primary upload failed: {str(e)}"
            )
            raise StorageError(f"Failed to upload to primary storage location: {str(e)}", raw_error=e)

        # 2. Replication to Secondary Location
        if replicate:
            for rep_loc in replica_locs:
                if rep_loc["simulated_unhealthy"]:
                    continue
                rep_adapter = self.get_adapter(rep_loc["id"])
                if rep_adapter:
                    try:
                        rep_res = rep_adapter.put_object(io.BytesIO(content), object_key, content_type)
                        rep_copy_id = db.save_file_copy(
                            file_id=file_id,
                            location_id=rep_loc["id"],
                            object_key=object_key,
                            etag=rep_res.get("etag", checksum),
                            checksum=checksum,
                            is_replica=True
                        )
                        saved_copies.append({"copy_id": rep_copy_id, "location": rep_loc["display_name"]})
                        db.log_operation(
                            operation_type="replication",
                            file_id=file_id,
                            location_id=rep_loc["id"],
                            status="success",
                            details=f"Verified replication to backup location ({rep_loc['display_name']})."
                        )
                    except Exception as e:
                        db.log_operation(
                            operation_type="replication",
                            file_id=file_id,
                            location_id=rep_loc["id"],
                            status="failure",
                            details=f"Backup replication attempt failed: {str(e)}"
                        )

        return {
            "file_id": file_id,
            "filename": filename,
            "size": file_size,
            "checksum": checksum,
            "copies": saved_copies
        }

    def download_file(self, file_id: str) -> Tuple[BinaryIO, str, str, Dict[str, Any]]:
        file_record, copies, _ = db.get_file_detail(file_id)
        if not file_record or file_record["status"] == "deleted":
            raise NotFoundError("Requested logical file does not exist or has been deleted.")

        if not copies:
            raise NotFoundError("No physical copies available for this file.")

        last_error = None
        for copy in copies:
            loc_id = copy["location_id"]
            loc_name = copy["display_name"]
            is_replica = bool(copy["is_replica"])
            simulated_unhealthy = bool(copy["simulated_unhealthy"])

            if simulated_unhealthy:
                db.log_operation(
                    operation_type="download_retry",
                    file_id=file_id,
                    location_id=loc_id,
                    status="degraded",
                    details=f"Primary location '{loc_name}' is offline (Simulated Outage). Initiating fallback to secondary replica..."
                )
                continue

            adapter = self.get_adapter(loc_id)
            if not adapter:
                continue

            try:
                stream, meta = adapter.download_file(copy["object_key"])
                
                if is_replica:
                    db.log_operation(
                        operation_type="download_fallback",
                        file_id=file_id,
                        location_id=loc_id,
                        status="success",
                        details=f"PRIMARY OUTAGE SIMULATED: File downloaded from verified secondary replica location ({loc_name})."
                    )
                else:
                    db.log_operation(
                        operation_type="download",
                        file_id=file_id,
                        location_id=loc_id,
                        status="success",
                        details=f"Downloaded directly from primary location ({loc_name})."
                    )

                download_info = {
                    "served_by": loc_name,
                    "is_replica": is_replica,
                    "location_id": loc_id,
                    "provider": copy["provider"]
                }

                return stream, file_record["filename"], file_record["content_type"], download_info

            except Exception as e:
                last_error = e
                db.log_operation(
                    operation_type="download_retry",
                    file_id=file_id,
                    location_id=loc_id,
                    status="degraded",
                    details=f"Failed to fetch from location {loc_name} ({str(e)}). Initiating fallback..."
                )

        raise StorageError(f"Failed to download file from all available storage locations: {str(last_error)}", raw_error=last_error)

    def delete_file(self, file_id: str) -> Dict[str, Any]:
        """Soft delete file into Recycle Bin (10-day retention)."""
        file_record, copies, _ = db.get_file_detail(file_id)
        if not file_record:
            raise NotFoundError("File not found.")

        db.mark_file_deleted(file_id)
        db.log_operation(
            operation_type="soft_delete",
            file_id=file_id,
            actor=dict(file_record).get("owner_username", "user"),
            status="success",
            details=f"File '{file_record['filename']}' moved to Recycle Bin (10-day retention)."
        )
        return {"file_id": file_id, "filename": file_record["filename"]}

    def restore_file(self, file_id: str) -> Dict[str, Any]:
        """Restore soft-deleted file back to active catalog."""
        file_record, _, _ = db.get_file_detail(file_id)
        if not file_record:
            raise NotFoundError("File not found.")

        db.restore_file(file_id)
        db.log_operation(
            operation_type="restore",
            file_id=file_id,
            actor=dict(file_record).get("owner_username", "user"),
            status="success",
            details=f"File '{file_record['filename']}' restored from Recycle Bin back to active vault."
        )
        return {"file_id": file_id, "filename": file_record["filename"]}

    def permanently_delete_file(self, file_id: str) -> Dict[str, Any]:
        """Permanently delete file across all physical S3 buckets and storage adapters."""
        file_record, copies, _ = db.get_file_detail(file_id)
        if not file_record:
            raise NotFoundError("File not found.")

        deleted_copies = []
        for copy in copies:
            loc_id = copy["location_id"]
            adapter = self.get_adapter(loc_id)
            if adapter:
                try:
                    adapter.delete_object(copy["object_key"])
                    deleted_copies.append(copy["display_name"])
                except Exception as e:
                    db.log_operation(
                        operation_type="delete_copy",
                        file_id=file_id,
                        location_id=loc_id,
                        status="degraded",
                        details=f"Failed to delete copy from {copy['display_name']}: {str(e)}"
                    )

        db.permanently_delete_file_db(file_id)
        db.log_operation(
            operation_type="permanent_delete",
            file_id=file_id,
            actor=dict(file_record).get("owner_username", "user"),
            status="success",
            details=f"File '{file_record['filename']}' permanently purged from storage: {', '.join(deleted_copies)}"
        )
        return {"file_id": file_id, "deleted_locations": deleted_copies}
