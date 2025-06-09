from celery import Celery  # type: ignore

# TODO: Configuration should ideally come from Flask app config
broker_url = "redis://localhost:6379/0"
result_backend = "redis://localhost:6379/0"

celery = Celery(
    __name__,
    broker=broker_url,
    backend=result_backend,
    include=["app.tasks"],
)  # Point to where tasks are defined

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],  # Ensure Celery uses JSON for messages
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    result_backend=result_backend,  # Explicitly specify the backend here again
    broker_url=broker_url,  # Explicitly specify the broker URL here again
)


# Optional: If you want to integrate Celery configuration with Flask's config
def init_celery(app):
    # celery.conf.update(app.config)

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
