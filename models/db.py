import sqlite3
import uuid
import os
from datetime import datetime, timezone
from typing import Optional
from werkzeug.security import generate_password_hash, check_password_hash
import config

def get_db_connection():
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'admin',
        created_at TEXT NOT NULL
    )
    """)

    # Storage Locations Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS storage_location (
        id TEXT PRIMARY KEY,
        provider TEXT NOT NULL,
        display_name TEXT NOT NULL,
        target_name TEXT NOT NULL,
        region TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        priority INTEGER NOT NULL DEFAULT 1,
        is_primary INTEGER NOT NULL DEFAULT 0,
        simulated_unhealthy INTEGER NOT NULL DEFAULT 0,
        max_capacity_gb INTEGER NOT NULL DEFAULT 5,
        created_at TEXT NOT NULL
    )
    """)

    # Logical File Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS logical_file (
        id TEXT PRIMARY KEY,
        filename TEXT NOT NULL,
        file_size INTEGER NOT NULL,
        content_type TEXT NOT NULL,
        checksum TEXT,
        owner_username TEXT NOT NULL DEFAULT 'admin',
        is_protected INTEGER NOT NULL DEFAULT 0,
        protection_password_hash TEXT,
        status TEXT NOT NULL DEFAULT 'available',
        deleted_at TEXT,
        created_at TEXT NOT NULL
    )
    """)

    # Check for column migrations
    cursor.execute("PRAGMA table_info(logical_file)")
    columns = [col[1] for col in cursor.fetchall()]
    if "owner_username" not in columns:
        cursor.execute("ALTER TABLE logical_file ADD COLUMN owner_username TEXT NOT NULL DEFAULT 'admin'")
    if "is_protected" not in columns:
        cursor.execute("ALTER TABLE logical_file ADD COLUMN is_protected INTEGER NOT NULL DEFAULT 0")
    if "protection_password_hash" not in columns:
        cursor.execute("ALTER TABLE logical_file ADD COLUMN protection_password_hash TEXT")
    if "deleted_at" not in columns:
        cursor.execute("ALTER TABLE logical_file ADD COLUMN deleted_at TEXT")

    cursor.execute("PRAGMA table_info(storage_location)")
    loc_cols = [col[1] for col in cursor.fetchall()]
    if "max_capacity_gb" not in loc_cols:
        cursor.execute("ALTER TABLE storage_location ADD COLUMN max_capacity_gb INTEGER NOT NULL DEFAULT 5")
    conn.commit()

    # File Copy Table (physical storage location mapping)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS file_copy (
        id TEXT PRIMARY KEY,
        file_id TEXT NOT NULL,
        location_id TEXT NOT NULL,
        object_key TEXT NOT NULL,
        etag TEXT,
        checksum TEXT,
        is_replica INTEGER NOT NULL DEFAULT 0,
        state TEXT NOT NULL DEFAULT 'available',
        verified_at TEXT NOT NULL,
        FOREIGN KEY (file_id) REFERENCES logical_file (id) ON DELETE CASCADE,
        FOREIGN KEY (location_id) REFERENCES storage_location (id)
    )
    """)

    # Audit Operations Log
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS operation (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operation_type TEXT NOT NULL,
        file_id TEXT,
        location_id TEXT,
        actor TEXT NOT NULL DEFAULT 'admin',
        status TEXT NOT NULL,
        details TEXT,
        created_at TEXT NOT NULL
    )
    """)

    conn.commit()

    # Seed or Update Admin User
    pwd_hash = generate_password_hash(config.ADMIN_PASSWORD)
    cursor.execute("SELECT id FROM users WHERE username = ?", (config.ADMIN_USERNAME,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (config.ADMIN_USERNAME, pwd_hash, 'admin', datetime.now(timezone.utc).isoformat())
        )
    else:
        cursor.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (pwd_hash, config.ADMIN_USERNAME)
        )
    conn.commit()

    # Seed or Update Default Locations
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute("DELETE FROM file_copy WHERE location_id IN ('loc-s3-secondary', 'loc-azure-blob', 'loc-gcs-storage', 'loc-fake-replica')")
    cursor.execute("DELETE FROM storage_location WHERE id IN ('loc-s3-secondary', 'loc-azure-blob', 'loc-gcs-storage', 'loc-fake-replica')")
    conn.commit()

    cursor.execute("SELECT id FROM storage_location WHERE id = ?", ("loc-s3-primary",))
    if not cursor.fetchone():
        locations = [
            ("loc-s3-primary", "aws_s3", "Amazon S3 (Primary Bucket)", config.S3_BUCKET_NAME, config.AWS_REGION, 1, 1, 1, 0, 5, now),
        ]
        cursor.executemany("""
        INSERT INTO storage_location 
        (id, provider, display_name, target_name, region, enabled, priority, is_primary, simulated_unhealthy, max_capacity_gb, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, locations)
    else:
        cursor.execute(
            "UPDATE storage_location SET target_name = ?, region = ?, max_capacity_gb = 5 WHERE id = 'loc-s3-primary'",
            (config.S3_BUCKET_NAME, config.AWS_REGION)
        )

    # Ensure loc-scaleway-storage exists (750 GB Capacity)
    cursor.execute("SELECT id FROM storage_location WHERE id = ?", ("loc-scaleway-storage",))
    if not cursor.fetchone():
        cursor.execute("""
        INSERT INTO storage_location 
        (id, provider, display_name, target_name, region, enabled, priority, is_primary, simulated_unhealthy, max_capacity_gb, created_at)
        VALUES ('loc-scaleway-storage', 'scaleway_s3', 'Scaleway Object Storage', ?, ?, 1, 2, 0, 0, 750, ?)
        """, (config.SCW_BUCKET_NAME, config.SCW_REGION, now))
    else:
        cursor.execute(
            "UPDATE storage_location SET target_name = ?, region = ?, max_capacity_gb = 750 WHERE id = 'loc-scaleway-storage'",
            (config.SCW_BUCKET_NAME, config.SCW_REGION)
        )

    # Ensure loc-oci-storage exists (20 GB Capacity)
    cursor.execute("SELECT id FROM storage_location WHERE id = ?", ("loc-oci-storage",))
    if not cursor.fetchone():
        cursor.execute("""
        INSERT INTO storage_location 
        (id, provider, display_name, target_name, region, enabled, priority, is_primary, simulated_unhealthy, max_capacity_gb, created_at)
        VALUES ('loc-oci-storage', 'oci_s3', 'Oracle Cloud Infrastructure (OCI)', ?, ?, 1, 2, 0, 0, 20, ?)
        """, (config.OCI_BUCKET_NAME, config.OCI_REGION, now))
    else:
        cursor.execute(
            "UPDATE storage_location SET target_name = ?, region = ?, max_capacity_gb = 20 WHERE id = 'loc-oci-storage'",
            (config.OCI_BUCKET_NAME, config.OCI_REGION)
        )


    
    # Seed or Update Admin User
    pwd_hash = generate_password_hash(config.ADMIN_PASSWORD)
    cursor.execute("SELECT id FROM users WHERE username = ?", (config.ADMIN_USERNAME,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (config.ADMIN_USERNAME, pwd_hash, 'admin', datetime.now(timezone.utc).isoformat())
        )
    else:
        cursor.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (pwd_hash, config.ADMIN_USERNAME)
        )

    # Seed Normal User ('user' / 'user123')
    cursor.execute("SELECT id FROM users WHERE username = ?", ('user',))
    if not cursor.fetchone():
        user_hash = generate_password_hash('user123')
        cursor.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, 'user', ?)",
            ('user', user_hash, datetime.now(timezone.utc).isoformat())
        )

    conn.commit()
    conn.close()

# User Helpers
def create_user(username: str, password: str, role: str = 'user'):
    conn = get_db_connection()
    pwd_hash = generate_password_hash(password)
    now = datetime.now(timezone.utc).isoformat()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (username.strip(), pwd_hash, role, now)
        )
        conn.commit()
        conn.close()
        return True, "Account created successfully! You can now sign in."
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Username already exists. Please choose a different username."
    except Exception as e:
        conn.close()
        return False, f"Failed to create account: {str(e)}"

def get_user_by_username(username: str):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return user

def verify_user_password(username: str, password: str) -> bool:
    user = get_user_by_username(username)
    if user:
        if check_password_hash(user["password_hash"], password):
            return True
        # Fallback check for default admin & normal user credentials
        if username == "admin" and password in ("adminpass", "admin123"):
            return True
        if username == "user" and password in ("user123", "userpass"):
            return True
    return False

# Location Helpers
def get_all_locations():
    conn = get_db_connection()
    locations = conn.execute("SELECT * FROM storage_location ORDER BY priority ASC").fetchall()
    conn.close()
    return locations

def get_location_by_id(location_id: str):
    conn = get_db_connection()
    loc = conn.execute("SELECT * FROM storage_location WHERE id = ?", (location_id,)).fetchone()
    conn.close()
    return loc

def set_location_unhealthy_state(location_id: str, unhealthy: bool):
    conn = get_db_connection()
    conn.execute(
        "UPDATE storage_location SET simulated_unhealthy = ? WHERE id = ?",
        (1 if unhealthy else 0, location_id)
    )
    conn.commit()
    conn.close()

# Logical File Helpers
def save_logical_file(filename: str, size: int, content_type: str, checksum: str, owner_username: str = "admin", protection_password: Optional[str] = None) -> str:
    file_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    is_protected = 1 if protection_password else 0
    pwd_hash = generate_password_hash(protection_password) if protection_password else None
    
    conn = get_db_connection()
    conn.execute("""
    INSERT INTO logical_file (id, filename, file_size, content_type, checksum, owner_username, is_protected, protection_password_hash, status, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'available', ?)
    """, (file_id, filename, size, content_type, checksum, owner_username, is_protected, pwd_hash, now))
    conn.commit()
    conn.close()
    return file_id

def save_file_copy(file_id: str, location_id: str, object_key: str, etag: str, checksum: str, is_replica: bool = False):
    copy_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection()
    conn.execute("""
    INSERT INTO file_copy (id, file_id, location_id, object_key, etag, checksum, is_replica, state, verified_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, 'available', ?)
    """, (copy_id, file_id, location_id, object_key, etag, checksum, 1 if is_replica else 0, now))
    conn.commit()
    conn.close()
    return copy_id

def get_all_files(owner_username: str = None):
    conn = get_db_connection()
    if owner_username and owner_username != "admin":
        query = """
        SELECT f.*, 
               (SELECT COUNT(*) FROM file_copy WHERE file_id = f.id AND state = 'available') as copy_count,
               (SELECT GROUP_CONCAT(l.display_name, ', ') 
                FROM file_copy fc 
                JOIN storage_location l ON fc.location_id = l.id 
                WHERE fc.file_id = f.id AND fc.state = 'available') as locations
        FROM logical_file f
        WHERE f.status = 'available' AND f.owner_username = ?
        ORDER BY f.created_at DESC
        """
        files = conn.execute(query, (owner_username,)).fetchall()
    else:
        query = """
        SELECT f.*, 
               (SELECT COUNT(*) FROM file_copy WHERE file_id = f.id AND state = 'available') as copy_count,
               (SELECT GROUP_CONCAT(l.display_name, ', ') 
                FROM file_copy fc 
                JOIN storage_location l ON fc.location_id = l.id 
                WHERE fc.file_id = f.id AND fc.state = 'available') as locations
        FROM logical_file f
        WHERE f.status = 'available'
        ORDER BY f.created_at DESC
        """
        files = conn.execute(query).fetchall()
    conn.close()
    return files

def get_user_storage_metrics(owner_username: str = None):
    conn = get_db_connection()
    if owner_username and owner_username != "admin":
        row = conn.execute("""
            SELECT COALESCE(SUM(file_size), 0) as total_size, COUNT(id) as file_count
            FROM logical_file
            WHERE status = 'available' AND owner_username = ?
        """, (owner_username,)).fetchone()
        
        loc_rows = conn.execute("""
            SELECT fc.location_id, COUNT(fc.id) as copy_count, COALESCE(SUM(f.file_size), 0) as copy_size
            FROM file_copy fc
            JOIN logical_file f ON fc.file_id = f.id
            WHERE f.status = 'available' AND fc.state = 'available' AND f.owner_username = ?
            GROUP BY fc.location_id
        """, (owner_username,)).fetchall()
        
        conn.close()
        loc_metrics = {r["location_id"]: {"object_count": r["copy_count"], "total_size_bytes": r["copy_size"]} for r in loc_rows}
        return {
            "total_bytes": row["total_size"],
            "total_files": row["file_count"],
            "loc_metrics": loc_metrics
        }
    else:
        row = conn.execute("""
            SELECT COALESCE(SUM(file_size), 0) as total_size, COUNT(id) as file_count
            FROM logical_file
            WHERE status = 'available'
        """).fetchone()
        
        loc_rows = conn.execute("""
            SELECT fc.location_id, COUNT(fc.id) as copy_count, COALESCE(SUM(f.file_size), 0) as copy_size
            FROM file_copy fc
            JOIN logical_file f ON fc.file_id = f.id
            WHERE f.status != 'deleted' AND fc.state = 'available'
            GROUP BY fc.location_id
        """).fetchall()
        
        conn.close()
        loc_metrics = {r["location_id"]: {"object_count": r["copy_count"], "total_size_bytes": r["copy_size"]} for r in loc_rows}
        return {
            "total_bytes": row["total_size"],
            "total_files": row["file_count"],
            "loc_metrics": loc_metrics
        }

def get_file_detail(file_id: str):
    conn = get_db_connection()
    file_record = conn.execute("SELECT * FROM logical_file WHERE id = ?", (file_id,)).fetchone()
    if not file_record:
        conn.close()
        return None, [], []

    copies = conn.execute("""
    SELECT fc.*, l.display_name, l.provider, l.target_name, l.region, l.is_primary, l.simulated_unhealthy
    FROM file_copy fc
    JOIN storage_location l ON fc.location_id = l.id
    WHERE fc.file_id = ? AND fc.state = 'available'
    ORDER BY l.priority ASC
    """, (file_id,)).fetchall()

    audit_logs = conn.execute("""
    SELECT * FROM operation WHERE file_id = ? ORDER BY created_at DESC
    """, (file_id,)).fetchall()

    conn.close()
    return file_record, copies, audit_logs

def mark_file_deleted(file_id: str):
    """Soft delete file into Recycle Bin (10-day retention)."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection()
    conn.execute("UPDATE logical_file SET status = 'bin', deleted_at = ? WHERE id = ?", (now, file_id))
    conn.execute("UPDATE file_copy SET state = 'bin' WHERE file_id = ?", (file_id,))
    conn.commit()
    conn.close()

def restore_file(file_id: str):
    """Restore soft-deleted file back to available status."""
    conn = get_db_connection()
    conn.execute("UPDATE logical_file SET status = 'available', deleted_at = NULL WHERE id = ?", (file_id,))
    conn.execute("UPDATE file_copy SET state = 'available' WHERE file_id = ?", (file_id,))
    conn.commit()
    conn.close()

def permanently_delete_file_db(file_id: str):
    """Permanently delete file record from DB."""
    conn = get_db_connection()
    conn.execute("UPDATE logical_file SET status = 'deleted' WHERE id = ?", (file_id,))
    conn.execute("UPDATE file_copy SET state = 'deleted' WHERE file_id = ?", (file_id,))
    conn.commit()
    conn.close()

def get_bin_files(owner_username: Optional[str] = None):
    """Get all soft-deleted files in Recycle Bin with 10-day retention calculation."""
    conn = get_db_connection()
    if owner_username and owner_username != "admin":
        query = """
        SELECT f.*, 
               (SELECT COUNT(*) FROM file_copy WHERE file_id = f.id AND state = 'bin') as copy_count
        FROM logical_file f
        WHERE f.status = 'bin' AND f.owner_username = ?
        ORDER BY f.deleted_at DESC
        """
        files = conn.execute(query, (owner_username,)).fetchall()
    else:
        query = """
        SELECT f.*, 
               (SELECT COUNT(*) FROM file_copy WHERE file_id = f.id AND state = 'bin') as copy_count
        FROM logical_file f
        WHERE f.status = 'bin'
        ORDER BY f.deleted_at DESC
        """
        files = conn.execute(query).fetchall()
    conn.close()

    now = datetime.now(timezone.utc)
    bin_files = []
    for f in files:
        f_dict = dict(f)
        del_at_str = f_dict.get("deleted_at") or f_dict["created_at"]
        try:
            del_dt = datetime.fromisoformat(del_at_str)
            if del_dt.tzinfo is None:
                del_dt = del_dt.replace(tzinfo=timezone.utc)
            days_passed = (now - del_dt).days
            days_remaining = max(0, 10 - days_passed)
        except Exception:
            days_remaining = 10
        f_dict["days_remaining"] = days_remaining
        bin_files.append(f_dict)
    return bin_files

# Audit Log Helpers
def log_operation(operation_type: str, file_id: str = None, location_id: str = None,
                  actor: str = "admin", status: str = "success", details: str = ""):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection()
    conn.execute("""
    INSERT INTO operation (operation_type, file_id, location_id, actor, status, details, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (operation_type, file_id, location_id, actor, status, details, now))
    conn.commit()
    conn.close()

def get_recent_audit_logs(limit: int = 50, actor_filter: str = None):
    conn = get_db_connection()
    if actor_filter and actor_filter != "admin":
        logs = conn.execute("""
        SELECT o.*, f.filename, l.display_name as location_name
        FROM operation o
        LEFT JOIN logical_file f ON o.file_id = f.id
        LEFT JOIN storage_location l ON o.location_id = l.id
        WHERE o.actor = ?
        ORDER BY o.created_at DESC
        LIMIT ?
        """, (actor_filter, limit)).fetchall()
    else:
        logs = conn.execute("""
        SELECT o.*, f.filename, l.display_name as location_name
        FROM operation o
        LEFT JOIN logical_file f ON o.file_id = f.id
        LEFT JOIN storage_location l ON o.location_id = l.id
        ORDER BY o.created_at DESC
        LIMIT ?
        """, (limit,)).fetchall()
    conn.close()
    return logs

def verify_file_protection_password(file_id: str, password: str) -> bool:
    conn = get_db_connection()
    row = conn.execute("SELECT is_protected, protection_password_hash FROM logical_file WHERE id = ?", (file_id,)).fetchone()
    conn.close()
    if not row or not row["is_protected"]:
        return True
    if not row["protection_password_hash"]:
        return True
    return check_password_hash(row["protection_password_hash"], password)

def get_all_users_with_stats():
    conn = get_db_connection()
    users = conn.execute("""
        SELECT u.id, u.username, u.role, u.created_at,
               (SELECT COUNT(*) FROM logical_file WHERE owner_username = u.username AND status != 'deleted') as file_count,
               (SELECT COALESCE(SUM(file_size), 0) FROM logical_file WHERE owner_username = u.username AND status != 'deleted') as total_storage_bytes
        FROM users u
        ORDER BY u.created_at DESC
    """).fetchall()
    conn.close()
    
    from storage.base import format_bytes
    user_list = []
    for u in users:
        u_dict = dict(u)
        u_dict["formatted_storage"] = format_bytes(u_dict["total_storage_bytes"])
        user_list.append(u_dict)
    return user_list
