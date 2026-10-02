FROM python:3.11-slim

# Install system dependencies, FFmpeg, and standard fonts for subtitles
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-dejavu-core \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Ensure media and cache directories exist with full write permissions (for Hugging Face / Render / Railway)
RUN mkdir -p output temp static assets && chmod -R 777 /app

ENV PORT=8000
EXPOSE 8000

# Dynamically bind to cloud-injected PORT (Render/Railway use $PORT, default is 8000)
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}"]
