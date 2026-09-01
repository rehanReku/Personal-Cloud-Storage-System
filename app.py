import os
from functools import wraps
from flask import (
    Flask, request, render_template, redirect, url_for,
    flash, session, send_file, jsonify
)

import config
from models import db
from storage.service import StorageService

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# Initialize Database Schema & Seed Locations
db.init_db()

# Initialize Storage Service Orchestrator (No boto3 or AWS SDK in Web Routes!)
storage_service = StorageService()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Authentication Routes
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "user")

        if not username or not password:
            flash("Username and password are required.", "error")
            return render_template("register.html")

        success, msg = db.create_user(username, password, role)
        if success:
            session["user"] = username
            session["role"] = role
            flash(f"Account '{username}' created successfully! Welcome to CloudVault.", "success")
            return redirect(url_for("index"))
        else:
            flash(msg, "error")

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if db.verify_user_password(username, password):
            user_record = db.get_user_by_username(username)
            role = user_record["role"] if user_record else ("admin" if username == "admin" else "user")
            session["user"] = username
            session["role"] = role
            flash(f"Welcome back, {username} ({role})!", "success")
            return redirect(url_for("index"))
        else:
            flash("Invalid username or password.", "error")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("role", None)
    flash("Signed out successfully.", "info")
    return redirect(url_for("login"))

# Main Dashboard Route (Files Catalog & Overview)
@app.route("/", methods=["GET"])
@login_required
def index():
    # Auto re-lock all protected files whenever user returns to or reloads the main dashboard
    for k in list(session.keys()):
        if k.startswith("unlocked_"):
            session.pop(k, None)

    user = session.get("user")
    files = db.get_all_files(owner_username=user)
    locations = db.get_all_locations()
    health_status = storage_service.check_all_locations_health()
    storage_summary = storage_service.get_overall_storage_summary(owner_username=user)
    return render_template("index.html", files=files, locations=locations, health_status=health_status, storage_summary=storage_summary)

# Locations & Outage Simulation Management
@app.route("/locations", methods=["GET"])
@login_required
def view_locations():
    user = session.get("user")
    locations = db.get_all_locations()
    health_results = storage_service.check_all_locations_health()
    storage_summary = storage_service.get_overall_storage_summary(owner_username=user)
    return render_template("locations.html", locations=locations, health_results=health_results, storage_summary=storage_summary)

# File Upload Route
@app.route("/upload", methods=["POST"])
@login_required
def upload_file_route():
    if "file" not in request.files:
        flash("No file part provided in request.", "error")
        return redirect(url_for("index"))

    file = request.files["file"]
    if file.filename == "":
        flash("No selected file.", "error")
        return redirect(url_for("index"))

    replicate = request.form.get("replicate") == "true"
    target_location_id = request.form.get("target_location_id", "auto")
    protection_password = request.form.get("protection_password", "").strip() or None
    user = session.get("user", "admin")

    try:
        res = storage_service.upload_file(
            file_stream=file.stream,
            filename=file.filename,
            content_type=file.content_type,
            replicate=replicate,
            owner_username=user,
            target_location_id=target_location_id,
            protection_password=protection_password
        )
        flash(f"File '{file.filename}' uploaded successfully to Cloud Vault across {len(res['copies'])} location(s)!", "success")
    except Exception as e:
        flash(f"Error uploading file: {str(e)}", "error")

    return redirect(url_for("index"))

# File Detail Route
@app.route("/files/<file_id>", methods=["GET"])
@login_required
def view_file_detail(file_id):
    file_record, copies, audit_logs = db.get_file_detail(file_id)
    if not file_record:
        flash("Requested file not found.", "error")
        return redirect(url_for("index"))

    user = session.get("user")
    role = session.get("role", "user")
    if file_record["owner_username"] != user and role != "admin":
        flash("Access denied: You do not have permission to view this file.", "error")
        return redirect(url_for("index"))

    # Strict Privacy Enforcement: Require protection password unlock for ALL users (including Admin)
    file_dict = dict(file_record)
    if file_dict.get("is_protected") and not session.get(f"unlocked_{file_id}"):
        flash("🔒 Privacy Lock: Enter file protection password to view file details.", "warning")
        return redirect(url_for("index"))

    return render_template(
        "file_detail.html",
        file=file_record,
        copies=copies,
        audit_logs=audit_logs
    )

# Download File Route (Supports Transparent Verified Fallback & Password Protection!)
@app.route("/files/<file_id>/download", methods=["GET"])
@login_required
def download_file_route(file_id):
    file_record, _, _ = db.get_file_detail(file_id)
    if not file_record:
        flash("File not found.", "error")
        return redirect(url_for("index"))

    user = session.get("user")
    role = session.get("role", "user")
    file_dict = dict(file_record)
    if file_dict["owner_username"] != user and role != "admin":
        flash("Access denied: You do not have permission to download this file.", "error")
        return redirect(url_for("index"))

    # Strict Privacy & Password Secrecy (Admin cannot bypass without user password)
    if file_dict.get("is_protected") and not session.get(f"unlocked_{file_id}"):
        flash("🔒 Privacy Lock: Enter file protection password to download this file.", "error")
        return redirect(url_for("index"))

    try:
        stream, filename, content_type, download_info = storage_service.download_file(file_id)

        if download_info["is_replica"]:
            flash(f"⚠️ PRIMARY OUTAGE: File served via secondary backup replica ({download_info['served_by']}).", "warning")
        
        return send_file(
            stream,
            download_name=filename,
            mimetype=content_type or "application/octet-stream",
            as_attachment=True
        )

    except Exception as e:
        flash(f"Download failed: {str(e)}", "error")
        return redirect(url_for("view_file_detail", file_id=file_id))

# Delete File Route (Soft Delete into Recycle Bin)
@app.route("/files/<file_id>/delete", methods=["POST"])
@login_required
def delete_file_route(file_id):
    file_record, _, _ = db.get_file_detail(file_id)
    if not file_record:
        flash("File not found.", "error")
        return redirect(url_for("index"))

    user = session.get("user")
    role = session.get("role", "user")
    if file_record["owner_username"] != user and role != "admin":
        flash("Access denied: You do not have permission to delete this file.", "error")
        return redirect(url_for("index"))

    try:
        storage_service.delete_file(file_id)
        flash(f"🗑️ File '{file_record['filename']}' moved to Recycle Bin (10-day retention).", "success")
    except Exception as e:
        flash(f"Failed to delete file: {str(e)}", "error")

    return redirect(url_for("index"))

# Recycle Bin Management Routes (10-Day Retention & Retrieval)
@app.route("/bin", methods=["GET"])
@login_required
def view_recycle_bin():
    user = session.get("user")
    role = session.get("role", "user")
    owner_filter = None if role == "admin" else user
    bin_files = db.get_bin_files(owner_username=owner_filter)
    return render_template("bin.html", bin_files=bin_files)

@app.route("/files/<file_id>/restore", methods=["POST"])
@login_required
def restore_file_route(file_id):
    file_record, _, _ = db.get_file_detail(file_id)
    if not file_record:
        flash("File not found.", "error")
        return redirect(url_for("view_recycle_bin"))

    user = session.get("user")
    role = session.get("role", "user")
    if file_record["owner_username"] != user and role != "admin":
        flash("Access denied.", "error")
        return redirect(url_for("view_recycle_bin"))

    try:
        storage_service.restore_file(file_id)
        flash(f"♻️ File '{file_record['filename']}' restored back to active vault!", "success")
    except Exception as e:
        flash(f"Failed to restore file: {str(e)}", "error")

    return redirect(url_for("view_recycle_bin"))

@app.route("/files/<file_id>/permanent-delete", methods=["POST"])
@login_required
def permanent_delete_file_route(file_id):
    file_record, _, _ = db.get_file_detail(file_id)
    if not file_record:
        flash("File not found.", "error")
        return redirect(url_for("view_recycle_bin"))

    user = session.get("user")
    role = session.get("role", "user")
    if file_record["owner_username"] != user and role != "admin":
        flash("Access denied.", "error")
        return redirect(url_for("view_recycle_bin"))

    try:
        storage_service.permanently_delete_file(file_id)
        flash(f"❌ File '{file_record['filename']}' permanently purged from cloud storage.", "warning")
    except Exception as e:
        flash(f"Failed to permanently delete file: {str(e)}", "error")

    return redirect(url_for("view_recycle_bin"))


@app.route("/locations/<location_id>/health", methods=["POST"])
@login_required
def check_location_health_route(location_id):
    health = storage_service.check_location_health(location_id)
    flash(f"Health check for {location_id}: {health['status'].upper()} ({health['latency_ms']}ms) - {health['message']}", 
          "success" if health["status"] == "healthy" else "warning")
    return redirect(url_for("view_locations"))

@app.route("/locations/<location_id>/toggle-simulation", methods=["POST"])
@login_required
def toggle_simulation_route(location_id):
    if session.get("role") != "admin":
        flash("Permission denied: Only Admin can toggle outage simulations.", "error")
        return redirect(url_for("view_locations"))

    loc = db.get_location_by_id(location_id)
    if loc:
        current_state = bool(loc["simulated_unhealthy"])
        new_state = not current_state
        db.set_location_unhealthy_state(location_id, new_state)

        # Trigger adapter sync
        storage_service._reload_adapters()

        status_msg = "SIMULATED OUTAGE ENABLED (Location marked offline)" if new_state else "RESTORED ONLINE (Location healthy)"
        flash(f"{loc['display_name']} -> {status_msg}", "warning" if new_state else "success")

    return redirect(url_for("view_locations"))

# Audit History Route (Admin Only)
@app.route("/audit", methods=["GET"])
@login_required
def view_audit_logs():
    if session.get("role") != "admin":
        flash("Permission denied: Audit logs are restricted to Administrators.", "error")
        return redirect(url_for("index"))
    
    logs = db.get_recent_audit_logs(limit=100, actor_filter=None)
    return render_template("audit.html", logs=logs)

# File Unlock Route (For extra password-protected files)
@app.route("/files/<file_id>/unlock", methods=["POST"])
@login_required
def unlock_file_route(file_id):
    password = request.form.get("protection_password", "").strip()
    if db.verify_file_protection_password(file_id, password):
        session[f"unlocked_{file_id}"] = True
        flash("🔓 File unlocked successfully!", "success")
        return redirect(url_for("view_file_detail", file_id=file_id))
    else:
        flash("❌ Incorrect file protection password.", "error")
        return redirect(url_for("index"))

# File Preview Route (Only for public pictures of users - NOT password protected)
@app.route("/files/<file_id>/preview", methods=["GET"])
@login_required
def preview_file_route(file_id):
    file_record, _, _ = db.get_file_detail(file_id)
    if not file_record:
        return "Not found", 404

    user = session.get("user")
    role = session.get("role", "user")
    file_dict = dict(file_record)
    if file_dict["owner_username"] != user and role != "admin":
        return "Access denied", 403

    # STRICT SECRECY: If password protected and not unlocked, DO NOT stream picture preview!
    if file_dict.get("is_protected") and not session.get(f"unlocked_{file_id}"):
        return "🔒 Protected File - Password required for preview", 403

    try:
        stream, filename, content_type, download_info = storage_service.download_file(file_id)
        return send_file(stream, mimetype=content_type or "image/png", as_attachment=False)
    except Exception:
        return "Error loading preview", 500

# Admin Users Management & User Vault Overview Route
@app.route("/admin/users", methods=["GET"])
@login_required
def admin_users_management():
    if session.get("role") != "admin":
        flash("Permission denied: Only Admin can access Users Management.", "error")
        return redirect(url_for("index"))

    users_list = db.get_all_users_with_stats()
    storage_summary = storage_service.get_overall_storage_summary(owner_username=None)
    return render_template("admin_users.html", users=users_list, storage_summary=storage_summary)

# Admin Inspect Specific User Vault Route
@app.route("/admin/users/<username>", methods=["GET"])
@login_required
def admin_inspect_user_vault(username):
    if session.get("role") != "admin":
        flash("Permission denied.", "error")
        return redirect(url_for("index"))

    files = db.get_all_files(owner_username=username)
    locations = db.get_all_locations()
    health_status = storage_service.check_all_locations_health()
    storage_summary = storage_service.get_overall_storage_summary(owner_username=username)
    return render_template("index.html", files=files, locations=locations, health_status=health_status, storage_summary=storage_summary, inspected_user=username)

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Starting Personal Multi-Cloud Storage Dashboard Server")
    print("   Listening on http://0.0.0.0:5000")
    print("=" * 60)
    app.run(
        debug=True,
        host="0.0.0.0",
        port=5000
    )