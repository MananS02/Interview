# ============================================================================
# Multi-Stage Dockerfile for FastAPI Interview Platform
# ============================================================================
# This Dockerfile uses multi-stage builds to create a minimal, secure,
# production-ready image with optimized layer caching.

# ----------------------------------------------------------------------------
# Stage 1: Builder Stage
# ----------------------------------------------------------------------------
# This stage installs all dependencies and builds the application.
# We use a full Python image here for building dependencies that may need
# compilation (like opencv-python, mediapipe, etc.)

FROM python:3.11-slim as builder

# Set build arguments for dependency installation
ARG DEBIAN_FRONTEND=noninteractive

# Install system dependencies required for building Python packages
# These are needed for OpenCV, MediaPipe, and other packages with native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    cmake \
    pkg-config \
    libgl1-mesa-dri \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory in builder stage
WORKDIR /app

# Copy only requirements file first for better layer caching
# This allows Docker to cache the dependency installation layer
# and only rebuild it when requirements.txt changes
COPY requirements.txt .

# Create a virtual environment and install Python dependencies
# Using virtual environment keeps the final image cleaner
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip setuptools wheel && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# ----------------------------------------------------------------------------
# Stage 2: Runner Stage (Production Image)
# ----------------------------------------------------------------------------
# This stage creates the final minimal production image.
# We use python:3.11-slim as the base to keep the image size small.

FROM python:3.11-slim as runner

# Set environment variables for production
# NODE_ENV equivalent for Python - prevents debug mode
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONHASHSEED=random \
    PYTHONPATH=/app \
    MPLCONFIGDIR=/tmp/matplotlib \
    FONTCONFIG_PATH=/etc/fonts

# Install only runtime system dependencies (no build tools)
# These are minimal dependencies needed for OpenCV and MediaPipe to run
# curl is included for healthcheck functionality
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-dri \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    ffmpeg \
    curl \
    ca-certificates \
    fontconfig \
    && rm -rf /var/lib/apt/lists/* && \
    apt-get clean

# Create a non-root user for security best practices
# Running as root in containers is a security risk
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set working directory
WORKDIR /app

# Copy the virtual environment from builder stage
# This includes all installed Python packages
COPY --from=builder /opt/venv /opt/venv

# Make sure we use the virtual environment's Python
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
# Copy in order: static files, templates, then source code
COPY static/ ./static/
COPY templates/ ./templates/
COPY app.py proctoring_service.py ./

# Create necessary directories with proper permissions
# These directories are created at runtime by the application
RUN mkdir -p audio_files /tmp/matplotlib && \
    chmod 777 /tmp/matplotlib && \
    chown -R appuser:appuser /app

# Switch to non-root user for security
USER appuser

# Expose the application port
# Port 8080 is the default port used by the FastAPI application
EXPOSE 8080

# Add healthcheck to monitor application status
# This allows Docker/Kubernetes to detect if the container is healthy
# Healthcheck: Check if the root endpoint responds with HTTP 200
# --interval: Check every 30 seconds
# --timeout: Each check times out after 10 seconds
# --start-period: Allow 40 seconds for the app to start before marking unhealthy
# --retries: Mark unhealthy after 3 consecutive failures
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# Set the default command to run the application
# Using uvicorn with production settings:
# - host 0.0.0.0: Listen on all interfaces (required for Docker)
# - port 8080: Application port
# - workers 2: Multiple workers supported now that sessions are stored in MongoDB
#   (Can scale up to 4 workers based on CPU cores for better concurrency)
# - log-level: Set appropriate log level
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2", "--log-level", "info"]
