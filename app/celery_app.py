from celery import Celery  # type: ignore

# TODO: Configuration should ideally come from Flask app config
CELERY_BROKER_URL = "redis://localhost:6379/0"
CELERY_RESULT_BACKEND = "redis://localhost:6379/0"

celery = Celery(
    __name__,
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["app.tasks"],
)  # Point to where tasks are defined

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],  # Ensure Celery uses JSON for messages
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Optional: Add a task time limit
    # task_time_limit=300, # 5 minutes
)


# Optional: If you want to integrate Celery configuration with Flask's config
def init_celery(app):
    celery.conf.update(app.config)

    # Subclass Task to automatically push Flask app context
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    # Store celery instance on app for access in routes (e.g. for AsyncResult with app=celery_instance)
    app.extensions = getattr(app, "extensions", {})
    app.extensions["celery"] = celery
    return celery
