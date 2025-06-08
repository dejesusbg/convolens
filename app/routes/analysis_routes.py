from flask import Blueprint, request, jsonify, current_app, url_for, abort  # type: ignore # Added abort
from ..tasks import run_full_analysis
from celery.result import AsyncResult  # type: ignore
from ..models import db, Conversation, AnalysisResult
from sqlalchemy import or_  # type: ignore

analysis_bp = Blueprint("analysis_bp", __name__)


@analysis_bp.route("/api/conversations", methods=["GET"])
def list_conversations():
    try:
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)
        if page <= 0 or per_page <= 0:
            abort(400, description="Page and per_page must be positive integers.")
        if per_page > 100:  # Max limit for per_page
            per_page = 100
    except ValueError:  # Handle cases where type=int fails for non-integer strings
        abort(400, description="Page and per_page must be integers.")

    status_filter = request.args.get("status", type=str)
    lang_filter = request.args.get("language", type=str)

    query = Conversation.query.order_by(Conversation.upload_timestamp.desc())

    if status_filter:
        valid_statuses = [
            "UPLOADED",
            "PENDING_ANALYSIS",
            "PROCESSING",
            "COMPLETED",
            "COMPLETED_WITH_ERRORS",
            "FAILED",
        ]
        if status_filter not in valid_statuses:
            abort(
                400,
                description=f"Invalid status filter. Valid statuses: {', '.join(valid_statuses)}",
            )
        query = query.filter(Conversation.status == status_filter)

    if lang_filter:
        # Assuming SUPPORTED_LANGUAGES is accessible or re-defined here, or passed from app config
        # For simplicity, let's assume it's ok to filter by any string for now,
        # or rely on the upload validation to ensure only valid langs are in DB.
        query = query.filter(Conversation.language == lang_filter.lower())

    try:
        paginated_conversations = query.paginate(
            page, per_page, error_out=False
        )  # error_out=False prevents 404 on empty page
    except Exception as e:  # Catch potential pagination errors not covered by aborts
        current_app.logger.error(f"Pagination query error: {e}")
        abort(500, description="Error during data retrieval.")

    conv_list = [
        {
            "id": c.id,
            "file_id": c.file_id,
            "original_filename": c.original_filename,
            "status": c.status.value if c.status else None,
            "language": c.language,
            "upload_timestamp": (
                c.upload_timestamp.isoformat() if c.upload_timestamp else None
            ),
            "celery_task_id": c.celery_task_id,
            "details_url": url_for(
                "analysis_bp.get_conversation_details",
                conversation_identifier=c.id,
                _external=True,
            ),
            "analysis_result_url": (
                url_for(
                    "analysis_bp.get_task_result",
                    task_id=c.celery_task_id,
                    _external=True,
                )
                if c.celery_task_id
                else None
            ),
        }
        for c in paginated_conversations.items
    ]

    return (
        jsonify(
            {
                "conversations": conv_list,
                "total_pages": paginated_conversations.pages,
                "current_page": page,
                "per_page": per_page,
                "total_items": paginated_conversations.total,
            }
        ),
        200,
    )


@analysis_bp.route("/api/conversations/<conversation_identifier>", methods=["GET"])
def get_conversation_details(conversation_identifier):
    query = Conversation.query
    if conversation_identifier.isdigit():
        query = query.filter(Conversation.id == int(conversation_identifier))
    else:
        query = query.filter(Conversation.file_id == conversation_identifier)

    conversation = query.first()
    if not conversation:
        abort(404, description="Conversation not found.")

    # Ensure c.upload_timestamp is used in isoformat(), not the loop variable from list_conversations
    upload_ts_iso = (
        conversation.upload_timestamp.isoformat()
        if conversation.upload_timestamp
        else None
    )

    return (
        jsonify(
            {
                "id": conversation.id,
                "file_id": conversation.file_id,
                "original_filename": conversation.original_filename,
                "status": conversation.status.value if conversation.status else None,
                "language": conversation.language,
                "upload_timestamp": upload_ts_iso,
                "celery_task_id": conversation.celery_task_id,
                "analysis_result_summary_url": (
                    url_for(
                        "analysis_bp.get_task_result",
                        task_id=conversation.celery_task_id,
                        _external=True,
                    )
                    if conversation.celery_task_id
                    else None
                ),
                "emotion_results_url": (
                    url_for(
                        "analysis_bp.get_specific_analysis_result",
                        conversation_identifier=conversation.id,
                        analysis_type="emotion_analysis",
                        _external=True,
                    )
                    if conversation.status
                    in [
                        "COMPLETED",
                        "COMPLETED_WITH_ERRORS",
                    ]
                    else None
                ),
                "persuasion_results_url": (
                    url_for(
                        "analysis_bp.get_specific_analysis_result",
                        conversation_identifier=conversation.id,
                        analysis_type="persuasion_analysis",
                        _external=True,
                    )
                    if conversation.status
                    in [
                        "COMPLETED",
                        "COMPLETED_WITH_ERRORS",
                    ]
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
    query = Conversation.query
    if conversation_identifier.isdigit():
        query = query.filter(Conversation.id == int(conversation_identifier))
    else:
        query = query.filter(Conversation.file_id == conversation_identifier)

    conversation = query.first()
    if not conversation:
        abort(404, description="Conversation not found.")

    if conversation.status not in [
        "COMPLETED",
        "COMPLETED_WITH_ERRORS",
    ]:
        abort(
            409,
            description=f"Analysis not yet complete or failed. Current status: {conversation.status.value}",
        )

    analysis_result_record = AnalysisResult.query.filter_by(
        conversation_id=conversation.id
    ).first()
    if not analysis_result_record or not analysis_result_record.data:
        abort(404, description="Analysis result data not found for this conversation.")

    full_results_payload = analysis_result_record.data.get("results", {})

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

    specific_result = full_results_payload.get(
        actual_key_found
    )  # Use the found actual key

    return (
        jsonify(
            {
                "conversation_id": conversation.id,
                "file_id": conversation.file_id,
                "analysis_type_requested": analysis_type,
                "analysis_type_found": actual_key_found,
                "data": specific_result,
            }
        ),
        200,
    )


# --- Task Management Endpoints (largely same, rely on app error handlers) ---
@analysis_bp.route("/api/analyze/<file_id>", methods=["POST"])
def start_analysis_task(file_id):
    if ".." in file_id or "/" in file_id:
        abort(400, description="Invalid file_id format.")

    conversation = Conversation.query.filter_by(file_id=file_id).first()
    if not conversation:
        abort(404, description=f"Conversation with file_id: {file_id} not found.")

    force_analysis = request.args.get("force", "false").lower() == "true"
    if (
        conversation.status
        in [
            "PROCESSING",
            "PENDING_ANALYSIS",
            "COMPLETED",
            "COMPLETED_WITH_ERRORS",
        ]
        and not force_analysis
    ):
        abort(
            409,
            description="Analysis for this file is already processing or completed. Use ?force=true to re-analyze.",
        )

    task = run_full_analysis.delay(file_id)
    conversation.celery_task_id = task.id
    conversation.status = "PENDING_ANALYSIS"
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"DB error in start_analysis_task: {e}", exc_info=True)
        abort(
            500, description="Failed to update conversation status for analysis task."
        )

    return (
        jsonify(
            {
                "message": "Analysis task started.",
                "task_id": task.id,
                "file_id": file_id,
                "conversation_id": conversation.id,
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
    # (Logic largely same, error handling for not found conversation is now handled by abort(404) or similar)
    conversation = Conversation.query.filter_by(celery_task_id=task_id).first()
    db_status = conversation.status.value if conversation else "TASK_ID_NOT_IN_DB"

    # Check Celery task state
    celery_task = AsyncResult(task_id, app=current_app.extensions["celery"])
    celery_state = celery_task.state

    response = {
        "task_id": task_id,
        "celery_state": celery_state,
        "db_conversation_status": db_status,
    }

    if conversation and conversation.status in [
        "COMPLETED",
        "COMPLETED_WITH_ERRORS",
        "FAILED",
    ]:
        response["authoritative_status"] = db_status
        response["status_message"] = f"Final status from DB: {db_status}"
    elif celery_state == "PENDING":
        response["status_message"] = "Task is waiting."
    elif celery_state in ["STARTED", "PROGRESS"]:
        response["status_message"] = "Task running."
        if celery_task.info and isinstance(celery_task.info, dict):
            response["progress"] = celery_task.info
    elif celery_state == "SUCCESS":
        response["status_message"] = (
            "Celery task success. DB should reflect final state."
        )
    elif celery_state == "FAILURE":
        response["status_message"] = "Celery task failed."
        response["error_info_celery"] = str(celery_task.info)
    else:
        response["status_message"] = f"Task state: {celery_state}."

    return jsonify(response), 200


@analysis_bp.route("/api/analysis_result/<task_id>", methods=["GET"])
def get_task_result(task_id):
    conversation = Conversation.query.filter_by(celery_task_id=task_id).first()
    if not conversation:
        abort(404, description=f"No conversation found for task_id: {task_id}.")

    if conversation.status not in [
        "COMPLETED",
        "COMPLETED_WITH_ERRORS",
        "FAILED",
    ]:
        celery_task = AsyncResult(task_id, app=current_app.extensions["celery"])
        return (
            jsonify(
                message="Analysis not yet complete or results unavailable.",
                task_id=task_id,
                db_status=conversation.status.value,
                celery_state=celery_task.state,
            ),
            202,
        )

    analysis_result_record = AnalysisResult.query.filter_by(
        conversation_id=conversation.id
    ).first()
    if not analysis_result_record:
        abort(404, description="Analysis result record not found.")

    return (
        jsonify(
            {
                "task_id": task_id,
                "file_id": conversation.file_id,
                "conversation_id": conversation.id,
                "final_db_status": conversation.status.value,
                "analysis_output": analysis_result_record.data,
            }
        ),
        200,
    )
