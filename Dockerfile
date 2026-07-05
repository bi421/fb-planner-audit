# Use slim Python image for Render.com
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source
COPY . .

# Ensure the app can import local packages
ENV PYTHONPATH=/app

# Render uses PORT env var; default to 10000 (as requested)
ENV PORT=10000

EXPOSE 10000

# Start server
CMD ["python", "run.py"]

