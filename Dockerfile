FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11
RUN apt-get update && apt-get install -y \
    apache2 \
    apache2-dev \
    build-essential \
    default-libmysqlclient-dev \
    vim \
    cron \
 && rm -rf /var/lib/apt/lists/*

# Leverage layer cache for deps
COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r /tmp/requirements.txt \
 && pip install mod_wsgi

# Setup Apache with pip-installed mod_wsgi (compiled against Python 3.11)
RUN mod_wsgi-express module-config > /etc/apache2/mods-available/wsgi_express.load \
 && a2enmod wsgi_express headers
COPY ./apache-flask.conf /etc/apache2/sites-available/apache-flask.conf
RUN a2ensite apache-flask
RUN a2dissite 000-default.conf

# Setup Logging
RUN mkdir -p /var/log/dash_app && chmod 777 /var/log/dash_app
RUN ln -sf /proc/self/fd/1 /var/log/apache2/access.log && \
    ln -sf /proc/self/fd/1 /var/log/apache2/error.log

WORKDIR /var/www/apache-flask

ENV PYTHONPATH "${PYTHONPATH}:/var/www/apache-flask"
ENV PORT 80
EXPOSE 80
EXPOSE 8050

# Copy the application code
COPY . /var/www/apache-flask/
# Copy built React frontend from first stage
COPY --from=frontend-build /app/frontend/dist /var/www/apache-flask/frontend/dist
RUN chmod +x /var/www/apache-flask/docker_start.sh

ENTRYPOINT ["/var/www/apache-flask/docker_start.sh"]
