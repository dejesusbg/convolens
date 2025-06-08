from flask_sqlalchemy import SQLAlchemy  # type: ignore
from sqlalchemy.dialects.postgresql import JSONB  # type: ignore
from datetime import datetime

db = SQLAlchemy()

# class ConversationStatus(enum.Enum):
#     UPLOADED = "UPLOADED"
#     PENDING_ANALYSIS = "PENDING_ANALYSIS"
#     PROCESSING = "PROCESSING"
#     COMPLETED = "COMPLETED"
#     COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
#     FAILED = "FAILED"


class Conversation(db.Model):
    __tablename__ = "conversations"

    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.String(128), unique=True, nullable=False, index=True)
    original_filename = db.Column(db.String(255), nullable=True)
    upload_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default="UPLOADED")
    celery_task_id = db.Column(db.String(128), nullable=True, index=True)
    language = db.Column(db.String(10), default="en", nullable=False)

    analysis_result = db.relationship(
        "AnalysisResult",
        backref="conversation",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Conversation {self.file_id} ({self.status}) Lang: {self.language}>"


class AnalysisResult(db.Model):
    __tablename__ = "analysis_results"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer, db.ForeignKey("conversations.id"), nullable=False, unique=True
    )
    data = db.Column(JSONB, nullable=False)
    created_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    updated_timestamp = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self):
        return f"<AnalysisResult for Conversation ID {self.conversation_id}>"
