import os
from flask import current_app  # type: ignore
from .celery_app import celery
from .services.analysis_service import (
    extract_speaker_statistics,
    analyze_emotions_with_text2emotion,
    extract_text_from_file,
    calculate_interaction_frequency,
    calculate_persuasion_scores_heuristic,
    detect_fallacies_and_manipulation_heuristic,
)
import redis # type: ignore
import json # type: ignore


@celery.task(bind=True)
def run_full_analysis(self, file_id):
    """
    Celery task to run the full analysis pipeline and save results to Redis.
    """
    redis_client = current_app.redis_client
    meta_key = f"filemeta:{file_id}"
    result_key = f"analysisresult:{file_id}"

    file_metadata = redis_client.hgetall(meta_key)

    if not file_metadata:
        self.update_state(state="FAILURE", meta={"exc_type": "ValueError", "exc_message": f"File metadata not found in Redis for file_id: {file_id} (possibly expired)"})
        return {"error": f"File metadata not found for file_id: {file_id}", "status": "FAILURE_METADATA_NOT_FOUND"}

    redis_client.hmset(meta_key, {"status": "PROCESSING", "celery_task_id": self.request.id})
    # Re-apply TTL if needed, though updating fields doesn't clear it. Consider if TTL should be extended.
    redis_client.expire(meta_key, current_app.config["REDIS_CACHE_TTL_SECONDS"])

    upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")
    filepath = os.path.join(upload_folder, file_id)

    if not os.path.exists(filepath):
        redis_client.hset(meta_key, "status", "FAILED")
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
    results_payload = {}
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
    final_status_for_redis = ""
    if errors_list:
        final_status_for_redis = "COMPLETED_WITH_ERRORS"
        task_final_status_for_celery_result = "COMPLETED_WITH_ERRORS"
    else:
        final_status_for_redis = "COMPLETED"
        task_final_status_for_celery_result = "SUCCESS"

    final_data_for_storage = {
        "task_status_reported": task_final_status_for_celery_result,
        "results": results_payload,
        "errors": errors_list,
        "file_id": file_id # Include file_id for clarity
    }

    redis_client.set(result_key, json.dumps(final_data_for_storage))
    redis_client.expire(result_key, current_app.config["REDIS_CACHE_TTL_SECONDS"])
    redis_client.hset(meta_key, "status", final_status_for_redis)

    return {
        "status": task_final_status_for_celery_result,
        "file_id": file_id, # Changed from conversation_id
        "analysis_result_key_redis": result_key, # Instead of db_id
        "errors_count": len(errors_list),
    }
