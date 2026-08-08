# Paceloop public server image.
#   docker build -t sprintgpt .
#   docker run -p 8000:8000 -v sprintgpt-data:/data \
#     -e SPRINTGPT_SECRET=change-me sprintgpt
FROM python:3.12-slim

WORKDIR /app

# Install deps first so image layers cache between code changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Keep the database (and session secret) on a mounted volume so accounts and
# runs survive container restarts and upgrades.
ENV SPRINTGPT_DB=/data/sprintgpt.db \
    HOST=0.0.0.0 \
    PORT=8000
VOLUME ["/data"]
EXPOSE 8000

CMD ["python", "serve.py"]
