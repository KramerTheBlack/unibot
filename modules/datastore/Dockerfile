# UniBot Datastore Module Dockerfile
# Version: 2026.10.21_1

FROM python:3.9-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set working directory
WORKDIR /app

# Copy module files
COPY module.yml module.conf module.api datastore.py ./

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies for various databases
RUN pip install --no-cache-dir \
    psycopg2-binary==2.9.9 \
    pymysql==1.1.0 \
    pyodbc==4.0.39

# Create necessary directories
RUN mkdir -p /var/log/unibot /var/unibot/secrets /var/unibot/data /etc/ssl/certs /etc/ssl/private

# Set default environment variables
ENV MODULE_NAME=datastore \
    MODULE_VERSION=2026.10.21_1 \
    DATASTORE_PORT=5002

# Expose port
EXPOSE 5002

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5002/api/v1/health').raise_for_status()" || exit 1

# Run the module
CMD ["python", "datastore.py", "--port", "5002", "--host", "0.0.0.0"]
