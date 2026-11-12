FROM python:3.11-slim

WORKDIR /app

# Native codecs and OCR/frame-processing tools used by Vision and Media agents.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire Forge codebase into the container
COPY . .

# Expose the port FastAPI runs on
EXPOSE 8000

# Define the command to start the orchestrator using Uvicorn
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]