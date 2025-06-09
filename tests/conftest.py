import pytest  # type: ignore
import fakeredis  # type: ignore
from app.app import create_app

# from app.models import db, Conversation, AnalysisResult # Removed DB models
import os
import tempfile

# from io import BytesIO # BytesIO not used directly here, can be removed if not needed by other fixtures


@pytest.fixture(scope="session")
def app():
    """Session-wide test Flask app."""
    flask_app = create_app()  # Create app using your factory

    # Configure a temporary directory for uploads for the test session
    upload_temp_dir = tempfile.TemporaryDirectory()

    flask_app.config.update(
        {
            "TESTING": True,
            # "SQLALCHEMY_DATABASE_URI": test_db_url, # Removed DB config
            "CELERY_BROKER_URL": "memory://",  # Use in-memory broker for Celery
            "CELERY_RESULT_BACKEND": "cache+memory://",  # Use in-memory result backend for Celery
            "UPLOAD_FOLDER": upload_temp_dir.name,  # Use the temp dir for uploads
            "SERVER_NAME": "localhost.test",  # For url_for to work without active request context
            "REDIS_CACHE_TTL_SECONDS": 3600,  # Example TTL for tests
        }
    )

    # Initialize fakeredis and patch the app's redis_client
    # This single instance will be shared across the test session.
    # For test isolation at the function level, this could be a function-scoped fixture.
    # However, app context setup usually happens once per session for efficiency.
    # Individual tests can clear redis if needed: `app.redis_client.flushall()`
    fake_redis_client = fakeredis.FakeStrictRedis(
        decode_responses=True
    )  # Matched decode_responses with app
    flask_app.redis_client = fake_redis_client

    # print(f"App config during test setup: {flask_app.config}")
    # print(f"Using fakeredis client: {flask_app.redis_client}")

    yield flask_app  # Provide the app object to tests

    # Teardown: clean up the temporary upload directory
    upload_temp_dir.cleanup()


@pytest.fixture()
def client(app):
    """A test client for the app."""
    # Ensure redis is clean before each test that uses the client if needed
    # app.redis_client.flushall() # Add this if tests interfere via Redis state
    return app.test_client()


@pytest.fixture()
def runner(app):
    """A test CLI runner for the app."""
    return app.test_cli_runner()


# Removed clean_db fixture as it was DB specific.
# If Redis needs cleaning per test, it can be done in client fixture or individual tests.
# Example of a fixture to provide a clean redis client for each test:
@pytest.fixture(scope="function")
def redis_client(app):
    """Provides a clean fakeredis client for each test function."""
    # app.redis_client is the session-wide client from the app fixture
    app.redis_client.flushall()  # Clear before each test
    return app.redis_client
