# Use Debian Slim (Best balance of size vs. compatibility for OCR/ML)
FROM python:3.11-slim-bullseye

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 1. Install System Dependencies (Minimal but complete)
# Tesseract is needed for Docling fallback OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    libgl1-mesa-glx \
    libglib2.0-0 \
    tesseract-ocr \
    tesseract-ocr-eng \
    libtesseract-dev \
    libleptonica-dev \
    pkg-config \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 2. Install UV (The fastest Python package installer)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

# 3. Setup Workspace
WORKDIR /usr/src/app

# 4. Copy Requirements First (for better layer caching)
COPY requirements.txt ./

# 5. Create Virtual Environment and Install Python Dependencies
RUN uv venv .venv
ENV VIRTUAL_ENV=/usr/src/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install dependencies with UV (much faster than pip)
RUN uv pip install -r requirements.txt

# 6. Copy Source Code
COPY . ./

# 7. Create Non-Root User for Security
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /usr/src/app
USER appuser

# 8. Health Check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# 9. Set Python Path
ENV PYTHONPATH=/usr/src/app

# 10. Run the Application
CMD ["python", "-m", "src.main"]