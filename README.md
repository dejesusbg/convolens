# Project Specification: Conversation-Based Influence & Persuasion Analyzer (Convolens)

## 1. Project Overview

**Convolens** is an **AI-powered web application** designed to provide a multi-dimensional analysis of text-based conversations. It analyzes influence, persuasion, emotional tone, manipulation tactics, and logical fallacies. The system offers interactive visualizations of interaction networks and is built for continuous model training and research extensibility.

## 2. Purpose & Scope

The **primary aim** of Convolens is to empower researchers, analysts, and business users to understand how speakers influence group consensus, identify persuasive strategies, and detect ethical or manipulative communication patterns. This supports evidence-based decision-making in areas like sales optimization, political debate analysis, social media moderation, and academic research on rhetoric.

### Scope Definition

- **Input**: JSON or TXT transcripts with speaker tags.
- **Core Analysis**: Speaker identification, persuasion scoring, emotion detection, logical fallacy detection, and manipulation highlighting.
- **Visualization**: Interactive influence graphs, time-series emotion/persuasion trends, and annotated transcripts.
- **Architecture**: Next.js + React (frontend), Python Flask (backend), and a modular AI/ML pipeline using TensorFlow/Keras and Hugging Face models. Redis is used for Celery and temporary caching of job data and results.
- **Data**: User-uploaded transcripts, with optional pre-labeled corpora for model fine-tuning. All uploaded data and analysis results are stored temporarily and subject to cache expiry.
- **Extensibility**: Includes continuous training workflows, research modules, and pluggable detectors.

## 3. Expected Outcomes & Release Plan

### 3.1. MVP Release (v0.1)

The initial MVP focuses on clean ingestion and a scalable NLP baseline:

- Upload and validate conversation files.
- Run transformer-based sentiment and emotion analysis.
- Extract basic speaker statistics.
- Build a first-pass influence graph using interaction frequency.
- Frontend charts and network graph with placeholder models.

### 3.2. Feature Expansion (v1.0)

This phase deepens the analytical capabilities with token-level feature extraction:

- **Persuasion Scoring**: Implement heuristic lexicons for ethos/pathos/logos (token/phrase-level) and a shallow ML model with token- and sentence-level features (e.g., LIWC, rhetorical markers).
- **Emotion Classification**: Fine-tune a transformer for multi-label output.
- **Fallacy & Manipulation Detection**: Develop rule-based detection with rich inputs (e.g., negation patterns, modal verbs) and a zero-shot fallback using prompt-engineered transformers.
- **Model Versioning**: Begin using MLflow or DVC.
- **Modular Backend**: Implement Flask routers and an async task layer with Celery.

### 3.3. Research & Training Pipeline (v2.x)

This phase focuses on advanced DNNs, fine-tuning, and continual learning:

- **Custom DNN Classifiers**: Train TensorFlow/Keras models for persuasion micro-strategies, multi-label logical fallacies, and manipulation subtypes (gaslighting, emotional blackmail).
- **Token-Based Feature Engineering**: Integrate POS tags, dependency parsing, rhetorical structure, and statistical embeddings (TF-IDF, averaged embeddings) alongside transformer embeddings.
- **Continuous Learning Loop**: Build a feedback-driven annotation UI and active learning for data sampling.
- **Model Tracking**: Monitor precision, recall, F1, and confidence intervals.

### 3.4. Documentation & Research Report

Comprehensive documentation and research outputs will include:

- Detailed design documents, API reference, and model architecture diagrams.
- A whitepaper on methodology and psycholinguistic foundations.
- Case studies demonstrating sales call analysis and political debate insights.

## 4. Functional Requirements

### 4.1. Data Ingestion

- Accept file uploads (.json, .txt, .csv) with a standardized schema.
- Validate speaker tags and timestamps.

### 4.2. Analysis Modules (Core)

- **Speaker Identification**: Parse speaker IDs and merge multi-platform formats.
- **Emotion Analysis**: Apply pre-trained transformer models or `text2emotion` patterns.
- **Persuasion Scoring**: Calculate scores based on logical appeal, emotional appeal, credibility markers, and rhetorical devices.
- **Logical Fallacy Detection**: Detect specific fallacies such as _ad hominem_, straw man, false dichotomy, and slippery slope.
- **Manipulation Detection**: Flag tactics like gaslighting, guilt-tripping, and emotional exploitation using rule-based and ML heuristics.

### 4.3. Visualization & Reporting

- **Interactive Influence Graph**: Visualize speakers as nodes with edges weighted by persuasion flow.
- **Trend Charts**: Display time-series data for sentiment, emotion intensity, and persuasion scores.
- **Annotated Transcript Viewer**: Highlight text segments corresponding to detected fallacies or manipulation.

### 4.4. User Interface

- Responsive Next.js pages.
- Drag-and-drop upload functionality with progress indicators.
- Filter controls for speaker, tactic, and date.

### 4.5. Security & Privacy

- TLS 1.3 encryption end-to-end.
- Optional data anonymization.
- Role-based access control (admin, researcher, viewer).

## 5. Non-Functional Requirements

- **Performance**: Average analysis latency of less than 5 seconds for a 1,000-message conversation.
- **Scalability**: Horizontally scalable backend via Docker and Kubernetes.
- **Reliability**: 99.9% uptime for core services.
- **Maintainability**: Modular codebase with linting, unit, and integration tests (>80% coverage).
- **Extensibility**: Plugin architecture for adding new detectors or visualizations.

## 6. Architecture & Technical Stack

### Frontend

- **Framework**: Next.js + React + TypeScript.
- **Styling**: TailwindCSS.
- **Components**: shadcn/ui.
- **Charting/Graphing**: recharts + react-force-graph.

### Backend

- **Language/Framework**: Python 3.13+ with Flask.
- **ASGI Server**: Uvicorn + Gunicorn.
- **Asynchronous Tasks**: Celery + Redis.
- **Caching & Temporary Storage**: Redis (for file metadata, analysis results, and Celery).
- **File Storage (Optional/Future)**: MinIO or S3 (for persistent file storage, not currently implemented for primary data).

### AI/ML Pipeline

- **Pre-trained Models**: Hugging Face transformers for sentiment and emotion.
- **Custom Models**: TensorFlow/Keras for persuasion micro-strategy and fallacy detection.
- **Data/Model Versioning**: DVC or MLflow for fine-tuning scripts.

### Deployment

- **Local Development**: Docker Compose.
- **Production**: Kubernetes (EKS/GKE).
- **CI/CD**: GitHub Actions for build, test, and deploy.

## Prerequisites / Setup (Local Development)

To run Convolens locally using Docker Compose, you will need:
- Docker
- Docker Compose

The `docker-compose.yml` will set up the following services:
- `web`: The Flask backend application.
- `worker`: The Celery worker for asynchronous analysis tasks.
- `redis`: The Redis instance used by Celery and for caching.
- (Previously `db`: PostgreSQL - This has been removed).

## Configuration

Key environment variables (can be set in `.env` file for local Docker Compose, or in your deployment environment):

- `FLASK_ENV`: Set to `development` or `production`.
- `CELERY_BROKER_URL`: URL for the Celery message broker (e.g., `redis://redis:6379/0`).
- `CELERY_RESULT_BACKEND`: URL for the Celery result backend (e.g., `redis://redis:6379/0`).
- `REDIS_CACHE_TTL_SECONDS`: (New) Time-To-Live in seconds for cached items in Redis. Default: `600` (10 minutes).
- (Removed) `DATABASE_URL`: No longer used.
- (Removed) `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`: No longer used.

## 7. AI/ML Components & Data Strategy

### 7.1. Emotion & Sentiment Analysis

- Utilize Hugging Face pipelines (e.g., `nlptown/bert-base-multilingual-uncased-sentiment`).
- Evaluate against `text2emotion` library for optimal speed and accuracy balance.

### 7.2. Persuasion Scoring

- **Token-level features**: Include discourse markers (e.g., “clearly,” “as you know”), rhetorical questions, analogies, intensifiers, modal verbs (“should,” “must” for assertiveness), and speaker-specific lexicons (ethos/pathos/logos words).
- **Modeling approach**: Initially, Regression and SVM/RandomForest with engineered features; later, a Transformer + DNN hybrid (concatenating BERT embeddings with handcrafted features).
- **ML Model**: A multi-class classifier trained on annotated dialogues (labels: logical appeal, emotional appeal, credibility cues).
- **Metrics**: Accuracy, macro-F1.

### 7.3. Logical Fallacy & Manipulation Detection

- **Feature fusion**: Combine token-level syntax (POS tags, clause depth, connectives) with contextual features (prior sentence polarity, topic shift).
- **Prompt templates**: Use for few-shot classification.
- **Continual learning**: Ingest user corrections to improve models via active learning pipelines.
- **Custom architecture**: Employ hierarchical attention models (context-aware) and fine-tune `roberta-base` or `bertweet` on annotated dialogue sets.
- **Custom DNN**: Define a taxonomy of fallacies and fine-tune BERT or RoBERTa in TensorFlow/Keras.
- **Zero-shot classification**: Leverage models like `facebook/bart-large-mnli` with prompt templates.

### 7.4. Continuous Training & Research Loop

- **Data labeling interface**: For expert feedback.
- **Retraining jobs**: Scheduled via Airflow or CI workflows.
- **Logging and model registry**: For version control.

## 8. Psychological & Rhetorical Foundations

Convolens is built upon strong theoretical foundations:

- **Theoretical Basis**: Aristotle’s modes of persuasion (ethos, pathos, logos), modern rhetorical theory, and argumentation mining research.
- **Psychological Approaches**: Framing effects, cognitive biases (anchoring, confirmation bias), and emotional contagion.

### Research Use Cases

- Political scientists measuring debate effectiveness.
- Psychologists studying manipulation tactics in online forums.
- Marketing teams optimizing sales scripts.

## 9. Target Users & Expert Roles

### Primary Users

- Researchers (linguistics, psychology, communication).
- Analysts (sales enablement, political campaign strategists).
- Social media and community managers.

### Expert Collaborators

- NLP Engineers & Data Scientists (model development).
- Cognitive Psychologists & Rhetoricians (taxonomy design, annotation guidelines).
- Frontend Engineers & UX Designers.

## 10. Future Directions & Research

- **Multimodal Extension**: Integrate audio (ASR + speaker diarization) and video (facial emotion recognition).
- **Cross-Language Analysis**: Support for Spanish and other languages, leveraging multilingual transformers.
- **Adaptive Dialogue Coaching**: Provide real-time recommendations to users on persuasive language.
- **Academic Publication**: Contribute datasets and code for open research.

## 11. Cognitive Modeling & Neuroscience Alignment

While not directly simulating biological neural systems, Convolens aligns with **cognitive and behavioral neuroscience** by computationally modeling psychological processes such as emotion recognition, influence dynamics, and decision-making biases. This bridges **AI-driven language analysis** with **human cognitive functions**, making the system relevant for both applied NLP and scientific exploration.

### Modeling Human Cognitive Processes

The system reflects **observable psychological patterns** studied in neuroscience:

#### ✅ Cognitive/Emotional Processing Simulation

Our models simulate how humans process emotional and persuasive language. For example:

> “This model detects emotional appeals using linguistic markers like urgency, fear, or guilt. These map to emotional processing systems in the brain, such as the **limbic system**, known for mediating fear responses and emotional salience.”

This connects NLP outputs to real-world psychological and neurobiological reactions, aligning with affective neuroscience and behavioral modeling.

#### ✅ Decision-Making & Cognitive Bias Mapping

Manipulation detection features are informed by well-established **cognitive biases**, including:

- **Anchoring**
- **Framing effects**
- **Guilt appeals and emotional coercion**

> “These biases, while modeled through language, correspond to behavioral phenomena studied in **decision neuroscience**, particularly in contexts involving value-based judgments, social influence, and emotional salience.”

#### ✅ Neural Representation & Social Cognition

Interaction visualizations (e.g., influence graphs) reflect how people track **social roles, intentions, and mental states**. These processes relate to:

- **Theory of Mind (ToM)**
- **Social perception**
- **Trust attribution**

> “Speaker dynamics and influence flow may simulate how individuals form mental models of others' intentions—cognitive tasks associated with the **temporoparietal junction (TPJ)** and **medial prefrontal cortex (mPFC)** in social neuroscience literature.”

## 12. Systems Thinking Perspective

Convolens, as a systems engineering–driven project, applies **systems thinking** to communication analysis. It models conversations as **complex, dynamic systems** with:

- Interacting agents (speakers).
- Emergent properties (e.g., consensus, polarization).
- Feedback loops (reinforcement, deflection, escalation).
- Hidden influences (subtle manipulation, emotional drift).

This framework supports **multi-scale analysis**—from token-level rhetorical tactics to conversation-wide influence trends—consistent with systems approaches in engineering and cognitive science.

**Document Status**: Living specification.
