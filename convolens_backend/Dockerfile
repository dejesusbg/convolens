# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies that might be needed by psycopg2 or other libs
# For slim buster, common ones are:
RUN apt-get update && apt-get install -y --no-install-recommends     gcc     libpq-dev     # netcat-traditional \ # Useful for wait-for-it scripts, but not strictly needed by app
    && apt-get clean     && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container at /app
# This assumes Dockerfile is in 'convolens_backend' directory.
# If Dockerfile is outside, the COPY path needs to be 'convolens_backend/app' etc.
# For this setup, assuming Dockerfile is IN 'convolens_backend/'
COPY . .
# If your app structure is convolens_backend/app, and Dockerfile is in convolens_backend:
# COPY app ./app
# COPY requirements.txt .
# COPY run.py . # If you have a top-level run script for gunicorn

# Expose the port the app runs on (for Flask/Gunicorn)
EXPOSE 5000

# Default command (can be overridden by docker-compose)
# For example, to run Gunicorn directly if app.py is executable or via module:
# CMD ["gunicorn", "-b", "0.0.0.0:5000", "app.app:create_app()"]
# For now, no default CMD here, it will be set in docker-compose.yml
# This makes the image more flexible for different entrypoints (web, worker).
