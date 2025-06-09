from flask import Blueprint, request, jsonify, current_app, url_for, abort  # type: ignore
from celery.result import AsyncResult  # type: ignore
import redis # type: ignore
import json # type: ignore
from ..tasks import run_full_analysis

analysis_bp = Blueprint("analysis_bp", __name__)


@analysis_bp.route("/api/conversations", methods=["GET"])
def list_conversations():
    redis_client = current_app.redis_client
    status_filter = request.args.get("status", type=str)
    lang_filter = request.args.get("language", type=str)

    conv_list = []
    file_meta_keys = redis_client.scan_iter("filemeta:*")

    for key in file_meta_keys:
        c_data = redis_client.hgetall(key)

        if status_filter and c_data.get("status") != status_filter:
            continue
        if lang_filter and c_data.get("language") != lang_filter.lower():
            continue

        file_id = c_data.get("file_id", key.split(":", 1)[1]) # Extract file_id from key if not in hash

        conv_list.append({
            "id": file_id, # Using file_id as the primary identifier
            "file_id": file_id,
            "original_filename": c_data.get("original_filename"),
            "status": c_data.get("status"),
            "language": c_data.get("language"),
            "upload_timestamp": c_data.get("upload_timestamp"),
            "celery_task_id": c_data.get("celery_task_id"),
            "details_url": url_for(
                "analysis_bp.get_conversation_details",
                conversation_identifier=file_id, # Use file_id
                _external=True,
            ),
            "analysis_result_url": (
                url_for(
                    "analysis_bp.get_task_result", # This will need adjustment if route changes
                    task_id=c_data.get("celery_task_id"),
                    _external=True,
                )
                if c_data.get("celery_task_id")
                else None
            ),
        })

    # Optional: Sort by upload_timestamp if needed, requires parsing the string to datetime
    # conv_list.sort(key=lambda x: x.get("upload_timestamp") or "", reverse=True)


    return jsonify({"conversations": conv_list, "total_items": len(conv_list)}), 200


@analysis_bp.route("/api/conversations/<conversation_identifier>", methods=["GET"])
def get_conversation_details(conversation_identifier):
    file_id = conversation_identifier # Assuming identifier is file_id
    redis_client = current_app.redis_client
    meta_key = f"filemeta:{file_id}"

    metadata = redis_client.hgetall(meta_key)
    if not metadata:
        abort(404, description="Conversation metadata not found in Redis.")

    status = metadata.get("status")
    celery_task_id = metadata.get("celery_task_id")

    return (
        jsonify(
            {
                "id": file_id, # Using file_id as the primary identifier
                "file_id": file_id,
                "original_filename": metadata.get("original_filename"),
                "status": status,
                "language": metadata.get("language"),
                "upload_timestamp": metadata.get("upload_timestamp"),
                "celery_task_id": celery_task_id,
                "analysis_result_summary_url": (
                    url_for(
                        "analysis_bp.get_task_result", # This will be updated if route changes
                        task_id=celery_task_id,
                        _external=True,
                    )
                    if celery_task_id
                    else None
                ),
                "emotion_results_url": (
                    url_for(
                        "analysis_bp.get_specific_analysis_result",
                        conversation_identifier=file_id, # Use file_id
                        analysis_type="emotion_analysis",
                        _external=True,
                    )
                    if status in ["COMPLETED", "COMPLETED_WITH_ERRORS"]
                    else None
                ),
                "persuasion_results_url": (
                    url_for(
                        "analysis_bp.get_specific_analysis_result",
                        conversation_identifier=file_id, # Use file_id
                        analysis_type="persuasion_analysis",
                        _external=True,
                    )
                    if status in ["COMPLETED", "COMPLETED_WITH_ERRORS"]
                    else None
                ),
            }
        ),
        200,
    )


@analysis_bp.route(
    "/api/conversations/<conversation_identifier>/results/<analysis_type>",
    methods=["GET"],
)
def get_specific_analysis_result(conversation_identifier, analysis_type):
    file_id = conversation_identifier # Assuming identifier is file_id
    redis_client = current_app.redis_client
    meta_key = f"filemeta:{file_id}"
    result_key = f"analysisresult:{file_id}"

    file_meta = redis_client.hgetall(meta_key)
    if not file_meta:
        abort(404, description="Conversation metadata not found in Redis.")

    status = file_meta.get("status")
    if status not in ["COMPLETED", "COMPLETED_WITH_ERRORS"]:
        abort(
            409,
            description=f"Analysis not yet complete or failed. Current status: {status}",
        )

    result_json_str = redis_client.get(result_key)
    if not result_json_str:
        abort(404, description="Analysis result data not found in Redis.")

    analysis_result_record_data = json.loads(result_json_str)
    full_results_payload = analysis_result_record_data.get("results", {})

    # Normalize analysis_type for matching (e.g. emotion vs emotion_analysis)
    # This simple check is basic, more robust mapping might be needed if keys vary a lot.
    normalized_analysis_type = analysis_type.lower().replace("-", "_")
    actual_key_found = None
    for key in full_results_payload.keys():
        if normalized_analysis_type == key.lower().replace("-", "_"):
            actual_key_found = key
            break

    if not actual_key_found:
        valid_types = list(full_results_payload.keys())
        abort(
            404,
            description=f"Invalid analysis type '{analysis_type}'. Valid types: {valid_types}",
        )

    # Use the found actual key
    specific_result = full_results_payload.get(actual_key_found)

    return (
        jsonify(
            {
                "file_id": file_id,
                "analysis_type_requested": analysis_type,
                "analysis_type_found": actual_key_found,
                "data": specific_result,
            }
        ),
        200,
    )


# --- Task Management Endpoints (rely on app error handlers) ---
@analysis_bp.route("/api/analyze/<file_id>", methods=["POST"])
def start_analysis_task(file_id):
    if ".." in file_id or "/" in file_id: # Basic check, consider more robust validation
        abort(400, description="Invalid file_id format.")

    redis_client = current_app.redis_client
    meta_key = f"filemeta:{file_id}"
    metadata = redis_client.hgetall(meta_key)

    if not metadata:
        abort(404, description=f"File metadata for file_id: {file_id} not found in Redis.")

    current_status = metadata.get("status")
    force_analysis = request.args.get("force", "false").lower() == "true"

    if (
        current_status in ["PROCESSING", "PENDING_ANALYSIS", "COMPLETED", "COMPLETED_WITH_ERRORS"]
        and not force_analysis
    ):
        abort(
            409,
            description=(
                f"Analysis for this file is status: {current_status}. "
                "Use ?force=true to re-analyze."
            ),
        )

    task = run_full_analysis.delay(file_id)

    # Update Redis with task ID and new status
    redis_client.hmset(meta_key, {"celery_task_id": task.id, "status": "PENDING_ANALYSIS"})
    # Store task_id to file_id mapping
    redis_client.set(f"task_to_fileid:{task.id}", file_id, ex=current_app.config["REDIS_CACHE_TTL_SECONDS"])

    # Re-apply TTL to meta_key if needed (hmset doesn't clear it but good practice if fields are critical)
    redis_client.expire(meta_key, current_app.config["REDIS_CACHE_TTL_SECONDS"])


    return (
        jsonify(
            {
                "message": "Analysis task started.",
                "task_id": task.id,
                "file_id": file_id,
                "status_url": url_for(
                    "analysis_bp.get_task_status", task_id=task.id, _external=True
                ),
                "result_url": url_for(
                    "analysis_bp.get_task_result", task_id=task.id, _external=True
                ),
            }
        ),
        202,
    )


@analysis_bp.route("/api/analysis_status/<task_id>", methods=["GET"])
def get_task_status(task_id):
    redis_client = current_app.redis_client
    celery_task = AsyncResult(task_id, app=current_app.extensions["celery"])
    celery_state = celery_task.state

    response = {
        "task_id": task_id,
        "celery_state": celery_state,
    }

    # Try to get file_id and its status from Redis
    file_id = redis_client.get(f"task_to_fileid:{task_id}")
    redis_file_status = None
    if file_id:
        response["file_id"] = file_id
        file_meta = redis_client.hgetall(f"filemeta:{file_id}")
        if file_meta and "status" in file_meta:
            redis_file_status = file_meta["status"]
            response["redis_file_status"] = redis_file_status

    if redis_file_status and redis_file_status in ["COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED"]:
        response["authoritative_status"] = redis_file_status
        response["status_message"] = f"Final status from Redis: {redis_file_status}"
    elif celery_state == "PENDING":
        response["status_message"] = "Task is waiting."
    elif celery_state in ["STARTED", "PROGRESS"]:
        response["status_message"] = "Task running."
        if celery_task.info and isinstance(celery_task.info, dict):
            response["progress"] = celery_task.info
    elif celery_state == "SUCCESS":
        # Celery task is done, but processing in run_full_analysis might still be updating Redis status
        response["status_message"] = (
            "Celery task processing completed. Check redis_file_status for final application status."
        )
    elif celery_state == "FAILURE":
        response["status_message"] = "Celery task failed."
        response["error_info_celery"] = str(celery_task.info) # Could be an exception string
        # If Celery task failed, it's possible the file status in Redis wasn't updated to FAILED yet
        if redis_file_status != "FAILED" and file_id: # Check if we have file_id
             # Attempt to update filemeta status to FAILED if Celery reports failure
             # This is a best-effort, actual failure handling should be in the task itself.
             # redis_client.hset(f"filemeta:{file_id}", "status", "FAILED")
             # response["redis_file_status_updated_to_failed"] = True
             pass # Decided against auto-updating here to keep GET idempotent
    else:
        response["status_message"] = f"Task state: {celery_state}."

    return jsonify(response), 200


@analysis_bp.route("/api/analysis_result/<task_id>", methods=["GET"])
def get_task_result(task_id):
    redis_client = current_app.redis_client
    file_id = redis_client.get(f"task_to_fileid:{task_id}")

    if not file_id:
        # Fallback: Check if task_id itself might be a file_id for older/direct calls (optional)
        # For now, strictly rely on task_to_fileid mapping
        # Could also iterate all filemeta:* and check celery_task_id if critical, but inefficient.
        abort(404, description=f"Mapping for task_id {task_id} to file_id not found or expired.")

    meta_key = f"filemeta:{file_id}"
    result_key = f"analysisresult:{file_id}"

    file_meta = redis_client.hgetall(meta_key)
    if not file_meta:
        abort(404, description=f"File metadata for file_id {file_id} (from task_id {task_id}) not found.")

    current_status = file_meta.get("status")
    if current_status not in ["COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED"]: # FAILED tasks might still have partial results if task logic saves them before failing
        celery_task_state = AsyncResult(task_id, app=current_app.extensions["celery"]).state
        return (
            jsonify(
                message="Analysis not yet complete or results are not in a final state.",
                task_id=task_id,
                file_id=file_id,
                current_file_status=current_status,
                celery_task_state=celery_task_state,
            ),
            202, # Accepted, but not ready
        )

    result_json_str = redis_client.get(result_key)
    if not result_json_str:
        # This could happen if task failed before saving results but status is COMPLETED/FAILED
        abort(404, description=f"Analysis result data for file_id {file_id} (task_id {task_id}) not found in Redis.")

    analysis_output = json.loads(result_json_str)
    return (
        jsonify(
            {
                "task_id": task_id,
                "file_id": file_id,
                "final_file_status": current_status, # Status from filemeta
                "analysis_output": analysis_output, # Content from analysisresult:{file_id}
            }
        ),
        200,
    )
