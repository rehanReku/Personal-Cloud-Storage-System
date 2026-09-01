import os
import sys
import glob

# Ensure project virtualenv packages are accessible if app is launched with system python3
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
venv_site_packages = glob.glob(os.path.join(BASE_DIR, "venv", "lib", "python*", "site-packages"))
for site_pkg in venv_site_packages:
    if site_pkg not in sys.path:
        sys.path.insert(0, site_pkg)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass



BASE_DIR = os.path.abspath(os.path.dirname(__file__))

SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-multicloud-storage-2026")
DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "multicloud_storage.db"))

# Primary AWS S3 configuration
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "endsemproj")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

# Scaleway Object Storage configuration
SCW_ACCESS_KEY = os.getenv("SCW_ACCESS_KEY")
SCW_SECRET_KEY = os.getenv("SCW_SECRET_KEY")
SCW_REGION = os.getenv("SCW_REGION", os.getenv("SCW_DEFAULT_REGION", "fr-par"))
SCW_BUCKET_NAME = os.getenv("SCW_BUCKET_NAME", os.getenv("SCW_BUCKET", "scaleway-cloud-storage"))
SCW_ENDPOINT_URL = os.getenv("SCW_ENDPOINT_URL", f"https://s3.{SCW_REGION}.scw.cloud")

# Oracle Cloud Infrastructure (OCI) Object Storage configuration
OCI_ACCESS_KEY = os.getenv("OCI_ACCESS_KEY")
OCI_SECRET_KEY = os.getenv("OCI_SECRET_KEY")
OCI_REGION = os.getenv("OCI_REGION", "ap-hyderabad-1")
OCI_NAMESPACE = os.getenv("OCI_NAMESPACE")
OCI_BUCKET_NAME = os.getenv("OCI_BUCKET_NAME", "oci-storage-bucket")
OCI_ENDPOINT_URL = os.getenv("OCI_ENDPOINT_URL")




# Single Owner Credentials
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "adminpass")

# Local Storage Directory for Fake / Local Backup Adapter
LOCAL_STORAGE_DIR = os.path.join(BASE_DIR, "local_storage_data")
os.makedirs(LOCAL_STORAGE_DIR, exist_ok=True)
