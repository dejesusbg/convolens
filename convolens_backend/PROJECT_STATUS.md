# Project Status: Convolens Backend

This document tracks the development progress of the Convolens backend.

## Current State:
- **Steps 1-7** - Completed
- **Step 8: Implement Fallacy & Manipulation Detection (v1.0 - Rule-Based)** - Completed
- **Step 9: Database Integration (PostgreSQL)** - In Progress
    - Added `Flask-SQLAlchemy` and `psycopg2-binary` to `requirements.txt`.
    - Defined SQLAlchemy models in `app/models.py`:
        - `Conversation`: Tracks uploaded files, original names, status (enum `ConversationStatus`), Celery task ID.
        - `AnalysisResult`: Stores analysis output (as JSONB) linked to a `Conversation`.
    - Configured PostgreSQL connection URI in `app/app.py` (defaulting to `postgresql://user:password@localhost:5432/convolens_db`, uses `DATABASE_URL` env var if set).
    - Initialized `db` (SQLAlchemy instance) and called `db.create_all()` in `app/app.py` to create tables.
    - Modified `/api/upload`: Creates a `Conversation` record upon successful file upload.
    - Modified `run_full_analysis` Celery task in `app/tasks.py`:
        - Retrieves `Conversation` record by `file_id`.
        - Updates `Conversation.status` (e.g., `PROCESSING`, `COMPLETED`, `FAILED`) and `celery_task_id`.
        - Saves the full analysis results (including any errors from sub-modules) into `AnalysisResult.data` (JSONB field). The saved data includes a task status, the main results payload, and an errors list.
    - Modified `/api/analysis_status/<task_id>`:
        - Now also checks and returns status from the `Conversation` table in the DB, alongside Celery's real-time state, providing a more holistic status.
    - Modified `/api/analysis_result/<task_id>`:
        - Primarily fetches results from the `AnalysisResult` table in the DB, making results persistent. Includes fallback checks to Celery state if DB record is missing.
    - Updated `/api/files` to list conversations from the database.
    - Added basic DB health check to `/health` endpoint.

## Completed Features:
- Basic Flask application setup & API endpoints.
- Asynchronous analysis pipeline via Celery.
- Modules for: Speaker ID/Stats, Emotion, Influence Graph, Persuasion Scoring, Fallacy/Manipulation Detection.
- PostgreSQL database integration:
    - Storage for conversation metadata and analysis results.
    - API and Celery tasks interact with the database for state and results.

## Missing Features / Next Steps (from original plan):
- *DB Setup: Instructions/script for setting up PostgreSQL DB and user locally.*
- *Migrations: Implement Flask-Migrate for schema changes.*
- **Refine API and Add Endpoints for v1.0 features** (e.g., endpoints to get specific parts of analysis, list conversations with filters).
- **Containerization with Docker** (Will include PostgreSQL service).
- **Basic Security and Error Handling** (Ongoing; DB error handling added).
- **Documentation (API_DOCUMENTATION.md)** (Needs significant update for DB interaction and refined async flow).
- **Testing (Unit/Integration tests for DB models, interactions, task DB updates)**.
EOL
