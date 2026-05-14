# Use a slim Python image to keep size down (~150MB)
FROM python:3.11-slim

# Prevent python from writing pyc files to disc
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create a non-root user for security
RUN useradd --create-home --shell /bin/bash agent
WORKDIR /workspace

# Install essential build tools (often needed for pip install)
# Kept minimal. Add git if agents need to clone inside (usually better to clone outside and mount).
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Switch to non-root user
USER agent

# Default command keeps container alive but idle, waiting for exec commands
CMD ["tail", "-f", "/dev/null"]
