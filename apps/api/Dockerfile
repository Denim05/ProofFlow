# ProofFlow API — Production/Staging Container
# Base image with Python 3.11-slim
FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app:/app/apps/api"

WORKDIR /app

# Install security updates and curl for healthcheck
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY apps/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Create non-root user and application directories
RUN groupadd -g 10001 proofflow && \
    useradd -u 10001 -g proofflow -s /bin/bash -m proofflow && \
    mkdir -p /app/storage/evidence /app/storage/temp && \
    chown -R proofflow:proofflow /app

# Copy application source code
COPY apps/api /app/apps/api
COPY ml /app/ml

# Ensure permissions for non-root user
RUN chown -R proofflow:proofflow /app

USER proofflow

# Mount point for persistent evidence storage
VOLUME ["/app/storage/evidence"]

EXPOSE 8000

# Container liveness and readiness probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
