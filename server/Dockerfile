FROM python:3.11-slim as builder
WORKDIR /app
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libstdc++6 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local
COPY main.py .
COPY static ./static
COPY templates ./templates
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV GAME_DIR=/game_data
RUN mkdir -p /game_data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/', timeout=2)" || exit 1
ENTRYPOINT ["python", "main.py", "--port=8080", "--game_dir=/game_data"]