FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Set working directory
WORKDIR /app

# Install system dependencies (curl for healthcheck, sed for line-ending sanitization)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    sed \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency definition and install
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code and configurations (excluding test files for production security)
COPY backend /app/backend
COPY frontend /app/frontend
COPY .streamlit /app/.streamlit
COPY .env.example /app/
COPY entrypoint.sh /app/entrypoint.sh

# Ensure entrypoint script has Unix line endings and execute permissions
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Expose FastAPI; React is served by the separate frontend service
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/runtime || exit 1

# Run entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]


