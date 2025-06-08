import pytest  # type: ignore
from app.app import create_app
from app.models import db, Conversation, AnalysisResult
import os
import tempfile
from io import BytesIO


@pytest.fixture(scope="session")
def app():
    """Session-wide test Flask app."""
    # Use a temporary SQLite DB for testing to avoid interfering with dev DB
    # And to ensure a clean state for each test session (or module/function).
    # For simplicity in this subtask, we'll override the SQLALCHEMY_DATABASE_URI.
    # A more robust setup might involve a separate config file for testing.

    # Create a temporary file for the SQLite database
    # db_fd, db_path = tempfile.mkstemp(suffix='.sqlite')
    # print(f"Using test database: {db_path}")

    # Forcing SQLite in memory for tests for speed and isolation
    # Note: Some PostgreSQL specific features like JSONB might behave differently or not be available.
    # For true integration tests, a test PostgreSQL instance is better.
    # For now, this focuses on unit/functional tests of Flask logic.
    # Using a file-based SQLite for persistence across test client requests if needed.

    # Using a named temporary file for SQLite
    # This ensures it has a path that can be used by SQLAlchemy
    # temp_db_file = tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False)
    # test_db_url = f"sqlite:///{temp_db_file.name}"
    # temp_db_file.close() # Close it so SQLAlchemy can open it

    # Simplest for now: in-memory SQLite. This won't persist across different parts of tests
    # if they re-initialize app, but for a single test client session it's fine.
    # For tests involving Celery tasks that run out-of-process, this won't work well
    # as the worker won't see the in-memory DB.
    # Given the current scope, let's try file-based temp SQLite.

    # Create a temporary directory for the instance folder and SQLite DB
    temp_dir = tempfile.TemporaryDirectory()
    instance_path = os.path.join(temp_dir.name, "instance")
    os.makedirs(instance_path, exist_ok=True)
    test_db_path = os.path.join(instance_path, "test.sqlite")
    test_db_url = f"sqlite:///{test_db_path}"

    flask_app = create_app()  # Create app using your factory
    flask_app.config.update(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": test_db_url,
            "CELERY_BROKER_URL": "memory://",  # Use in-memory broker for Celery for tests (if tasks are tested directly)
            "CELERY_RESULT_BACKEND": "cache+memory://",  # Or use a test Redis if available/mocked
            "UPLOAD_FOLDER": tempfile.mkdtemp(),  # Temporary upload folder
            "SERVER_NAME": "localhost.test",  # For url_for to work without active request context
        }
    )

    # print(f"App config during test setup: {flask_app.config}")

    with flask_app.app_context():
        db.create_all()  # Create tables in the test DB

    yield flask_app  # Provide the app object to tests

    # Teardown: clean up the temporary database file and directory
    # os.close(db_fd)
    # os.unlink(db_path)
    # os.unlink(temp_db_file.name) # Remove the named temporary file
    # if os.path.exists(test_db_path):
    #    os.unlink(test_db_path)
    temp_dir.cleanup()  # Cleans up the directory and its contents


@pytest.fixture()
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture()
def runner(app):
    """A test CLI runner for the app."""
    return app.test_cli_runner()


@pytest.fixture(scope="function")
def clean_db(app):
    """Clean database tables before each test function that needs it."""
    with app.app_context():
        # This is a simple way to clean. For more complex scenarios,
        # database transaction rollbacks or tools like pytest-postgresql might be used.
        # For SQLite, deleting and recreating is often fast enough.
        db.session.remove()
        db.drop_all()
        db.create_all()
    yield  # Test runs here
    # Optional: any post-test cleanup specific to this fixture if needed
