from .celery_app import celery
from .services.analysis_service import (
    extract_speaker_statistics,
    analyze_emotions_with_text2emotion,
    extract_text_from_file,
    calculate_interaction_frequency,
    calculate_persuasion_scores_heuristic,
    detect_fallacies_and_manipulation_heuristic,
)
from .models import (
    db,
    Conversation,
    AnalysisResult,
)  # Import db and models
import os
from flask import current_app  # type: ignore


@celery.task(bind=True)
def run_full_analysis(self, file_id):
    """
    Celery task to run the full analysis pipeline and save results to DB.
    """
    # App context should be available due to ContextTask in celery_app.py
    conversation = Conversation.query.filter_by(file_id=file_id).first()

    if not conversation:
        # This case should ideally be prevented by checks before dispatching
        self.update_state(
            state="FAILURE",
            meta={
                "exc_type": "ValueError",
                "exc_message": f"Conversation record not found for file_id: {file_id}",
            },
        )
        # No db record to update status on here if it's missing.
        return {
            "error": f"Conversation record not found for file_id: {file_id}",
            "status": "FAILURE_DB_ERROR",
        }

    # Update conversation status to PROCESSING
    conversation.celery_task_id = self.request.id  # Store Celery task ID
    conversation.status = "PROCESSING"
    try:
        db.session.commit()
    except Exception as e_db_commit:
        db.session.rollback()
        # Log this critical error
        self.update_state(
            state="FAILURE",
            meta={
                "exc_type": str(type(e_db_commit)),
                "exc_message": f"DB error updating status: {str(e_db_commit)}",
            },
        )
        return {"error": f"DB error: {str(e_db_commit)}", "status": "FAILURE_DB_ERROR"}

    upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")
    filepath = os.path.join(upload_folder, file_id)

    if not os.path.exists(filepath):
        conversation.status = "FAILED"  # File gone missing after upload
        db.session.commit()
        self.update_state(
            state="FAILURE",
            meta={
                "exc_type": "FileNotFoundError",
                "exc_message": f"File not found: {file_id}",
            },
        )
        return {
            "error": f"File not found: {file_id}",
            "status": "FAILURE_FILE_NOT_FOUND",
        }

    # --- Analysis Pipeline ---
    results_payload = {}  # This will store the 'results' dict for AnalysisResult.data
    errors_list = []
    total_steps = 5

    self.update_state(
        state="PROGRESS",
        meta={
            "current": 1,
            "total": total_steps,
            "status": "Analyzing speaker statistics...",
        },
    )
    speaker_stats = extract_speaker_statistics(filepath)
    if "error" in speaker_stats:
        errors_list.append(f"Speaker statistics error: {speaker_stats['error']}")
    results_payload["speaker_statistics"] = speaker_stats

    texts_to_analyze = extract_text_from_file(filepath)
    if isinstance(texts_to_analyze, dict) and "error" in texts_to_analyze:
        err_msg = f"Text extraction error: {texts_to_analyze['error']}"
        errors_list.append(err_msg)
        results_payload["emotion_analysis"] = {"error": err_msg}
        results_payload["persuasion_analysis"] = {"error": err_msg}
        results_payload["tactic_detection"] = {"error": err_msg}
    elif not texts_to_analyze:
        err_msg = "No text content found for analysis."
        errors_list.append(err_msg)
        results_payload["emotion_analysis"] = {"error": err_msg}
        results_payload["persuasion_analysis"] = {"error": err_msg}
        results_payload["tactic_detection"] = {"error": err_msg}
    else:
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 2,
                "total": total_steps,
                "status": "Analyzing emotions...",
            },
        )
        emotion_results = analyze_emotions_with_text2emotion(texts_to_analyze)
        if emotion_results.get("error") or (
            emotion_results.get("results")
            and emotion_results.get("results", [])
            and emotion_results["results"][0].get("error")
        ):
            errors_list.append("Emotion analysis issue.")
        results_payload["emotion_analysis"] = emotion_results

        self.update_state(
            state="PROGRESS",
            meta={
                "current": 3,
                "total": total_steps,
                "status": "Calculating persuasion...",
            },
        )
        persuasion_scores = calculate_persuasion_scores_heuristic(texts_to_analyze)
        if persuasion_scores.get("error") or (
            persuasion_scores.get("results")
            and persuasion_scores.get("results", [])
            and persuasion_scores["results"][0].get("error")
        ):
            errors_list.append("Persuasion analysis issue.")
        results_payload["persuasion_analysis"] = persuasion_scores

        self.update_state(
            state="PROGRESS",
            meta={"current": 4, "total": total_steps, "status": "Detecting tactics..."},
        )
        tactic_detection_results = detect_fallacies_and_manipulation_heuristic(
            texts_to_analyze
        )
        if tactic_detection_results.get("error") or (
            tactic_detection_results.get("results")
            and tactic_detection_results.get("results", [])
            and tactic_detection_results["results"][0].get("error")
        ):
            errors_list.append("Tactic detection issue.")
        results_payload["tactic_detection"] = tactic_detection_results

    self.update_state(
        state="PROGRESS",
        meta={
            "current": 5,
            "total": total_steps,
            "status": "Calculating influence graph...",
        },
    )
    influence_graph_data = calculate_interaction_frequency(filepath)
    if "error" in influence_graph_data:
        errors_list.append(f"Influence graph error: {influence_graph_data['error']}")
    results_payload["influence_graph"] = influence_graph_data
    # --- End Analysis Pipeline ---

    # Determine final status and save results
    task_final_status_for_celery_result = ""
    if errors_list:
        conversation.status = "COMPLETED_WITH_ERRORS"
        task_final_status_for_celery_result = "COMPLETED_WITH_ERRORS"
    else:
        conversation.status = "COMPLETED"
        task_final_status_for_celery_result = "SUCCESS"

    # Create or update AnalysisResult
    # The entire task output (status, results_payload, errors_list) will be stored in AnalysisResult.data
    final_data_for_db = {
        "task_status_reported": task_final_status_for_celery_result,
        "results": results_payload,
        "errors": errors_list,
    }

    existing_analysis_result = AnalysisResult.query.filter_by(
        conversation_id=conversation.id
    ).first()
    if existing_analysis_result:
        existing_analysis_result.data = final_data_for_db
    else:
        new_analysis_result = AnalysisResult(
            conversation_id=conversation.id, data=final_data_for_db
        )
        db.session.add(new_analysis_result)

    try:
        db.session.commit()
    except Exception as e_db_final_commit:
        db.session.rollback()
        # This is a critical failure to save results
        # Mark conversation as failed if results cannot be saved
        conversation.status = "FAILED"
        try:
            db.session.commit()  # Try to commit the FAILED status at least
        except:
            db.session.rollback()  # Give up if even that fails

        self.update_state(
            state="FAILURE",
            meta={
                "exc_type": str(type(e_db_final_commit)),
                "exc_message": f"DB error saving results: {str(e_db_final_commit)}",
            },
        )
        return {
            "error": f"DB error saving results: {str(e_db_final_commit)}",
            "status": "FAILURE_DB_SAVE_RESULT",
        }

    # This is the return value for Celery's own result backend (e.g., Redis)
    # Adding conversation_id to the celery task result for easier tracking if needed from celery directly
    return {
        "status": task_final_status_for_celery_result,
        "conversation_id": conversation.id,
        "analysis_result_db_id": (
            existing_analysis_result.id
            if existing_analysis_result
            else new_analysis_result.id
        ),
        "errors_count": len(errors_list),
    }
