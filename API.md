# Convolens Backend API Documentation

Version: 1.0 (MVP + Enhancements)

## Base URL

The API is served from the root of the application. If running locally via Docker Compose, this might be \`http://localhost:5000\`.

## Overview

The Convolens backend system processes conversation files to extract various analytical insights. It uses Celery for asynchronous task management and **Redis for temporary storage of file metadata and analysis results.**
**Important: All uploaded data and analysis results are transient and stored in a Redis cache. Data will expire and be removed after a configurable period (default is 10 minutes). This system is not designed for long-term data persistence.**

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

- **Endpoint:** \`GET /api/health\`
- **Description:** Checks the health of the application and its connection to Redis.
- **Request:** None
- **Success Response (200 OK):**
  \`\`\`json
  {
  "status": "OK",
  "redis_connection": "OK"
  // "redis_connection" might show an error message if connection fails
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
  "message": "File uploaded successfully.",
  "file_id": "generated-uuid-filename.ext",
  "language": "en" // Language code used
  }
  \`\`\`
- **Error Responses:**
  - \`400 Bad Request\`: No file part, no selected file, unsupported language, file type not allowed.
  - \`500 Internal Server Error\`: If file saving or storing metadata in Redis fails.

### 3. List Conversations

- **Endpoint:** \`GET /api/conversations\`
- **Description:** Retrieves a list of recently uploaded/processed files currently available in the Redis cache. Pagination is not supported; all cached items matching filters are returned.
- **Query Parameters:**
  - \`status\` (optional, string): Filter by conversation status (e.g., "UPLOADED", "PROCESSING", "COMPLETED", "FAILED"). Applies only to currently cached items.
  - \`language\` (optional, string): Filter by language code (e.g., "en", "es"). Applies only to currently cached items.
- **Success Response (200 OK):**
  \`\`\`json
  {
  "conversations": [
  {
  "id": "generated-uuid-filename.ext", // file_id is used as the primary identifier
  "file_id": "generated-uuid-filename.ext",
  "original_filename": "my_chat.txt",
  "status": "COMPLETED",
  "language": "en",
  "upload_timestamp": "YYYY-MM-DDTHH:MM:SS.ffffffZ", // ISO format from Redis
  "celery_task_id": "celery-task-uuid",
  "details_url": "/api/conversations/generated-uuid-filename.ext",
  "analysis_result_url": "/api/analysis_result/celery-task-uuid" // if task ID exists
  }
  // ... more conversations
  ],
  "total_items": 2 // Total number of items matching filters in cache
  }
  \`\`\`
- **Error Responses:**
  - \`400 Bad Request\`: Invalid \`status\` or \`language\` filter values.

### 4. Get Conversation Details

- **Endpoint:** \`GET /api/conversations/<conversation_identifier>\`
- **Description:** Retrieves detailed metadata for a specific file/conversation from the Redis cache.
- **Path Parameters:**
  - \`conversation_identifier\`: The \`file_id\` (string) of the conversation.
- **Success Response (200 OK):**
  \`\`\`json
  {
  "id": "generated-uuid-filename.ext", // file_id is used as the primary identifier
  "file_id": "generated-uuid-filename.ext",
  "original_filename": "my_chat.txt",
  "status": "COMPLETED",
  "language": "en",
  "upload_timestamp": "YYYY-MM-DDTHH:MM:SS.ffffffZ", // ISO format from Redis
  "celery_task_id": "celery-task-uuid", // if analysis started
  "analysis_result_summary_url": "/api/analysis_result/celery-task-uuid", // if task ID exists
  "emotion_results_url": "/api/conversations/generated-uuid-filename.ext/results/emotion_analysis",
  "persuasion_results_url": "/api/conversations/generated-uuid-filename.ext/results/persuasion_analysis"
  // ... other specific result URLs
  }
  \`\`\`
- **Error Responses:**
  - \`404 Not Found\`: If the conversation metadata for the given \`file_id\` is not found in Redis.

### 5. Get Specific Analysis Result for a Conversation

- **Endpoint:** \`GET /api/conversations/<file_id>/results/<analysis_type>\`
- **Description:** Retrieves a specific part of the analysis results for a completed conversation from the Redis cache.
- **Path Parameters:**
  - \`file_id\`: The \`file_id\` (string) of the conversation.
  - \`analysis_type\`: The key of the analysis result to retrieve (e.g., "speaker_statistics", "emotion_analysis", "persuasion_analysis", "tactic_detection", "influence_graph").
- **Success Response (200 OK):**
  \`\`\`json
  {
  "file_id": "generated-uuid-filename.ext",
  "analysis_type_requested": "emotion_analysis",
  "analysis_type_found": "emotion_analysis", // Actual key found in results
  "data": {
  // ... content of the specific analysis, e.g.:
  // "results": [ { "text": "...", "emotions": { ... } } ]
  }
  }
  \`\`\`
- **Error Responses:**
  - \`404 Not Found\`: Conversation metadata or analysis result data not found in Redis.
  - \`409 Conflict\`: If analysis is not yet complete or has failed (check status from file metadata in Redis).

### 6. Start Analysis Task

- **Endpoint:** \`POST /api/analyze/<file_id>\`
- **Description:** Initiates an asynchronous analysis task for a previously uploaded file (file metadata must exist in Redis).
- **Path Parameters:**
  - \`file_id\`: The \`file_id\` of the conversation to analyze.
- **Query Parameters:**
  - \`force\` (optional, boolean): If set to \`true\`, will attempt to start analysis even if a previous analysis exists (based on status in Redis). Default: \`false\`.
- **Success Response (202 Accepted):**
  \`\`\`json
  {
  "message": "Analysis task started.",
  "task_id": "celery-task-uuid",
  "file_id": "generated-uuid-filename.ext",
  "status_url": "/api/analysis_status/celery-task-uuid",
  "result_url": "/api/analysis_result/celery-task-uuid"
  }
  \`\`\`
- **Error Responses:**
  - \`400 Bad Request\`: Invalid \`file_id\` format.
  - \`404 Not Found\`: If file metadata for the given \`file_id\` is not found in Redis.
  - \`409 Conflict\`: If analysis is already processing or completed (based on status in Redis) and \`force=true\` is not used.
  - \`500 Internal Server Error\`: If failed to update metadata in Redis.

### 7. Get Analysis Task Status

- **Endpoint:** \`GET /api/analysis_status/<task_id>\`
- **Description:** Retrieves the current status of an asynchronous analysis task. It combines Celery's task state with the file processing status stored in Redis (if the task ID can be mapped to a file ID).
- **Path Parameters:**
  - \`task_id\`: The Celery task ID.
- **Success Response (200 OK):**
  Response structure varies based on task state.
  Example (Processing):
  \`\`\`json
  {
  "task_id": "celery-task-uuid",
  "celery_state": "PROGRESS", // or PENDING, STARTED, SUCCESS, FAILURE
  "file_id": "generated-uuid-filename.ext", // If mapping found
  "redis_file_status": "PROCESSING", // Status from Redis filemeta
  "status_message": "Task running.",
  "progress": { "current": 2, "total": 5, "status": "Analyzing emotions..." }
  }
  \`\`\`
  Example (Completed):
  \`\`\`json
  {
  "task_id": "celery-task-uuid",
  "celery_state": "SUCCESS",
  "file_id": "generated-uuid-filename.ext",
  "redis_file_status": "COMPLETED",
  "authoritative_status": "COMPLETED", // Indicates final status from Redis
  "status_message": "Final status from Redis: COMPLETED"
  }
  \`\`\`
- **Error Responses:** No specific errors beyond global ones; missing task_id to file_id mapping will result in a response without `file_id` and `redis_file_status`.

### 8. Get Analysis Task Result (Full Result)

- **Endpoint:** \`GET /api/analysis_result/<task_id>\`
- **Description:** Retrieves the full analysis results for a completed task. This relies on a temporary Redis mapping from \`task_id\` to \`file_id\` to locate the results.
- **Path Parameters:**
  - \`task_id\`: The Celery task ID.
- **Success Response (200 OK):**
  \`\`\`json
  {
  "task_id": "celery-task-uuid",
  "file_id": "generated-uuid-filename.ext",
  "final_file_status": "COMPLETED", // e.g., COMPLETED, COMPLETED_WITH_ERRORS (from Redis filemeta)
  "analysis_output": {
  // This is the structure saved by the Celery task into analysisresult:{file_id} in Redis
  "task_status_reported": "SUCCESS", // or "COMPLETED_WITH_ERRORS" (from Celery task return)
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
  - \`202 Accepted\`: If the analysis is not yet complete (based on status in Redis filemeta).
    \`\`\`json
    {
    "message": "Analysis not yet complete or results are not in a final state.",
    "task_id": "celery-task-uuid",
    "file_id": "generated-uuid-filename.ext",
    "current_file_status": "PROCESSING",
    "celery_task_state": "PROGRESS" // or other non-final Celery state
    }
    \`\`\`
  - \`404 Not Found\`: If the \`task_id\` to \`file_id\` mapping is not found, or if \`filemeta\` or \`analysisresult\` data for the \`file_id\` is not found in Redis.

---

## Data Persistence and Cache

**All file metadata and analysis results are stored temporarily in a Redis cache.** This means:
- Data is **not persisted long-term**.
- Cached items have a **Time-To-Live (TTL)** and will be automatically deleted from Redis after this period.
- The default TTL is **10 minutes (600 seconds)** but can be configured via the \`REDIS_CACHE_TTL_SECONDS\` environment variable.
- This system is designed for quick, on-demand analysis with transient storage. Do not rely on it for permanent data retention.

This documentation provides an overview of the Convolens backend API.
