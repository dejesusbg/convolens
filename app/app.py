import os
import uuid
import logging
from flask import Flask, request, jsonify  # type: ignore
from flask_cors import CORS  # type: ignore
from flask_talisman import Talisman  # type: ignore
import redis # type: ignore
from datetime import datetime # type: ignore
from .celery_app import init_celery

ALLOWED_EXTENSIONS = {"txt", "json", "csv"}
SUPPORTED_LANGUAGES = ["en", "es"]


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def create_app(config_name=None):
    app = Flask(__name__)

    # --- Configuration ---
    app.config["UPLOAD_FOLDER"] = os.path.join(os.getcwd(), "uploads")
    app.config["CELERY_BROKER_URL"] = os.environ.get(
        "CELERY_BROKER_URL", "redis://localhost:6379/0"
    )
    app.config["CELERY_RESULT_BACKEND"] = os.environ.get(
        "CELERY_RESULT_BACKEND", "redis://localhost:6379/0"
    )
    app.config["REDIS_CACHE_TTL_SECONDS"] = int(os.environ.get("REDIS_CACHE_TTL_SECONDS", "600"))
    app.config["SESSION_COOKIE_HTTPONLY"] = True

    # CORS Configuration - Allow all origins for development.
    # For production, specify allowed origins: CORS(app, origins=["https://yourfrontend.com"])
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Talisman Configuration for security headers
    # Basic CSP: only allow resources from 'self'. API might not need complex CSP.
    # For a pure API, a very restrictive CSP like "default-src 'none'" might be too much if health checks or other things are served.
    # Let's start with some common non-CSP headers.
    talisman_options = {
        "content_security_policy": None,  # Disable complex CSP for now, can be added later
        "force_https": os.environ.get("FLASK_ENV")
        == "production",  # Force HTTPS if in production (behind a proxy usually)
        "strict_transport_security": os.environ.get("FLASK_ENV") == "production",
        "session_cookie_secure": os.environ.get("FLASK_ENV") == "production",
        "frame_options": "DENY",
    }
    Talisman(app, **talisman_options)

    if not os.path.exists(app.config["UPLOAD_FOLDER"]):
        os.makedirs(app.config["UPLOAD_FOLDER"])

    # --- Logging Configuration ---
    if not app.debug:  # More verbose logging in production
        app.logger.setLevel(logging.INFO)
        # Example: Add a file handler
        # file_handler = logging.FileHandler('production.log')
        # file_handler.setLevel(logging.INFO)
        # app.logger.addHandler(file_handler)
    else:
        app.logger.setLevel(logging.DEBUG)

    app.logger.info("Convolens application starting up...")

    # --- Initialize Extensions ---
    init_celery(app)
    app.redis_client = redis.Redis.from_url(
        app.config["CELERY_BROKER_URL"],
        decode_responses=True # Important for reading strings back easily
    )

    # --- Error Handling ---
    @app.errorhandler(400)
    def bad_request_error(error):
        return (
            jsonify(
                error="Bad Request",
                message=str(
                    error.description if hasattr(error, "description") else error
                ),
            ),
            400,
        )

    @app.errorhandler(404)
    def not_found_error(error):
        return (
            jsonify(
                error="Not Found",
                message=str(
                    error.description
                    if hasattr(error, "description")
                    else "Resource not found."
                ),
            ),
            404,
        )

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f"Internal Server Error: {error}", exc_info=True)
        return (
            jsonify(
                error="Internal Server Error",
                message="An unexpected error occurred. Please try again later.",
            ),
            500,
        )

    # --- Routes ---
    @app.route("/api/health")
    def health():
        try:
            current_app.redis_client.ping()
            redis_status = "OK"
        except Exception as e:
            redis_status = f"Error: {str(e)}"
        return jsonify(status="OK", redis_connection=redis_status)

    @app.route("/api/upload", methods=["POST"])
    def upload_file():
        # (Upload logic remains similar, but benefits from global error handlers)
        if "file" not in request.files:
            return (
                jsonify(
                    error="No file part in the request", details="File is required."
                ),
                400,
            )

        file = request.files["file"]
        original_fname = file.filename

        lang_code = request.form.get("language", "en").lower()
        if lang_code not in SUPPORTED_LANGUAGES:
            return (
                jsonify(
                    error="Unsupported language",
                    details=f"Supported codes: {', '.join(SUPPORTED_LANGUAGES)}",
                ),
                400,
            )

        if original_fname == "":
            return (
                jsonify(error="No selected file", details="Filename cannot be empty."),
                400,
            )

        if not allowed_file(original_fname):
            return (
                jsonify(
                    error="File type not allowed",
                    details=f"Allowed types: {', '.join(ALLOWED_EXTENSIONS)}",
                ),
                400,
            )

        file_id = str(uuid.uuid4()) + os.path.splitext(original_fname)[1]

        try:
            upload_dir = app.config["UPLOAD_FOLDER"]
            # Path creation already handled in create_app, but defensive check:
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir)

            filepath_to_save = os.path.join(upload_dir, file_id)
            file.save(filepath_to_save)

            upload_ts = datetime.utcnow().isoformat()
            metadata = {
                "original_filename": original_fname,
                "upload_timestamp": upload_ts,
                "status": "UPLOADED",
                "language": lang_code,
                "file_id": file_id # Also store file_id in the hash for convenience
            }
            redis_key = f"filemeta:{file_id}"
            app.redis_client.hmset(redis_key, metadata)
            app.redis_client.expire(redis_key, app.config["REDIS_CACHE_TTL_SECONDS"])

            return (
                jsonify(
                    message="File uploaded successfully.",
                    file_id=file_id,
                    language=lang_code,
                ),
                201,
            )
        except Exception as e:
            app.logger.error(f"Upload error: {e}", exc_info=True)
            return jsonify(error="Upload failed", message=str(e)), 500

    from .routes.analysis_routes import analysis_bp

    app.register_blueprint(analysis_bp)

    return app


if __name__ == "__main__":
    # Renamed to avoid conflict with flask.current_app proxy
    current_app_instance = create_app()
    # Use the instance here
    current_app_instance.run(host="0.0.0.0", port=5000, debug=True)
