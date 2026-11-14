# Multi-stage Dockerfile for FastAPI Python Backend
FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing .pyc and buffer stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend app source code
COPY . .

# Expose API port
EXPOSE 8000

# Start Uvicorn
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
