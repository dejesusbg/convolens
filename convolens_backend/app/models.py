from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
import enum

db = SQLAlchemy()

class ConversationStatus(enum.Enum):
    UPLOADED = "UPLOADED"
    PENDING_ANALYSIS = "PENDING_ANALYSIS" # Task has been dispatched
    PROCESSING = "PROCESSING" # Task worker picked it up
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED" # Task failed critically or file invalid

class Conversation(db.Model):
    __tablename__ = 'conversations'

    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.String(128), unique=True, nullable=False, index=True) # Original UUID based name
    original_filename = db.Column(db.String(255), nullable=True)
    upload_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.Enum(ConversationStatus), default=ConversationStatus.UPLOADED)
    celery_task_id = db.Column(db.String(128), nullable=True, index=True)

    analysis_result = db.relationship('AnalysisResult', backref='conversation', uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Conversation {self.file_id} ({self.status})>'

class AnalysisResult(db.Model):
    __tablename__ = 'analysis_results'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False, unique=True)
    # Store the full JSON result from the analysis task
    data = db.Column(JSONB, nullable=False)
    # This 'data' field will store the 'results' dictionary from the Celery task
    # and potentially the 'errors' list as well, or errors can be part of the Conversation status/log.
    # For now, let's assume 'data' holds the 'results' part, and 'errors' can be in a sub-key or on Conversation.
    # Let's refine: data will hold the entire output of the task (status, results, errors).

    created_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    updated_timestamp = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<AnalysisResult for Conversation ID {self.conversation_id}>'

EOL
