# UniBot Apps Module Dockerfile
# Version: 2026.10.21_1
# This module dynamically loads functional submodules from the apps directory

FROM python:3.9-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set working directory
WORKDIR /app

# Copy module files
COPY module.yml module.conf module.api apps.py ./

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    requests==2.31.0 \
    pyyaml==6.0.1

# Create necessary directories
RUN mkdir -p /var/log/unibot /var/unibot/secrets /etc/ssl/certs /etc/ssl/private /app/apps

# Set default environment variables
ENV MODULE_NAME=apps \
    MODULE_VERSION=2026.10.21_1 \
    APPS_PORT=5006

# Expose port
EXPOSE 5006

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5006/api/v1/health').raise_for_status()" || exit 1

# Run the module
CMD ["python", "apps.py", "--port", "5006", "--host", "0.0.0.0", "--apps-dir", "/app"]
