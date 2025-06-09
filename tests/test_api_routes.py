import pytest  # type: ignore
from io import BytesIO

# from app.models import Conversation, db  # Import models # Removed DB models
import json  # For loading json strings from redis
from unittest.mock import MagicMock  # For mocking celery task object


def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["status"] == "OK"
    assert "database" not in json_data  # Ensure 'database' key is removed
    assert json_data["redis_connection"] == "OK"


def test_upload_file_success(
    client, redis_client, mocker
):  # Added redis_client and mocker
    # Test successful file upload
    data = {
        "file": (BytesIO(b"Speaker A: Hello\nSpeaker B: Hi there"), "test_chat.txt"),
        "language": "en",
    }
    # Mock redis methods
    mock_hmset = mocker.patch.object(client.application.redis_client, "hmset")
    mock_expire = mocker.patch.object(client.application.redis_client, "expire")

    response = client.post("/api/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 201
    json_data = response.get_json()
    assert "file_id" in json_data
    assert "conversation_id" not in json_data  # Ensure 'conversation_id' is removed
    assert json_data["language"] == "en"

    # Verify redis calls
    file_id = json_data["file_id"]
    expected_redis_key = f"filemeta:{file_id}"

    mock_hmset.assert_called_once()
    args_hmset, _ = mock_hmset.call_args
    assert args_hmset[0] == expected_redis_key
    metadata_arg = args_hmset[1]
    assert metadata_arg["original_filename"] == "test_chat.txt"
    assert metadata_arg["status"] == "UPLOADED"
    assert metadata_arg["language"] == "en"
    assert "upload_timestamp" in metadata_arg
    assert metadata_arg["file_id"] == file_id

    mock_expire.assert_called_once_with(
        expected_redis_key, client.application.config["REDIS_CACHE_TTL_SECONDS"]
    )


def test_upload_file_invalid_type(
    client, redis_client
):  # Replaced clean_db with redis_client
    data = {"file": (BytesIO(b"some content"), "test.exe")}
    response = client.post("/api/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    json_data = response.get_json()
    assert "error" in json_data
    assert "File type not allowed" in json_data["error"]


def test_upload_file_unsupported_language(
    client, redis_client
):  # Replaced clean_db with redis_client
    data = {
        "file": (BytesIO(b"Speaker A: Hola"), "chat_es.txt"),
        "language": "fr",  # Unsupported
    }
    response = client.post("/api/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    json_data = response.get_json()
    assert "Unsupported language" in json_data["error"]


def test_list_conversations_empty(client, redis_client):  # Replaced clean_db
    # Ensure redis is empty for this test (handled by redis_client fixture)
    response = client.get("/api/conversations")
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["conversations"] == []
    assert json_data["total_items"] == 0


def test_list_conversations_with_data_and_filter(
    client, redis_client
):  # Replaced clean_db
    # Setup: Populate Redis with mock data
    redis_client.hmset(
        "filemeta:file1.txt",
        {
            "file_id": "file1.txt",
            "original_filename": "file1.txt",
            "status": "COMPLETED",
            "language": "en",
            "upload_timestamp": "2023-01-01T10:00:00Z",
            "celery_task_id": "task1",
        },
    )
    redis_client.hmset(
        "filemeta:file2.txt",
        {
            "file_id": "file2.txt",
            "original_filename": "file2.txt",
            "status": "PROCESSING",
            "language": "es",
            "upload_timestamp": "2023-01-02T11:00:00Z",
            "celery_task_id": "task2",
        },
    )

    # Test without filter
    response = client.get("/api/conversations")
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["total_items"] == 2
    # Order might vary as Redis scan_iter doesn't guarantee order. Find by file_id.
    conv_data_file1 = next(
        c for c in json_data["conversations"] if c["file_id"] == "file1.txt"
    )
    assert conv_data_file1["status"] == "COMPLETED"

    # Test filter by status
    response_completed = client.get("/api/conversations?status=COMPLETED")
    assert response_completed.status_code == 200
    json_data_completed = response_completed.get_json()
    assert json_data_completed["total_items"] == 1
    assert json_data_completed["conversations"][0]["file_id"] == "file1.txt"
    assert json_data_completed["conversations"][0]["status"] == "COMPLETED"

    # Test filter by language
    response_es = client.get("/api/conversations?language=es")
    assert response_es.status_code == 200
    json_data_es = response_es.get_json()
    assert json_data_es["total_items"] == 1
    assert json_data_es["conversations"][0]["file_id"] == "file2.txt"
    assert json_data_es["conversations"][0]["language"] == "es"


# Mock Celery task for analyze endpoint tests to avoid actual Celery execution
@pytest.fixture
def mock_celery_task(mocker):
    # Mock the .delay() method of the run_full_analysis task
    mock_delay = mocker.patch("app.tasks.run_full_analysis.delay")

    # Define a mock task object that .delay() will return
    class MockTask:
        def __init__(self, task_id):
            self.id = task_id

    # Configure the mock_delay to return an instance of MockTask
    mock_delay.return_value = MockTask(task_id="mock_celery_task_id_123")
    return mock_delay


def test_start_analysis_task_success(
    client, redis_client, mock_celery_task, mocker
):  # Added redis_client, mocker
    file_id_for_analysis = "analysis_test_file.txt"
    meta_key = f"filemeta:{file_id_for_analysis}"
    task_id = "mock_celery_task_id_123"  # from mock_celery_task fixture

    # Setup: Populate Redis with initial file metadata
    initial_metadata = {
        "file_id": file_id_for_analysis,
        "original_filename": "analysis_test_file.txt",
        "status": "UPLOADED",
        "language": "en",
    }
    redis_client.hmset(meta_key, initial_metadata)

    # Mock redis methods that will be called by the endpoint
    mock_redis_hmset = mocker.patch.object(client.application.redis_client, "hmset")
    mock_redis_set = mocker.patch.object(client.application.redis_client, "set")
    mock_redis_expire = mocker.patch.object(client.application.redis_client, "expire")

    response = client.post(f"/api/analyze/{file_id_for_analysis}")
    assert response.status_code == 202  # Accepted
    json_data = response.get_json()
    assert json_data["message"] == "Analysis task started."
    assert json_data["task_id"] == task_id  # From our mock

    # Verify Celery task's delay method was called
    mock_celery_task.assert_called_once_with(file_id_for_analysis)

    # Verify Redis calls
    # 1. Update filemeta with task_id and PENDING_ANALYSIS status
    mock_redis_hmset.assert_called_once_with(
        meta_key, {"celery_task_id": task_id, "status": "PENDING_ANALYSIS"}
    )

    # 2. Store task_to_fileid mapping
    expected_task_to_fileid_key = f"task_to_fileid:{task_id}"
    ttl = client.application.config["REDIS_CACHE_TTL_SECONDS"]
    mock_redis_set.assert_called_once_with(
        expected_task_to_fileid_key, file_id_for_analysis, ex=ttl
    )

    # 3. Expire on meta_key (called in the route)
    mock_redis_expire.assert_called_once_with(meta_key, ttl)


def test_start_analysis_task_file_not_found(
    client, redis_client, mock_celery_task
):  # Replaced clean_db
    # No need to setup anything in redis, as we are testing a non-existent file
    response = client.post("/api/analyze/non_existent_file.txt")
    assert response.status_code == 404
    json_data = response.get_json()
    assert (
        "File metadata for file_id: non_existent_file.txt not found"
        in json_data["description"]
    )


def test_get_conversation_details_success(client, redis_client):
    file_id = "testfile123.txt"
    meta_key = f"filemeta:{file_id}"
    mock_data = {
        "file_id": file_id,
        "original_filename": "original_test.txt",
        "status": "COMPLETED",
        "language": "en",
        "upload_timestamp": "2023-01-01T12:00:00Z",
        "celery_task_id": "task_abc",
    }
    redis_client.hmset(meta_key, mock_data)

    response = client.get(f"/api/conversations/{file_id}")
    assert response.status_code == 200
    json_data = response.get_json()

    assert json_data["id"] == file_id
    assert json_data["file_id"] == file_id
    assert json_data["original_filename"] == mock_data["original_filename"]
    assert json_data["status"] == mock_data["status"]
    assert json_data["language"] == mock_data["language"]
    assert json_data["upload_timestamp"] == mock_data["upload_timestamp"]
    assert json_data["celery_task_id"] == mock_data["celery_task_id"]
    assert (
        "analysis_result_summary_url" in json_data
    )  # Check for presence, content depends on url_for


def test_get_conversation_details_not_found(client, redis_client):
    response = client.get("/api/conversations/nonexistentfile.txt")
    assert response.status_code == 404
    json_data = response.get_json()
    assert "Conversation metadata not found" in json_data["description"]


def test_get_task_status(client, redis_client, mocker):
    task_id = "celery_task_for_status"
    file_id = "file_for_task_status.txt"

    # Mock Celery's AsyncResult
    mock_async_result = MagicMock()
    mock_async_result.state = "PROGRESS"
    mock_async_result.info = {"current": 1, "total": 5, "status": "processing..."}
    mocker.patch("celery.result.AsyncResult", return_value=mock_async_result)

    # Populate Redis for task_to_fileid mapping and filemeta
    redis_client.set(f"task_to_fileid:{task_id}", file_id)
    redis_client.hmset(
        f"filemeta:{file_id}", {"status": "PROCESSING", "celery_task_id": task_id}
    )

    response = client.get(f"/api/analysis_status/{task_id}")
    assert response.status_code == 200
    json_data = response.get_json()

    assert json_data["task_id"] == task_id
    assert json_data["celery_state"] == "PROGRESS"
    assert json_data["file_id"] == file_id
    assert json_data["redis_file_status"] == "PROCESSING"
    assert json_data["progress"]["current"] == 1
    assert "Task running" in json_data["status_message"]

    # Test case where task ID is not in Redis task_to_fileid
    mock_async_result.state = "PENDING"
    mocker.patch(
        "celery.result.AsyncResult", return_value=mock_async_result
    )  # Re-patch for new state

    # Ensure task_to_fileid is missing for this specific task_id
    redis_client.delete(f"task_to_fileid:unknown_task_id")  # ensure it's clean
    response_unknown = client.get("/api/analysis_status/unknown_task_id")
    assert response_unknown.status_code == 200
    json_data_unknown = response_unknown.get_json()
    assert json_data_unknown["task_id"] == "unknown_task_id"
    assert json_data_unknown["celery_state"] == "PENDING"
    assert "file_id" not in json_data_unknown  # As task_to_fileid mapping doesn't exist
    assert "redis_file_status" not in json_data_unknown


def test_get_task_result_success(client, redis_client, mocker):
    task_id = "celery_task_for_result"
    file_id = "file_for_task_result.txt"

    # Mock AsyncResult for the case where status is not final (though not strictly needed if Redis status is final)
    mock_async_result = MagicMock()
    mock_async_result.state = "SUCCESS"  # Assume Celery task itself succeeded
    mocker.patch("celery.result.AsyncResult", return_value=mock_async_result)

    # Populate Redis
    redis_client.set(f"task_to_fileid:{task_id}", file_id)
    redis_client.hmset(
        f"filemeta:{file_id}", {"status": "COMPLETED", "celery_task_id": task_id}
    )

    mock_analysis_output = {"results": {"emotion": "happy"}, "errors": []}
    redis_client.set(f"analysisresult:{file_id}", json.dumps(mock_analysis_output))

    response = client.get(f"/api/analysis_result/{task_id}")
    assert response.status_code == 200
    json_data = response.get_json()

    assert json_data["task_id"] == task_id
    assert json_data["file_id"] == file_id
    assert json_data["final_file_status"] == "COMPLETED"
    assert json_data["analysis_output"] == mock_analysis_output


def test_get_task_result_not_found(client, redis_client):
    # Case 1: task_to_fileid mapping missing
    response_no_map = client.get("/api/analysis_result/unmapped_task")
    assert response_no_map.status_code == 404
    assert (
        "Mapping for task_id unmapped_task to file_id not found"
        in response_no_map.get_json()["description"]
    )

    # Case 2: filemeta missing
    task_id_no_meta = "task_no_meta"
    redis_client.set(f"task_to_fileid:{task_id_no_meta}", "file_no_meta.txt")
    response_no_meta = client.get(f"/api/analysis_result/{task_id_no_meta}")
    assert response_no_meta.status_code == 404
    assert (
        "File metadata for file_id file_no_meta.txt"
        in response_no_meta.get_json()["description"]
    )

    # Case 3: analysisresult missing
    task_id_no_result = "task_no_result"
    file_id_no_result = "file_no_result.txt"
    redis_client.set(f"task_to_fileid:{task_id_no_result}", file_id_no_result)
    redis_client.hmset(
        f"filemeta:{file_id_no_result}", {"status": "COMPLETED"}
    )  # Status is completed
    # but analysisresult:{file_id_no_result} is not set
    response_no_result_data = client.get(f"/api/analysis_result/{task_id_no_result}")
    assert response_no_result_data.status_code == 404
    assert (
        f"Analysis result data for file_id {file_id_no_result}"
        in response_no_result_data.get_json()["description"]
    )

    # Case 4: Analysis not yet complete (status not final)
    task_id_not_complete = "task_not_complete"
    file_id_not_complete = "file_not_complete.txt"
    redis_client.set(f"task_to_fileid:{task_id_not_complete}", file_id_not_complete)
    redis_client.hmset(f"filemeta:{file_id_not_complete}", {"status": "PROCESSING"})
    response_not_complete = client.get(f"/api/analysis_result/{task_id_not_complete}")
    assert response_not_complete.status_code == 202  # Accepted, but not ready
    assert "Analysis not yet complete" in response_not_complete.get_json()["message"]


def test_get_specific_analysis_result_success(client, redis_client):
    file_id = "file_for_specific_result.txt"
    analysis_type = "emotion_analysis"

    # Populate Redis
    redis_client.hmset(f"filemeta:{file_id}", {"status": "COMPLETED"})

    mock_full_results = {
        "results": {
            "emotion_analysis": {"sentiment": "positive", "score": 0.9},
            "persuasion_analysis": {"effectiveness": "high"},
        },
        "errors": [],
    }
    redis_client.set(f"analysisresult:{file_id}", json.dumps(mock_full_results))

    response = client.get(f"/api/conversations/{file_id}/results/{analysis_type}")
    assert response.status_code == 200
    json_data = response.get_json()

    assert json_data["file_id"] == file_id
    assert json_data["analysis_type_requested"] == analysis_type
    assert (
        json_data["analysis_type_found"] == "emotion_analysis"
    )  # Assuming this is the key in stored data
    assert json_data["data"] == mock_full_results["results"]["emotion_analysis"]


def test_get_specific_analysis_result_not_found(client, redis_client):
    file_id = "specific_res_not_found.txt"

    # Case 1: filemeta missing
    response_no_meta = client.get(
        f"/api/conversations/{file_id}/results/emotion_analysis"
    )
    assert response_no_meta.status_code == 404
    assert (
        "Conversation metadata not found" in response_no_meta.get_json()["description"]
    )

    # Case 2: analysisresult (main result file) missing
    redis_client.hmset(f"filemeta:{file_id}", {"status": "COMPLETED"})  # Meta exists
    response_no_main_result = client.get(
        f"/api/conversations/{file_id}/results/emotion_analysis"
    )
    assert response_no_main_result.status_code == 404
    assert (
        "Analysis result data not found in Redis"
        in response_no_main_result.get_json()["description"]
    )
    redis_client.delete(f"filemeta:{file_id}")  # clean up for next case

    # Case 3: Specific analysis_type key missing in results
    redis_client.hmset(f"filemeta:{file_id}", {"status": "COMPLETED"})
    mock_partial_results = {
        "results": {"persuasion_analysis": {"effectiveness": "low"}},
        "errors": [],
    }
    redis_client.set(f"analysisresult:{file_id}", json.dumps(mock_partial_results))
    response_no_type = client.get(
        f"/api/conversations/{file_id}/results/emotion_analysis"
    )  # Requesting emotion
    assert response_no_type.status_code == 404
    assert (
        "Invalid analysis type 'emotion_analysis'"
        in response_no_type.get_json()["description"]
    )

    # Case 4: Analysis not yet complete
    redis_client.hmset(
        f"filemeta:{file_id}", {"status": "PROCESSING"}
    )  # Status is processing
    # result data may or may not exist yet
    response_not_complete = client.get(
        f"/api/conversations/{file_id}/results/emotion_analysis"
    )
    assert response_not_complete.status_code == 409  # Conflict / Not ready
    assert (
        "Analysis not yet complete or failed"
        in response_not_complete.get_json()["description"]
    )


# All planned API route tests updated for Redis.
