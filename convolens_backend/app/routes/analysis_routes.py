from flask import Blueprint, request, jsonify, current_app, url_for
import os
from ..tasks import run_full_analysis
from celery.result import AsyncResult
from ..models import db, Conversation, AnalysisResult, ConversationStatus # Import db and models

analysis_bp = Blueprint('analysis_bp', __name__)

@analysis_bp.route('/api/files', methods=['GET'])
def list_uploaded_files():
    # Optionally, list from DB conversations table instead of filesystem
    try:
        conversations = Conversation.query.with_entities(Conversation.file_id, Conversation.original_filename, Conversation.status, Conversation.upload_timestamp).all()
        file_list = [{
            "file_id": c.file_id,
            "original_filename": c.original_filename,
            "status": c.status.value if c.status else None,
            "uploaded_at": c.upload_timestamp.isoformat() if c.upload_timestamp else None
        } for c in conversations]
        return jsonify(files=file_list), 200
    except Exception as e:
        current_app.logger.error(f"Error listing files from DB: {e}")
        return jsonify(error="Could not retrieve file list from database."), 500

@analysis_bp.route('/api/analyze/<file_id>', methods=['POST'])
def start_analysis_task(file_id):
    if '..' in file_id or '/' in file_id: # Basic security check
        return jsonify(error="Invalid file_id format."), 400

    conversation = Conversation.query.filter_by(file_id=file_id).first()
    if not conversation:
         return jsonify(error=f"Conversation with file_id: {file_id} not found. Please upload the file first."), 404

    # Prevent re-analysis if already completed or processing, unless forced (add force param later)
    if conversation.status in [ConversationStatus.PROCESSING, ConversationStatus.PENDING_ANALYSIS, ConversationStatus.COMPLETED, ConversationStatus.COMPLETED_WITH_ERRORS]:
        return jsonify(message="Analysis for this file is already processing or completed.",
                       task_id=conversation.celery_task_id,
                       status=conversation.status.value,
                       status_url=url_for('analysis_bp.get_task_status', task_id=conversation.celery_task_id, _external=True) if conversation.celery_task_id else None,
                       result_url=url_for('analysis_bp.get_task_result', task_id=conversation.celery_task_id, _external=True) if conversation.celery_task_id else None
                       ), 409 # Conflict / Already done

    # Dispatch Celery task
    task = run_full_analysis.delay(file_id)

    # Update conversation record with task_id and PENDING_ANALYSIS status
    conversation.celery_task_id = task.id
    conversation.status = ConversationStatus.PENDING_ANALYSIS
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"DB error updating conversation for task start: {e}")
        # Task is dispatched, but DB state might be inconsistent. Client will see old status until worker updates it.
        # This is a potential inconsistency point.

    return jsonify({
        "message": "Analysis task started.",
        "task_id": task.id,
        "file_id": file_id,
        "conversation_id": conversation.id,
        "status_url": url_for('analysis_bp.get_task_status', task_id=task.id, _external=True),
        "result_url": url_for('analysis_bp.get_task_result', task_id=task.id, _external=True)
    }), 202 # Accepted

@analysis_bp.route('/api/analysis_status/<task_id>', methods=['GET'])
def get_task_status(task_id):
    # First, check DB for persisted status
    conversation = Conversation.query.filter_by(celery_task_id=task_id).first()
    db_status = None
    if conversation:
        db_status = conversation.status.value if conversation.status else "UNKNOWN_IN_DB"

    # Then, check Celery for real-time task state
    celery_task = AsyncResult(task_id, app=current_app.extensions['celery'])
    celery_state = celery_task.state

    response = {
        "task_id": task_id,
        "celery_state": celery_state,
        "db_conversation_status": db_status,
        "current_status_source": "celery" # Default to celery as more real-time
    }

    if celery_state == 'PENDING':
        response['status_message'] = 'Task is waiting to be processed by a worker.'
    elif celery_state == 'STARTED' or celery_state == 'PROGRESS': # Celery 'STARTED' or our custom 'PROGRESS'
        response['status_message'] = 'Task is currently running.'
        if celery_task.info and isinstance(celery_task.info, dict): # Our custom progress from task.update_state()
            response['progress'] = celery_task.info
    elif celery_state == 'SUCCESS':
        response['status_message'] = 'Celery task completed successfully. Result should be in DB.'
        response['current_status_source'] = "database" # If Celery says success, DB should reflect final state
    elif celery_state == 'FAILURE':
        response['status_message'] = 'Celery task failed.'
        response['error_info_celery'] = str(celery_task.info) # Celery's exception info
        response['current_status_source'] = "database" # DB should reflect FAILED or COMPLETED_WITH_ERRORS
    else: # Other states like RETRY, REVOKED
        response['status_message'] = f'Task is in state: {celery_state}.'

    # If Celery state is terminal (SUCCESS/FAILURE), but DB status doesn't match, flag it.
    if celery_state in ['SUCCESS', 'FAILURE'] and conversation and        ((celery_state == 'SUCCESS' and conversation.status not in [ConversationStatus.COMPLETED, ConversationStatus.COMPLETED_WITH_ERRORS]) or         (celery_state == 'FAILURE' and conversation.status != ConversationStatus.FAILED)):
        response['consistency_warning'] = "Potential inconsistency between Celery state and DB status. DB status is authoritative for final results."
        # response['current_status_source'] = "database" # Already set for SUCCESS/FAILURE


    # If conversation status from DB is terminal, it's more reliable than Celery if Celery result expired
    if conversation and conversation.status in [ConversationStatus.COMPLETED, ConversationStatus.COMPLETED_WITH_ERRORS, ConversationStatus.FAILED]:
         response['status_message'] = f"Final status from DB: {conversation.status.value}"
         response['current_status_source'] = "database"

    return jsonify(response), 200

@analysis_bp.route('/api/analysis_result/<task_id>', methods=['GET'])
def get_task_result(task_id):
    conversation = Conversation.query.filter_by(celery_task_id=task_id).first()

    if not conversation:
        # Try to get info from Celery directly if no DB record, Celery result might still exist
        celery_task_direct = AsyncResult(task_id, app=current_app.extensions['celery'])
        if celery_task_direct.state == 'PENDING' or celery_task_direct.state == 'PROGRESS':
             return jsonify(message="Analysis is still processing (no DB record yet).", task_id=task_id, celery_state=celery_task_direct.state), 202
        elif celery_task_direct.state == 'SUCCESS': # Should ideally be in DB, but as fallback
             return jsonify(message="Result found in Celery (DB record missing).", task_id=task_id, celery_state=celery_task_direct.state, result_from_celery=celery_task_direct.result), 200
        return jsonify(error=f"No conversation found for task_id: {task_id}. Celery result might have expired or task ID is invalid."), 404

    if conversation.status not in [ConversationStatus.COMPLETED, ConversationStatus.COMPLETED_WITH_ERRORS, ConversationStatus.FAILED]:
        # Task not finished yet, or failed before results could be processed
        celery_task = AsyncResult(task_id, app=current_app.extensions['celery']) # Check celery state
        return jsonify(message="Analysis is not yet complete or results are not available.",
                       task_id=task_id,
                       db_status=conversation.status.value if conversation.status else "N/A",
                       celery_state=celery_task.state), 202 # Accepted, but not ready

    analysis_result_record = AnalysisResult.query.filter_by(conversation_id=conversation.id).first()

    if not analysis_result_record:
        # This might happen if task failed before creating the result record, or DB issue
        return jsonify(error="Analysis result record not found in database, though conversation status is terminal.",
                       task_id=task_id,
                       conversation_status=conversation.status.value), 404

    # The 'data' field in AnalysisResult contains the full output from the Celery task.
    # This includes 'task_status_reported', 'results', and 'errors' keys.
    return jsonify({
        "task_id": task_id,
        "file_id": conversation.file_id,
        "conversation_id": conversation.id,
        "final_conversation_status_in_db": conversation.status.value,
        "analysis_output": analysis_result_record.data # This is the dict saved by the task
    }), 200

EOL
