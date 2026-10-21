# UniBot Web Module Dockerfile
# Version: 2026.10.21_1

FROM python:3.9-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set working directory
WORKDIR /app

# Copy module files
COPY module.yml module.conf module.api web.py requirements.txt ./

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies from requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories
RUN mkdir -p /var/log/unibot /var/unibot/secrets /etc/ssl/certs /etc/ssl/private /app/templates /app/static

# Create default templates directory structure
RUN mkdir -p /app/templates/pages /app/templates/layouts /app/static/css /app/static/js /app/static/images

# Set default environment variables
ENV MODULE_NAME=web \
    MODULE_VERSION=2026.10.21_1 \
    WEB_PORT=8080 \
    FLASK_ENV=production \
    FLASK_APP=web.py

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/api/v1/health').raise_for_status()" || exit 1

# Run the module
CMD ["python", "web.py", "--port", "8080", "--host", "0.0.0.0"]
