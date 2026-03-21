# =========================
# 1. Builder Stage
# =========================
FROM python:3.12-slim AS builder

WORKDIR /app

# System deps (if needed for builds)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Environment optimization
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .

# Install dependencies into a custom location
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt


# =========================
# 2. Final Stage
# =========================
FROM python:3.12-slim

WORKDIR /app

# Create non-root user
RUN useradd -m appuser

# Copy only installed packages
COPY --from=builder /install /usr/local

# Copy application
COPY app ./app

# Set permissions
RUN chown -R appuser:appuser /app

# Switch user
USER appuser

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Expose port (documentation purpose)
EXPOSE 8000

# Run server (production tuned)
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2"]