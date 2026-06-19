# SITA — Dockerfile for Railway
FROM python:3.13-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir pandas numpy ccxt pyyaml httpx aiofiles rich

# Copy source
COPY sita/ ./sita/
COPY pyproject.toml .

# Create directories
RUN mkdir -p /app/state/history /app/logs

# Paper trading by default
ENV SITA_TRADING_MODE=paper
ENV SITA_BASE_DIR=/app

# Health check
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python3 -c "from sita.config import VERSION; print('OK')" || exit 1

# Run
CMD ["python3", "-m", "sita", "run"]
