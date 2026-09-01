import io
import unittest
import config
from app import app
from models import db
from storage.base import StorageProvider
from storage.service import StorageService
from storage.adapters.aws_provider import AWSStorageProvider
from storage.adapters.scaleway_provider import ScalewayStorageProvider
from storage.adapters.oci_provider import OCIStorageProvider
from storage.adapters.fake_adapter import FakeStorageAdapter

class TestMultiCloudStorage(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

        with self.app.session_transaction() as sess:
            sess['user'] = 'admin'

        db.init_db()
        db.set_location_unhealthy_state("loc-s3-primary", False)
        db.set_location_unhealthy_state("loc-scaleway-storage", False)
        db.set_location_unhealthy_state("loc-oci-storage", False)
        self.service = StorageService()

        # Wire up mock storage adapters for deterministic local unit testing
        fake_primary = FakeStorageAdapter("s3-primary-vault", root_dir=config.LOCAL_STORAGE_DIR)
        fake_scaleway = FakeStorageAdapter("scaleway-obj-store", root_dir=config.LOCAL_STORAGE_DIR)
        fake_oci = FakeStorageAdapter("oci-obj-store", root_dir=config.LOCAL_STORAGE_DIR)
        
        self.service._adapters["loc-s3-primary"] = fake_primary
        self.service._adapters["loc-scaleway-storage"] = fake_scaleway
        self.service._adapters["loc-oci-storage"] = fake_oci

    def test_provider_inheritance_and_interface(self):
        print("\n[TEST] Verifying StorageProvider abstraction layer hierarchy...")
        aws_provider = AWSStorageProvider(
            bucket_name="test-aws-bucket",
            region_name="ap-south-1",
            aws_access_key_id="test_key",
            aws_secret_access_key="test_secret"
        )
        scaleway_provider = ScalewayStorageProvider(
            bucket_name="test-scw-bucket",
            region_name="fr-par",
            scw_access_key="test_scw_key",
            scw_secret_key="test_scw_secret"
        )
        oci_provider = OCIStorageProvider(
            bucket_name="test-oci-bucket",
            region_name="ap-mumbai-1",
            oci_access_key="test_oci_key",
            oci_secret_key="test_oci_secret"
        )

        self.assertIsInstance(aws_provider, StorageProvider)
        self.assertIsInstance(scaleway_provider, StorageProvider)
        self.assertIsInstance(scaleway_provider, AWSStorageProvider)
        self.assertIsInstance(oci_provider, StorageProvider)
        self.assertIsInstance(oci_provider, AWSStorageProvider)
        self.assertEqual(scaleway_provider.endpoint_url, "https://s3.fr-par.scw.cloud")
        self.assertEqual(oci_provider.endpoint_url, "https://compat.objectstorage.ap-mumbai-1.oraclecloud.com")
        print("-> Hierarchy verified: ScalewayStorageProvider, OCIStorageProvider -> AWSStorageProvider -> StorageProvider")

    def test_upload_replicate_and_fallback_download(self):
        print("\n[TEST] 1. Uploading test file with multi-cloud replication...")
        file_content = b"Hello, Multi-Cloud World! AWS S3, Scaleway, and OCI unified test."
        file_stream = io.BytesIO(file_content)

        upload_res = self.service.upload_file(
            file_stream=file_stream,
            filename="multicloud_demo.txt",
            content_type="text/plain",
            replicate=True
        )

        file_id = upload_res["file_id"]
        self.assertIsNotNone(file_id)
        self.assertGreaterEqual(len(upload_res["copies"]), 2)
        print(f"-> Uploaded successfully. Logical File ID: {file_id}")
        print(f"-> Physical copies created across locations: {upload_res['copies']}")

        # Test normal download (Primary)
        print("\n[TEST] 2. Downloading file when Primary is ONLINE...")
        stream, filename, ctype, download_info = self.service.download_file(file_id)
        self.assertEqual(stream.read(), file_content)
        self.assertFalse(download_info["is_replica"])
        print(f"-> Downloaded directly from: {download_info['served_by']} (Is Replica: {download_info['is_replica']})")

        # Simulate Primary Outage
        print("\n[TEST] 3. Simulating primary storage location outage...")
        locations = db.get_all_locations()
        primary_loc = next(l for l in locations if l["is_primary"])
        db.set_location_unhealthy_state(primary_loc["id"], True)

        # Test Transparent Fallback Download (Replica)
        print("\n[TEST] 4. Downloading file when Primary has SIMULATED OUTAGE...")
        stream_rep, filename_rep, ctype_rep, download_info_rep = self.service.download_file(file_id)
        self.assertEqual(stream_rep.read(), file_content)
        self.assertTrue(download_info_rep["is_replica"])
        print(f"-> SUCCESS! Transparent Fallback Download served by: {download_info_rep['served_by']} (Is Replica: {download_info_rep['is_replica']})")

        # Restore online state
        db.set_location_unhealthy_state(primary_loc["id"], False)

        # Check Audit Logs
        print("\n[TEST] 5. Verifying audit logs for fallback events...")
        logs = db.get_recent_audit_logs(limit=10)
        has_fallback_log = any("download_fallback" in l["operation_type"] or "PRIMARY OUTAGE" in l["details"] for l in logs)
        self.assertTrue(has_fallback_log)
        print("-> Audit logs confirmed. Verified fallback event recorded.")

if __name__ == '__main__':
    unittest.main()
