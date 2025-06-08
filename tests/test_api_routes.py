import pytest  # type: ignore
from io import BytesIO
from app.models import Conversation, db  # Import models


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["status"] == "OK"
    assert json_data["database"] == "OK"  # Assumes test DB is set up and working


def test_upload_file_success(client, clean_db):
    # Test successful file upload
    data = {
        "file": (BytesIO(b"Speaker A: Hello\nSpeaker B: Hi there"), "test_chat.txt"),
        "language": "en",
    }
    response = client.post("/api/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 201
    json_data = response.get_json()
    assert "file_id" in json_data
    assert "conversation_id" in json_data
    assert json_data["language"] == "en"

    # Check if conversation is in DB
    with client.application.app_context():
        convo = Conversation.query.get(json_data["conversation_id"])
        assert convo is not None
        assert convo.file_id == json_data["file_id"]
        assert convo.language == "en"
        assert convo.status == "UPLOADED"


def test_upload_file_invalid_type(client, clean_db):
    data = {"file": (BytesIO(b"some content"), "test.exe")}
    response = client.post("/api/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    json_data = response.get_json()
    assert "error" in json_data
    assert "File type not allowed" in json_data["error"]


def test_upload_file_unsupported_language(client, clean_db):
    data = {
        "file": (BytesIO(b"Speaker A: Hola"), "chat_es.txt"),
        "language": "fr",  # Unsupported
    }
    response = client.post("/api/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    json_data = response.get_json()
    assert "Unsupported language" in json_data["error"]


def test_list_conversations_empty(client, clean_db):
    response = client.get("/api/conversations")
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["conversations"] == []
    assert json_data["total_items"] == 0


def test_list_conversations_with_data_and_filter(client, clean_db):
    # Setup: Create a conversation directly or via upload
    with client.application.app_context():
        convo1 = Conversation(
            file_id="file1.txt",
            original_filename="file1.txt",
            status="COMPLETED",
            language="en",
        )
        convo2 = Conversation(
            file_id="file2.txt",
            original_filename="file2.txt",
            status="PROCESSING",
            language="es",
        )
        db.session.add_all([convo1, convo2])
        db.session.commit()

    # Test without filter
    response = client.get("/api/conversations")
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["total_items"] == 2

    # Test filter by status
    response_completed = client.get("/api/conversations?status=COMPLETED")
    assert response_completed.status_code == 200
    json_data_completed = response_completed.get_json()
    assert json_data_completed["total_items"] == 1
    assert json_data_completed["conversations"][0]["file_id"] == "file1.txt"

    # Test filter by language
    response_es = client.get("/api/conversations?language=es")
    assert response_es.status_code == 200
    json_data_es = response_es.get_json()
    assert json_data_es["total_items"] == 1
    assert json_data_es["conversations"][0]["file_id"] == "file2.txt"

    # Test pagination params (basic validation)
    response_invalid_page = client.get("/api/conversations?page=0")
    assert response_invalid_page.status_code == 400


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


def test_start_analysis_task_success(client, clean_db, mock_celery_task):
    # Setup: Create a conversation
    file_id_for_analysis = "analysis_test_file.txt"
    with client.application.app_context():
        convo = Conversation(
            file_id=file_id_for_analysis,
            original_filename="analysis_test_file.txt",
            status="UPLOADED",
        )
        db.session.add(convo)
        db.session.commit()
        # convo_id = convo.id # If needed

    response = client.post(f"/api/analyze/{file_id_for_analysis}")
    assert response.status_code == 202  # Accepted
    json_data = response.get_json()
    assert json_data["message"] == "Analysis task started."
    assert json_data["task_id"] == "mock_celery_task_id_123"  # From our mock

    # Verify Celery task's delay method was called
    mock_celery_task.assert_called_once_with(file_id_for_analysis)

    # Verify DB status update
    with client.application.app_context():
        updated_convo = Conversation.query.filter_by(
            file_id=file_id_for_analysis
        ).first()
        assert updated_convo.status == "PENDING_ANALYSIS"
        assert updated_convo.celery_task_id == "mock_celery_task_id_123"


def test_start_analysis_task_file_not_found(client, clean_db, mock_celery_task):
    response = client.post("/api/analyze/non_existent_file.txt")
    assert response.status_code == 404  # Conversation not found


# More tests needed for status/result endpoints, especially mocking Celery AsyncResult
# and DB states. For now, this provides a starting point.
