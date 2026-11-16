# ==============================================================================
# CivicAudit AI - Backend Production Dockerfile
# Multi-Agent Procurement Forensic Engine
# ==============================================================================

FROM python:3.13-slim AS production

# Set Python environment variables for container stability
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000 \
    HOST=0.0.0.0

WORKDIR /app

# Install curl for container health checks and clean apt cache
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Create a secure, non-root user and group
RUN groupadd -g 10001 civicgroup && \
    useradd -u 10001 -g civicgroup -s /bin/bash -m civicuser

# Copy requirements and install Python dependencies (layer cached)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code and default assets
COPY . .

# Ensure data and reports directories exist with correct permissions
RUN mkdir -p /app/reports /app/data && \
    chown -R civicuser:civicgroup /app

# Switch to non-root execution
USER civicuser

# Expose API port
EXPOSE 8000

# Health check to verify API responsiveness
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/settings || exit 1

# Launch production server with Uvicorn
CMD ["uvicorn", "web_server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--access-log"]
