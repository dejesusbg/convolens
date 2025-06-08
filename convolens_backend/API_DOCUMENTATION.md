# Convolens Backend API Documentation

Version: 1.0 (MVP + Enhancements)

## Base URL
The API is served from the root of the application. If running locally via Docker Compose, this might be \`http://localhost:5000\`.

## Authentication
Currently, the API does not require authentication. This will be addressed in future versions.

## Common Error Responses

Errors are generally returned in a JSON format:
\`\`\`json
{
  "error": "Error Type",
  "message": "Descriptive message about the error"
}
\`\`\`
Specific error codes are documented per endpoint. Common ones include:
- \`400 Bad Request\`: Invalid input, missing parameters, etc.
- \`404 Not Found\`: Resource not found.
- \`409 Conflict\`: Action cannot be performed due to current state (e.g., trying to re-analyze an already completed task without 'force').
- \`500 Internal Server Error\`: An unexpected error on the server.

---

## Endpoints

### 1. Health Check

- **Endpoint:** \`GET /health\`
- **Description:** Checks the health of the application and its database connection.
- **Request:** None
- **Success Response (200 OK):**
  \`\`\`json
  {
    "status": "OK",
    "database": "OK"
    // "database" might show an error message if connection fails
    // "redis_ping": "PONG" // (If redis check is added)
  }
  \`\`\`

### 2. Upload Conversation File

- **Endpoint:** \`POST /api/upload\`
- **Description:** Uploads a conversation file (TXT, JSON, CSV) for analysis.
- **Request Type:** \`multipart/form-data\`
- **Form Fields:**
    - \`file\`: The conversation file (required).
    - \`language\`: (Optional) Language code for the conversation (e.g., "en", "es"). Defaults to "en". Currently supported: "en", "es".
- **Success Response (201 Created):**
  \`\`\`json
  {
    "message": "File uploaded successfully and conversation record created.",
    "file_id": "generated-uuid-filename.ext",
    "conversation_id": 123, // Database ID of the conversation record
    "language": "en" // Language code used
  }
  \`\`\`
- **Error Responses:**
    - \`400 Bad Request\`: No file part, no selected file, unsupported language, file type not allowed.
    - \`500 Internal Server Error\`: If file saving or database record creation fails.

### 3. List Conversations

- **Endpoint:** \`GET /api/conversations\`
- **Description:** Retrieves a paginated list of uploaded conversations with filtering options.
- **Query Parameters:**
    - \`page\` (optional, integer): Page number for pagination. Default: 1.
    - \`per_page\` (optional, integer): Number of items per page. Default: 10. Max: 100.
    - \`status\` (optional, string): Filter by conversation status (e.g., "UPLOADED", "PROCESSING", "COMPLETED", "FAILED").
    - \`language\` (optional, string): Filter by language code (e.g., "en", "es").
- **Success Response (200 OK):**
  \`\`\`json
  {
    "conversations": [
      {
        "id": 123,
        "file_id": "generated-uuid-filename.ext",
        "original_filename": "my_chat.txt",
        "status": "COMPLETED",
        "language": "en",
        "upload_timestamp": "YYYY-MM-DDTHH:MM:SS.ffffff",
        "celery_task_id": "celery-task-uuid",
        "details_url": "/api/conversations/123",
        "analysis_result_url": "/api/analysis_result/celery-task-uuid"
      }
      // ... more conversations
    ],
    "total_pages": 5,
    "current_page": 1,
    "per_page": 10,
    "total_items": 50
  }
  \`\`\`
- **Error Responses:**
    - \`400 Bad Request\`: Invalid \`page\`, \`per_page\`, or \`status\` filter values.

### 4. Get Conversation Details

- **Endpoint:** \`GET /api/conversations/<conversation_identifier>\`
- **Description:** Retrieves detailed metadata for a specific conversation.
- **Path Parameters:**
    - \`conversation_identifier\`: The database ID (integer) or the \`file_id\` (string) of the conversation.
- **Success Response (200 OK):**
  \`\`\`json
  {
    "id": 123,
    "file_id": "generated-uuid-filename.ext",
    "original_filename": "my_chat.txt",
    "status": "COMPLETED",
    "language": "en",
    "upload_timestamp": "YYYY-MM-DDTHH:MM:SS.ffffff",
    "celery_task_id": "celery-task-uuid",
    "analysis_result_summary_url": "/api/analysis_result/celery-task-uuid",
    "emotion_results_url": "/api/conversations/123/results/emotion_analysis",
    "persuasion_results_url": "/api/conversations/123/results/persuasion_analysis"
    // ... other specific result URLs
  }
  \`\`\`
- **Error Responses:**
    - \`404 Not Found\`: If the conversation with the given identifier is not found.

### 5. Get Specific Analysis Result for a Conversation

- **Endpoint:** \`GET /api/conversations/<conversation_identifier>/results/<analysis_type>\`
- **Description:** Retrieves a specific part of the analysis results for a completed conversation.
- **Path Parameters:**
    - \`conversation_identifier\`: The database ID (integer) or the \`file_id\` (string) of the conversation.
    - \`analysis_type\`: The key of the analysis result to retrieve (e.g., "speaker_statistics", "emotion_analysis", "persuasion_analysis", "tactic_detection", "influence_graph").
- **Success Response (200 OK):**
  \`\`\`json
  {
    "conversation_id": 123,
    "file_id": "generated-uuid-filename.ext",
    "analysis_type_requested": "emotion_analysis",
    "analysis_type_found": "emotion_analysis", // Actual key found in results
    "data": {
      // ... content of the specific analysis, e.g.:
      // "emotion_analysis_engine": "text2emotion",
      // "results": [ { "text": "...", "emotions": { ... } } ]
    }
  }
  \`\`\`
- **Error Responses:**
    - \`404 Not Found\`: Conversation or specific analysis result data not found.
    - \`409 Conflict\`: If analysis is not yet complete or has failed.

### 6. Start Analysis Task

- **Endpoint:** \`POST /api/analyze/<file_id>\`
- **Description:** Initiates an asynchronous analysis task for a previously uploaded file.
- **Path Parameters:**
    - \`file_id\`: The \`file_id\` of the conversation to analyze.
- **Query Parameters:**
    - \`force\` (optional, boolean): If set to \`true\`, will attempt to start analysis even if a previous analysis exists for this file. Default: \`false\`.
- **Success Response (202 Accepted):**
  \`\`\`json
  {
    "message": "Analysis task started.",
    "task_id": "celery-task-uuid",
    "file_id": "generated-uuid-filename.ext",
    "conversation_id": 123,
    "status_url": "/api/analysis_status/celery-task-uuid",
    "result_url": "/api/analysis_result/celery-task-uuid"
  }
  \`\`\`
- **Error Responses:**
    - \`400 Bad Request\`: Invalid \`file_id\` format.
    - \`404 Not Found\`: If the conversation with the given \`file_id\` is not found.
    - \`409 Conflict\`: If analysis is already processing or completed for this file and \`force=true\` is not used.
    - \`500 Internal Server Error\`: If failed to update conversation status for the task.

### 7. Get Analysis Task Status

- **Endpoint:** \`GET /api/analysis_status/<task_id>\`
- **Description:** Retrieves the current status of an asynchronous analysis task.
- **Path Parameters:**
    - \`task_id\`: The Celery task ID obtained from the "Start Analysis Task" endpoint.
- **Success Response (200 OK):**
  Response structure varies based on task state.
  Example (Processing):
  \`\`\`json
  {
    "task_id": "celery-task-uuid",
    "celery_state": "PROGRESS", // or PENDING, STARTED, SUCCESS, FAILURE
    "db_conversation_status": "PROCESSING", // Status from Conversation model
    "status_message": "Task running.",
    "progress": { "current": 2, "total": 5, "status": "Analyzing emotions..." }
  }
  \`\`\`
  Example (Completed):
  \`\`\`json
  {
    "task_id": "celery-task-uuid",
    "celery_state": "SUCCESS",
    "db_conversation_status": "COMPLETED",
    "authoritative_status": "COMPLETED", // Indicates final status from DB
    "status_message": "Final status from DB: COMPLETED"
  }
  \`\`\`
- **Error Responses:** (Generally relies on global 404 if task_id does not map to a conversation, or returns status like "TASK_ID_NOT_IN_DB" for `db_conversation_status`).

### 8. Get Analysis Task Result (Full Result)

- **Endpoint:** \`GET /api/analysis_result/<task_id>\`
- **Description:** Retrieves the full analysis results for a completed task. Primarily fetches from the database.
- **Path Parameters:**
    - \`task_id\`: The Celery task ID.
- **Success Response (200 OK):**
  \`\`\`json
  {
    "task_id": "celery-task-uuid",
    "file_id": "generated-uuid-filename.ext",
    "conversation_id": 123,
    "final_db_status": "COMPLETED", // e.g., COMPLETED, COMPLETED_WITH_ERRORS
    "analysis_output": {
      // This is the structure saved by the Celery task into AnalysisResult.data
      "task_status_reported": "SUCCESS", // or "COMPLETED_WITH_ERRORS"
      "results": {
        "speaker_statistics": { /* ... */ },
        "emotion_analysis": { /* ... */ },
        "persuasion_analysis": { /* ... */ },
        "tactic_detection": { /* ... */ },
        "influence_graph": { /* ... */ }
      },
      "errors": [ /* list of error strings if any occurred during sub-analyses */ ]
    }
  }
  \`\`\`
- **Error Responses:**
    - \`202 Accepted\`: If the task is not yet complete.
      \`\`\`json
      {
        "message": "Analysis not yet complete or results unavailable.",
        "task_id": "celery-task-uuid",
        "db_status": "PROCESSING",
        "celery_state": "PROGRESS"
      }
      \`\`\`
    - \`404 Not Found\`: If no conversation or analysis result record is found for the task ID.

---
This documentation provides an overview of the Convolens backend API.
EOL
