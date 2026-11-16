# CivicAudit AI Backend - Docker Deployment Guide

This directory contains containerization configurations for both **development (hot-reloading)** and **production (hardened, multi-worker)** deployments.

---

## 📁 Files Overview

| File | Purpose |
|---|---|
| [`Dockerfile`](file:///c:/code/hackathon/backend/Dockerfile) | Production image (Python 3.13 slim, non-root user, curl healthcheck, Uvicorn workers) |
| [`Dockerfile.dev`](file:///c:/code/hackathon/backend/Dockerfile.dev) | Development image (Python 3.13 slim, `--reload` auto-reload on code change) |
| [`docker-compose.yml`](file:///c:/code/hackathon/backend/docker-compose.yml) | Production Compose stack for the backend service |
| [`docker-compose.dev.yml`](file:///c:/code/hackathon/backend/docker-compose.dev.yml) | Development Compose stack with live host directory mounting |
| [`.dockerignore`](file:///c:/code/hackathon/backend/.dockerignore) | Excludes virtualenvs, cache, and secrets from image layers |

---

## 🚀 Quick Start

### 1. Development Mode (with Live Hot-Reloading)

Mounts your local code into the container so any Python code change immediately reloads:

```bash
# Navigate to backend directory
cd backend

# Run development container
docker compose -f docker-compose.dev.yml up --build
```

- **Backend API:** [http://localhost:8000](http://localhost:8000)
- **API Docs / OpenAPI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Healthcheck:** [http://localhost:8000/api/settings](http://localhost:8000/api/settings)

---

### 2. Production Mode

Builds a hardened, standalone production image:

```bash
# Navigate to backend directory
cd backend

# Build and start in background
docker compose up -d --build

# View container logs
docker compose logs -f

# Stop production container
docker compose down
```

---

## 🛠️ Direct Docker Commands (without Compose)

### Build & Run Production Image

```bash
# Build production image
docker build -t civicaudit-backend:latest -f Dockerfile .

# Run with environment variables from .env
docker run -d \
  --name civicaudit-backend \
  -p 8000:8000 \
  --env-file .env \
  -v "$(pwd)/reports:/app/reports" \
  civicaudit-backend:latest
```

### Build & Run Development Image

```bash
# Build development image
docker build -t civicaudit-backend:dev -f Dockerfile.dev .

# Run with live volume mounting
docker run -it --rm \
  --name civicaudit-backend-dev \
  -p 8000:8000 \
  --env-file .env \
  -v "$(pwd):/app" \
  civicaudit-backend:dev
```

---

## 🔒 Security Best Practices Implemented

1. **Non-Root Execution:** The production container runs as `civicuser` (UID `10001`), mitigating privilege escalation risks.
2. **Layer Caching:** `requirements.txt` is copied and installed prior to copying source code, ensuring instant rebuilds when only code changes.
3. **Secret Isolation:** `.env` and credential files are excluded in `.dockerignore` to prevent leaking API keys into Docker image layers.
4. **Automated Healthcheck:** Monitors `/api/settings` every 30 seconds with automated Docker restarts if unresponsive.
5. **Report Persistence:** Host-mounted `/app/reports` ensures generated audit dossiers are persisted across container lifecycles.
