FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
RUN apt-get update && apt-get install -y \
    build-essential \
    default-libmysqlclient-dev \
    cron \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /app

ENV PYTHONPATH "${PYTHONPATH}:/app"
EXPOSE 80

COPY . /app/
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist
RUN chmod +x /app/docker_start.sh

ENTRYPOINT ["/app/docker_start.sh"]
