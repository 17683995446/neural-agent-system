FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install uv for faster package installation
RUN pip install uv

# Copy project files
COPY pyproject.toml ./
COPY app ./app

# Install Python dependencies
RUN uv sync --frozen --no-dev

# Create necessary directories
RUN mkdir -p /app/task_output /app/code_repos /app/logs

# Expose port
EXPOSE 8000

# Default command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]