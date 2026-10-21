# UniBot Core Module Dockerfile
# Version: 2026.10.21_1

FROM python:3.9-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set working directory
WORKDIR /app

# Copy module files
COPY module.yml module.conf module.api core.py ./

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Create necessary directories
RUN mkdir -p /var/log/unibot /var/unibot/secrets /etc/ssl/certs /etc/ssl/private

# Copy secrets (in production, mount these as volumes)
# COPY secrets/ /var/unibot/secrets/

# Set default environment variables
ENV MODULE_NAME=core \
    MODULE_VERSION=2026.10.21_1 \
    CORE_PORT=5000

# Expose port
EXPOSE 5000

# Create log directory
RUN mkdir -p /var/log/unibot

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/api/v1/health').raise_for_status()" || exit 1

# Run the module
CMD ["python", "core.py", "--port", "5000", "--host", "0.0.0.0"]
