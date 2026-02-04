# Multi-stage build for minimal Python FastAPI application with DuckDB
# This version uses python:slim which is more compatible with native extensions

FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies for DuckDB
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Verify DuckDB works
RUN python -c "import duckdb; print(f'✓ DuckDB {duckdb.__version__} installed successfully')"

# Final stage - minimal runtime image
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies for C++ extensions (DuckDB needs these)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libstdc++6 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY main.py .
COPY static ./static
COPY templates ./templates

# Set PATH for pip installed packages
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV GAME_DIR=/game_data

# Create directory for game data mount
RUN mkdir -p /game_data

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/', timeout=2)" || exit 1

# Run the application
ENTRYPOINT ["python", "main.py", "--port=8080", "--game_dir=/game_data"]