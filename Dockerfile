FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

# Install system dependencies that might be needed
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev netcat-traditional build-essential && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m nltk.downloader punkt stopwords

# Copy the rest of the application code into the container at /app
COPY . .

# Expose the port the app runs on (for Flask/Gunicorn)
EXPOSE 5000
